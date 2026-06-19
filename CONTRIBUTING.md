# Contributing

Thanks for helping improve Heisenberg Backup Manager.

## Install

```bash
python -m venv .venv
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run the App

```bash
python app.py
```

## Run Tests

```bash
python -m pytest -q
python scripts/smoke_check.py
```

## Coding Rules

- Keep the UI thin.
- Keep backup logic in `services`, `engines`, and `transports`.
- Add tests when changing behavior in repository, service, engine, or transport code.
- Prefer readable, typed Python with small focused modules.

## Security

- Do not commit real credentials.
- Do not commit local `config/profiles.json` or `config/settings.json`.
- Use the example config files as templates for local setup.

