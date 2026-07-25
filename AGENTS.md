# Repository Guidelines

## Project Structure & Module Organization

This repository is a Flask + SQLite monolith. `app.py` contains the application factory, routes, permissions, and business workflows; `db.py` owns database connections and initialization, while `schema.sql` defines tables, indexes, and constraints. Jinja templates live in `templates/`, and browser assets are in `static/`. Integration tests are collected in `tests/test_app.py`. Keep runtime data out of the repository: the database, secret key, and uploads belong under `CAMPUS_DATA_DIR` or the platform-specific user data directory.

## Build, Test, and Development Commands

- `./init_linux.sh --demo` creates `.venv`, installs dependencies, initializes SQLite, and adds demo data.
- `./start_linux.sh` serves the app with Waitress at `127.0.0.1:5000` by default.
- `flask --app app run --debug` runs the development server after activating `.venv`.
- `python -m unittest -v` runs the full test suite against temporary databases.
- `flask --app app init-db` initializes an empty database; `flask --app app create-admin` creates the first administrator.

Windows contributors should use the matching `init_windows.bat` and `start_windows.bat` scripts.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, `snake_case` functions and variables, `UPPER_CASE` constants, and short helpers near their callers. Use parameterized SQLite queries and keep authorization and validation on the server. Templates use lowercase descriptive filenames such as `resource_detail.html`; CSS classes use kebab-case. JavaScript uses `const`/`let`, two-space indentation, and progressive enhancement. No formatter or linter is configured, so keep diffs focused and match surrounding code.

## Testing Guidelines

Tests use Python's built-in `unittest` and Flask's test client. Name methods `test_<behavior>` and add integration coverage for permissions, state transitions, validation, and database effects. Tests must use temporary directories and must not read or alter local demo data. Run `python -m unittest -v` before submitting changes.

## Commit & Pull Request Guidelines

The current history uses Conventional Commit-style subjects, for example `feat: build campus resource circulation platform`. Use an imperative `type: summary` subject such as `fix: reject duplicate resource applications`. Pull requests should explain the user-visible change, list verification performed, and link relevant issues. Include screenshots for template or CSS changes and call out schema, configuration, or security impacts explicitly.

## Security & Configuration Tips

Never commit `app.db`, `secret.key`, uploads, real credentials, or production data. Preserve CSRF checks, password hashing, upload validation, and role checks. Do not expose the development server directly to the public internet.
