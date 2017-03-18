# Sotoki

*Stack Overflow to Kiwix*

The goal of this project is to create a suite of tools to create
[zim](http://www.openzim.org) files required by
[kiwix](http://kiwix.org/) reader to make available [Stack Overflow](https://stackoverflow.com/)
offline (without access to Internet).

## Getting started

Download the last [stackexchange dump](https://archive.org/details/stackexchange)
using BitTorrent (only "superuser.com.7z" is necessary) and put it in the Sotoki
source code root.
The use of btrfs as a file system is recommended (and required for stackoverflow)


Clone this repository:

```
git clone https://github.com/kiwix/sotoki.git
```

Install non python dependencies:

```
sudo apt-get install jpegoptim pngquant gifsicle advancecomp python-pip python-virtualenv python-dev libxml2-dev libxslt1-dev libbz2-dev p7zip-full python-pillow
```

Create a virtual environment for python:

```
virtualenv --system-site-packages venv
```

Activate the virtual enviroment:

```
source venv/bin/activate
```

Install the python requirements:

```
pip install -r requirements.txt
```

Copy `superuser.com.7z` and `unzip` it to `work/dump/`:

```
mkdir -p work/dump/
cp superuser.com.7z work/dump/
cd work/dump
7z e superuser.com.7z
rename 'y/A-Z/a-z/' *
```

Go back at the sotoki root and run the pipeline:

```
python sotoki.py run [url of stackechange website] [publisher] [--directory (optional)] [--nozim (optional)]

```

If you want to restart sotoki after a run, you must remove work/output directory
