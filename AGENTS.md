# Repository Guidelines

## Project Structure & Module Organization
- `tiklocal/` contains the Flask app; `app.py` wires routes, `run.py` provides the CLI entrypoint, and helper modules live alongside routes.
- `tiklocal/templates/` holds Jinja templates (`*.html`); match filenames to view names and use lower-case with hyphens when needed.
- `tiklocal/static/` stores Tailwind sources (`input.css`), compiled `output.css`, and vendor JS.
- `instance/` is created at runtime for per-machine overrides; keep secrets out of version control.

## Build, Test, and Development Commands
- `poetry install` sets up the Python environment with Flask, Waitress, and PyYAML.
- `poetry run tiklocal ~/MediaLibrary` launches the server against a local media directory; add `--port 9000` to test alternative ports.
- `npm run build-css` watches Tailwind sources and regenerates `static/output.css` while you iterate on UI changes.
- `npm run build-css-prod` minifies Tailwind output for release builds; run before publishing or creating screenshots.

## Coding Style & Naming Conventions
- Follow PEP 8: four-space indentation, snake_case for functions, and PascalCase only for classes or dataclasses.
- Keep Flask views lightweight; move shared helpers into module-level functions or new files in `tiklocal/` when they grow.
- Use explicit imports and type hints for new utilities; mirror existing docstring style for user-facing helpers.
- For templates, stick to descriptive block names (`content`, `sidebar`) and keep inline scripts minimal.

## Testing Guidelines
- No automated suite ships today; add `tests/` with `pytest` fixtures that exercise key routes via Flask’s test client.
- Run prospective suites with `poetry run pytest`; prefer temporary media directories created under `tmp_path`.
- Perform manual smoke tests by running `poetry run tiklocal <media_path>` and browsing `/`, `/gallery`, and `/browse`.

## Commit & Pull Request Guidelines
- Match the existing history: short, imperative messages (`fix: 调整视频播放布局`, `Release v0.4.0 …`); include scope prefixes when they clarify intent.
- Each PR should explain the problem, list functional changes, and link issues; attach screenshots or clips for UI updates.
- Confirm local testing (`tiklocal` run, Tailwind build, pytest when available) in the PR description and call out config files touched.

## Configuration Tips
- Accept `MEDIA_ROOT`, `TIKLOCAL_HOST`, and `TIKLOCAL_PORT` via env vars or `~/.config/tiklocal/config.yaml`; document defaults in PRs when they change.
- Keep large media samples out of the repo—reference relative paths (e.g., `~/Videos/demo`) in examples instead.
