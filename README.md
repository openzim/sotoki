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



Install non python dependencies:

```
sudo apt-get install jpegoptim pngquant gifsicle advancecomp python-pip python-virtualenv python-dev libxml2-dev libxslt1-dev libbz2-dev p7zip-full python-pillow gif2apng imagemagick
```


Create a virtual environment for python:

```
virtualenv --system-site-packages venv
```

Activate the virtual enviroment:

```
source venv/bin/activate
```


Install this lib:

```
pip install sotoki
```


```
sotoki [domain of stackechange website] [publisher] [--directory (optional)] [--nozim (optional)]

```

