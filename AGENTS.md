# Repository Guidelines

## Project Structure & Module Organization

    Prts-CN-New/
    ├── app.py              # Flask application factory and all routes
    ├── db.py               # SQLite connection, init helpers, and CLI commands
    ├── schema.sql           # Full DDL: users, resources, applications, lost_found
    ├── static/              # Frontend assets (app.css, app.js, logo.svg)
    ├── templates/           # Jinja2 templates (base.html + page templates)
    ├── tests/
    │   └── test_app.py      # unittest-based integration tests
    ├── requirements.txt     # Flask + Waitress
    ├── init_*.bat/sh        # One-time: create venv, install deps, init DB
    └── start_*.bat/sh       # Launch via Waitress on 127.0.0.1:5000

The app follows a **flat module layout**: `app.py` is a single-file Flask app
using the factory pattern (`create_app()`). Database helpers live in `db.py`.
Templates extend `base.html` and are organized by feature (resources, auth,
lost_found, etc.).

## Build, Test, and Development Commands

| Command | Purpose |
|---|---|
| `init_windows.bat` / `init_linux.sh` | Create `.venv`, install deps, init SQLite database, create admin user. Pass `--demo` to seed demo data. |
| `start_windows.bat` / `start_linux.sh` | Launch via Waitress at `127.0.0.1:5000`. Set `CAMPUS_HOST` / `CAMPUS_PORT` env vars to override. |
| `python -m unittest discover -s tests -v` | Run all tests. |
| `flask --app app init-db` | Re-initialize the database (destroys all data). |
| `flask --app app create-admin` | Interactively create an admin user. |

## Coding Style & Naming Conventions

- **Python**: 4-space indentation. Standard library imports first, then third-party, then local (`from db import ...`).
- **Type hints**: Used on function signatures throughout `db.py` and `app.py`.
- **SQL**: Table and column names are `snake_case`. Foreign keys enabled via `PRAGMA foreign_keys = ON`. Use `schema.sql` as the single source of truth for DDL.
- **Templates**: Jinja2 templates extend `base.html`. Page templates named after the feature (e.g., `resources.html`, `resource_detail.html`).
- No formatter or linter is currently configured.

## Testing Guidelines

Tests live in `tests/test_app.py` using Python's built-in `unittest`
framework. The test class `CampusAppTest` creates a temporary SQLite database per
test run via `setUp`/`tearDown`. Helper methods (`register`, `login`,
`publish_resource`, etc.) reduce boilerplate.

- Run with: `python -m unittest discover -s tests -v`
- Tests cover registration, login, resource CRUD, applications, and lost-found matching.
- Add new test methods to `CampusAppTest` following the existing helper pattern.

## Commit & Pull Request Guidelines

The project uses **Conventional Commits**: `feat:`, `fix:`, `refactor:`, etc.

- Keep commits small and focused on one logical change.
- PR descriptions should summarize what changed and why.
- If the change touches the database, include any schema migration notes.
