Sotoki
======

`Sotoki` (*Stack Overflow to Kiwix*) is an
[openZIM](https://github.com/openzim) scraper to create offline
versions of [Stack Exchange](https://stackexchange.com) websites such
as [Stack Overflow](https://stackoverflow.com/).

It is based on Stack Exchange's Data Dumps hosted by [The Internet
Archive](https://archive.org/download/stackexchange/).

[![CodeFactor](https://www.codefactor.io/repository/github/openzim/sotoki/badge)](https://www.codefactor.io/repository/github/openzim/sotoki)
[![Docker](https://ghcr-badge.deta.dev/openzim/sotoki/latest_tag?label=docker)](https://ghcr.io/openzim/sotoki)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![PyPI version shields.io](https://img.shields.io/pypi/v/sotoki.svg)](https://pypi.org/project/sotoki/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sotoki.svg)](https://pypi.org/project/sotoki)

## Usage

`Sotoki` works off a `domain` that you must provide. That is the
domain-name of the stackexchange website you want to scrape. Run
`sotoki --list-all` to get a list of those

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
