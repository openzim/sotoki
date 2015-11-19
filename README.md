# Sotoki

*Stack Overflow to Kiwix*

The goal of this project is to create a suite of tools to create
[zim](http://www.openzim.rog) files required by
[kiwix](http://kiwix.org/) reader to make available [Stack Overflow](https://stackoverflow.com/)
offline (without access to Internet).

## Getting started

Download the last [stackexchange dump](https://archive.org/details/stackexchange)
using BitTorrent (only "superusers.com.7z" is necessary) and put it in the Sotoki
source code root.

Clone this repository:

```
git clone https://github.com/kiwix/sotoki.git
```

Install non python dependencies:

```
sudo apt-get install jpegoptim pngquant gifsicle
```

Install pip:

```
sudo apt-get install python-setuptools python-dev
```

Install virtualenv installed:
```
sudo pip install virtualenv
```

Create a virtual enviroment in the sokoki source code root dir:

```
virtualenv --no-site-packages venv
```

Activate the virtual enviroment:
```
source venv/bin/activate
```

Install the python requirements:

```
pip install -r requirements.txt
```

Copy `superusers.com.7z` and `unzip` it to `work/dump/`:

```
mkdir -p work/dump/
cp superusers.com.7z work/dump/
cd work/dump
7z e superusers.com.7z
```

Go back at the sotoki root and run the pipeline:

```
python sotoki.py run
```

