# Contributing

Anybody is welcome to improve Sotoki.

## Setup
```bash
python3 -m venv ./env
./env/bin/pip install -e ".[dev]"
```

This installs all development dependencies including `ruff`, `black`, `pyright`,
`pytest`, and `pre-commit`.

## Code style

Pre-commit hooks enforce `ruff`, `black`, `pyright`, trailing whitespace, and
end-of-file fixes. Install them once after setting up your environment:
```bash
./env/bin/pre-commit install
```

Run manually at any time:
```bash
./env/bin/pre-commit run --all-files
```

## Testing
```bash
./env/bin/pytest tests/
```

## Changelog

Add an entry under `[Unreleased]` in `CHANGELOG.md` for any user-facing change.
