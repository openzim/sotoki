# sotoki

*StackOverflow to Kiwix*

The goal of this project is to create a suite of tools to create
zim files required by [kiwix](http://kiwix.org/) reader to make
available stackoverflow offline.

Download the [stackexchange dumps using bittorrent](https://archive.org/details/stackexchange) right now. You can to download only `superusers.com.7z`
in your favorite bittorrent client to do the tests.


## Getting started

First clone this repository:

```
git clone https://git.framasoft.org/amz3/sotoki.git
```

Install leveldb using you system packages:

```
sudo apt-get install libleveldb1 libleveldb-dev
```

To install python dependencies use a virtualenv that has
access to system python packages. Using virtualenvwrapper you can
create one with the following command:

```
mkvirtualenv sotoki --system-site-packages
```

Then install requirements:

```
pip install -r requirements.txt
```

Then you can run the builder. Prepare a directory with all the files for a given
StackOverflow website inside a directory and run the following commands:

```
make load
make build-all
```

The first will create a wiredtiger database with all the info found in the dump.
The second will build the html pages.
