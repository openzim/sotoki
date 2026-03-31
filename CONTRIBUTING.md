# Contributing

Anybody is welcome to improve Sotoki.

## Setup
Install [hatch](https://hatch.pypa.io/latest/install/) if you don't have it, then:

```bash
hatch shell
```

This creates and activates the development environment with all dependencies included.

## Code style

Pre-commit hooks enforce `ruff`, `black`, `pyright`, trailing whitespace, and
end-of-file fixes. Install them once after setting up your environment:
```bash
hatch run pre-commit install
```

Run manually at any time:
```bash
hatch run pre-commit run --all-files
```

## Testing
```bash
hatch run pytest tests/
```

## Changelog

Add an entry under `[Unreleased]` in `CHANGELOG.md` for any user-facing change.
