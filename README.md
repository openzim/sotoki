# Sotoki

*Stack Overflow to Kiwix*

The goal of this project is to create a suite of tools to create
[zim](https://openzim.org) files required by
[kiwix](https://kiwix.org/) reader to make available [Stack Overflow](https://stackoverflow.com/)
offline (without access to Internet).

## Getting started

The use of btrfs as a file system is recommended (and required for stackoverflow)

Install non python dependencies:
```bash
sudo apt-get install jpegoptim pngquant gifsicle advancecomp python-pip python-virtualenv python-dev libxml2-dev libxslt1-dev libbz2-dev p7zip-full python-pillow gif2apng imagemagick
```

Create a virtual environment for python:
```bash
virtualenv --system-site-packages venv
```

Activate the virtual enviroment:
```bash
source venv/bin/activate
```

Install this lib:
```bash
pip install sotoki
```

```bash
sotoki <domain> <publisher> [--directory=<dir>] [--nozim] [--tag-depth=<tag_depth>] [--threads=<threads>] [--zimpath=<zimpath>] [--reset] [--reset-images] [--clean-previous] [--nofulltextindex] [--ignoreoldsite] [--nopic] [--no-userprofile]

```
You can use `sotoki -h` to have more explanation about these options

## Example

```bash
for S in `./list_all.sh` ; do sotoki $S Kiwix --threads=12 --reset --clean-previous --no-userprofile ; done
```
