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
    if "uid" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN uid TEXT")
    if "credit_score" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN credit_score INTEGER NOT NULL DEFAULT 100")
    if "credit_recovered_on" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN credit_recovered_on TEXT NOT NULL DEFAULT ''")
    user_sql = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0]
    if "'owner'" not in user_sql:
        db.execute("PRAGMA foreign_keys=OFF")
        db.executescript("""
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT UNIQUE, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                name TEXT NOT NULL, student_no TEXT NOT NULL UNIQUE, grade TEXT NOT NULL,
                class_name TEXT NOT NULL, contact TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','admin','owner')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
                must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0,1)),
                credit_score INTEGER NOT NULL DEFAULT 100 CHECK (credit_score BETWEEN 0 AND 120),
                credit_recovered_on TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users_new(id,uid,username,password_hash,name,student_no,grade,class_name,contact,role,is_active,must_change_password,credit_score,credit_recovered_on,created_at)
            SELECT id,uid,username,password_hash,name,student_no,grade,class_name,contact,role,is_active,must_change_password,credit_score,credit_recovered_on,created_at FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
            CREATE TRIGGER users_assign_uid AFTER INSERT ON users
            WHEN NEW.uid IS NULL OR NEW.uid = ''
            BEGIN UPDATE users SET uid = 'U-' || lower(hex(randomblob(16))) WHERE id = NEW.id; END;
        """)
        db.execute("PRAGMA foreign_keys=ON")
    post_columns = {row["name"] for row in db.execute("PRAGMA table_info(posts)")}
    if "uid" not in post_columns:
        db.execute("ALTER TABLE posts ADD COLUMN uid TEXT")
    if "original_body" not in post_columns:
        db.execute("ALTER TABLE posts ADD COLUMN original_body TEXT NOT NULL DEFAULT ''")
    if "view_count" not in post_columns:
        db.execute("ALTER TABLE posts ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0")
    resource_columns = {row["name"] for row in db.execute("PRAGMA table_info(resources)")}
    if "kind" not in resource_columns:
        db.execute("ALTER TABLE resources ADD COLUMN kind TEXT NOT NULL DEFAULT 'supply'")
    comment_columns = {row["name"] for row in db.execute("PRAGMA table_info(comments)")}
    if "original_body" not in comment_columns:
        db.execute("ALTER TABLE comments ADD COLUMN original_body TEXT NOT NULL DEFAULT ''")
    db.execute("UPDATE users SET uid='U-' || lower(hex(randomblob(16))) WHERE uid IS NULL OR uid='' ")
    db.execute("UPDATE posts SET uid='P-' || lower(hex(randomblob(16))) WHERE uid IS NULL OR uid='' ")
    db.execute("UPDATE posts SET original_body=body WHERE original_body='' ")
    db.execute("UPDATE comments SET original_body=body WHERE original_body='' ")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_uid ON users(uid)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS posts_uid ON posts(uid)")
    db.execute("UPDATE users SET credit_score=100 WHERE credit_score IS NULL")
    if not db.execute("SELECT 1 FROM users WHERE role='owner'").fetchone():
        db.execute("UPDATE users SET role='owner' WHERE id=(SELECT id FROM users WHERE role='admin' AND is_active=1 ORDER BY id LIMIT 1)")
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
