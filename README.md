Sotoki
======

`Sotoki` (*Stack Overflow to Kiwix*) is an
[openZIM](https://github.com/openzim) scraper to create offline
versions of [Stack Exchange](https://stackexchange.com) websites such
as [Stack Overflow](https://stackoverflow.com/).

It is based on Stack Exchange's Data Dumps hosted by [The Internet
Archive](https://archive.org/download/stackexchange/).

[![CodeFactor](https://www.codefactor.io/repository/github/openzim/sotoki/badge)](https://www.codefactor.io/repository/github/openzim/sotoki)
[![Docker](https://ghcr-badge.egpl.dev/openzim/sotoki/latest_tag?label=docker)](https://ghcr.io/openzim/sotoki)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![PyPI version shields.io](https://img.shields.io/pypi/v/sotoki.svg)](https://pypi.org/project/sotoki/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sotoki.svg)](https://pypi.org/project/sotoki)

## Usage

`Sotoki` works off a dump of a StackExchange website, as regularly created by StackExchange team. You must provide
a `--mirror` to use to download this dump and the `--domain` you want to scrape.

For instance, to download Sports StackExchange website as of August 2024 and based on dump hosted on archive.org,
you have to use `--mirror https://archive.org/download/stackexchange_20240829 --domain sports.stackexchange.com`.
Value of mirror is hence continuously updated as new dumps are published by StackExchange team.

Other CLI parameters are mandatory:
- `--title`: Title of the ZIM, must be less than 30 chars
- `--description`: Description of the ZIM, mist be less than 80 chars
- `--primary-css` and `--secondary-css`:
  - URL (or path) to primary and secondary stylesheets of domain being dumped
  - Can be found by opening website online and using your browser developer tools to find their URLs
  - For sports.stackexchange, proper values are:
    - `--primary-css https://cdn.sstatic.net/Sites/sports/primary.css`
    - `--secondary-css https://cdn.sstatic.net/Sites/sports/secondary.css`

### Docker

```bash
docker run -v my_dir:/output ghcr.io/openzim/sotoki sotoki --help
```

### Installation

`sotoki` is a Python3 software. If you are not using the
[Docker](https://ghcr.io/openzim/sotoki/) image, you are advised to use it in a
virtual environment to avoid installing software dependencies on your
system.

```sh
python3 -m venv ./env  # creates a virtual python environment in ./env folder
./env/bin/pip install -U pip  # upgrade pip (package manager). recommended
./env/bin/pip install -U sotoki  # install/upgrade sotoki inside virtualenv

# direct access to in-virtualenv sotoki binary, without shell-attachment
./env/bin/sotoki --help
# alias or link it for convenience
sudo ln -s $(pwd)/env/bin/sotoki /usr/local/bin/

# alternatively, attach virtualenv to shell
source env/bin/activate
sotoki --help
deactivate  # unloads virtualenv from shell
```

## Developers

Anybody is welcome to improve the Sotoki.

To run Sotoki off the git repository, you'll need to download a few
external dependencies that we pack in Python releases. Just run
`python src/sotoki/dependencies.py`.

See `requirements.txt` for the list of python dependencies.

## Users

You don't have to make your own ZIM files of Stack Exchange's Web 
sites. Updated ZIM files are built on a regular basis for all 
of them. Look at https://library.kiwix.org/?category=stack_exchange
to download them.
