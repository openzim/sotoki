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

Copy superusers.com.7z and unzip it to `dumps/superuser/`:

```
mkdir -p dumps/superuser/
cp superusers.com.7z dumps/superuser/
cd dumps/superuser/
7z e superusers.com.7z
```

Go back at the sotoki root and load the superuser dump inside sqlite database:

```
cd ../..
make load
```

Build the html pages:

```
make build-all
```

Now you can have a look at the results in your browser, just run the following
command to start the server:

```
make serve
```
