Sotoki
========

`sotoki` (*stackoverflow to kiwix*) is an [OpenZIM](https://github.com/openzim) scraper to create offline versions of [Stack Exchange](https://stackexchange.com) websites such as [stack overflow](https://stackoverflow.com/).

It is based on Stack Exchange's Data Dumps hosted by [The Internet Archive](https://archive.org/download/stackexchange/).

[![CodeFactor](https://www.codefactor.io/repository/github/openzim/sotoki/badge)](https://www.codefactor.io/repository/github/openzim/sotoki)
[![Docker](https://img.shields.io/docker/v/openzim/sotoki?label=docker&sort=semver)](https://hub.docker.com/r/openzim/sotoki)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![PyPI version shields.io](https://img.shields.io/pypi/v/sotoki.svg)](https://pypi.org/project/sotoki/)

## ⚠️ Warning

`sotoki` is undergoing a major rewrite to use libzim7 and its python binding in order to bypass filesystem limitations seen in version `1.x`. Use tagged version until this warning is removed as **current master is not-functionnal**.

## Usage

`sotoki` works off a `domain` that you must provide. That is the domain-name of the stackexchange website you want to scrape. Run `sotoki --list-all` to get a list of those

**Note**: when running off the git repository, you'll need to download a few external dependencies that we pack in Python releases. Just run `python src/sotoki/dependencies.py`

### Docker

```bash
docker run -v my_dir:/output openzim/sotoki sotoki --help
```

### Virtualenv

`sotoki` is a Python3 software. If you are not using the [Docker](https://docker.com) image, you are advised to use it in a virtual environment to avoid installing software dependencies on your system.

```bash
python3 -m venv env      # Create virtualenv
source env/bin/Activate  # Activate the virtualenv
pip3 install sotoki # Install dependencies
sotoki --help       # Display kolibri2zim help
```

Call `deactivate` to quit the virtual environment.

See `requirements.txt` for the list of python dependencies.

