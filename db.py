import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext


def default_data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "CampusSmartFlow"
    return Path.home() / ".local" / "share" / "CampusSmartFlow"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    schema = Path(current_app.root_path, "schema.sql").read_text(encoding="utf-8")
    db = get_db()
    db.executescript(schema)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if "credit_score" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN credit_score INTEGER NOT NULL DEFAULT 100")
    if "credit_recovered_on" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN credit_recovered_on TEXT NOT NULL DEFAULT ''")
    db.execute("UPDATE users SET credit_score=100 WHERE credit_score IS NULL")
    db.commit()
    if os.name != "nt":
        Path(current_app.config["DATABASE"]).chmod(0o600)


def prune_backups(backup_dir: Path) -> None:
    for kind, keep in (("daily", 7), ("weekly", 4)):
        archives = sorted(backup_dir.glob(f"{kind}-*.zip"), reverse=True)
        for archive in archives[keep:]:
            archive.unlink()


def create_backup(data_dir: Path, database: Path, kind: str = "manual", created_by=None) -> Path:
    if kind not in {"daily", "weekly", "manual"}:
        raise ValueError("invalid backup kind")
    backup_dir = data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = backup_dir / f"{kind}-{stamp}.zip"
    with tempfile.TemporaryDirectory(dir=backup_dir) as temp_name:
        temp_dir = Path(temp_name)
        snapshot = temp_dir / "app.db"
        source = sqlite3.connect(database)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        partial = temp_dir / "backup.zip"
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as output:
            output.write(snapshot, "app.db")
            uploads = data_dir / "uploads"
            if uploads.exists():
                for item in uploads.rglob("*"):
                    if item.is_file():
                        output.write(item, Path("uploads", item.relative_to(uploads)))
        os.replace(partial, archive)
    record_db = sqlite3.connect(database)
    try:
        record_db.execute(
            "INSERT INTO backup_records(filename,kind,size_bytes,created_by) VALUES(?,?,?,?)",
            (archive.name, kind, archive.stat().st_size, created_by),
        )
        record_db.commit()
    finally:
        record_db.close()
    prune_backups(backup_dir)
    return archive


def restore_backup(data_dir: Path, database: Path, archive_name: str) -> None:
    if Path(archive_name).name != archive_name:
        raise ValueError("backup must be selected by filename")
    archive = data_dir / "backups" / archive_name
    if not archive.is_file():
        raise FileNotFoundError(archive_name)
    create_backup(data_dir, database, "manual")
    with tempfile.TemporaryDirectory(dir=data_dir) as temp_name:
        temp_dir = Path(temp_name)
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe backup entry")
            source.extractall(temp_dir)
        snapshot = temp_dir / "app.db"
        if not snapshot.is_file():
            raise ValueError("backup has no database")
        restored_uploads = temp_dir / "uploads"
        uploads = data_dir / "uploads"
        old_uploads = data_dir / ".uploads-before-restore"
        if old_uploads.exists():
            shutil.rmtree(old_uploads)
        if uploads.exists():
            os.replace(uploads, old_uploads)
        try:
            if restored_uploads.exists():
                os.replace(restored_uploads, uploads)
            else:
                uploads.mkdir(mode=0o700)
            os.replace(snapshot, database)
        except Exception:
            if uploads.exists():
                shutil.rmtree(uploads)
            if old_uploads.exists():
                os.replace(old_uploads, uploads)
            raise
        if old_uploads.exists():
            shutil.rmtree(old_uploads)


@click.command("init-db")
@with_appcontext
def init_db_command() -> None:
    init_db()
    click.echo("数据库已初始化。")


@click.command("create-backup")
@click.option("--kind", type=click.Choice(("daily", "weekly", "manual")), default="manual")
@with_appcontext
def create_backup_command(kind) -> None:
    archive = create_backup(
        Path(current_app.config["DATA_DIR"]), Path(current_app.config["DATABASE"]), kind
    )
    click.echo(f"备份已创建：{archive.name}")


@click.command("restore-backup")
@click.argument("archive_name")
@click.option("--confirm", is_flag=True, help="确认停止服务并覆盖当前数据")
@with_appcontext
def restore_backup_command(archive_name, confirm) -> None:
    if not confirm:
        raise click.ClickException("恢复会覆盖当前数据；确认后请添加 --confirm。")
    close_db()
    try:
        restore_backup(
            Path(current_app.config["DATA_DIR"]),
            Path(current_app.config["DATABASE"]),
            archive_name,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("恢复完成。")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_backup_command)
    app.cli.add_command(restore_backup_command)
