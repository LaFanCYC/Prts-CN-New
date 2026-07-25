import os
import sqlite3
from pathlib import Path

import click
from flask import current_app, g


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
    get_db().executescript(schema)
    if os.name != "nt":
        Path(current_app.config["DATABASE"]).chmod(0o600)


@click.command("init-db")
def init_db_command() -> None:
    init_db()
    click.echo("数据库已初始化。")


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
