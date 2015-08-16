# sotoki

*StackOverflow to Kiwi*

The goal of this project is to create a suite of tools to create
zim files required by [kiwix](http://kiwix.org/) reader to make
available stackoverflow offline.

Download the [stackexchange dumps using bittorrent](https://archive.org/details/stackexchange) right now. You can to download only `superusers.com.7z`
in your favorite bittorrent client to do the tests.


# Getting started

First clone this repository:

```bash
git clone https://git.framasoft.org/amz3/sotoki.git
```

wiredtiger [documentation](http://source.wiredtiger.com/2.6.1/index.html)
is used as database. The reason for this choice and a tutorial are available
in `wiredtiger.md` file next to this file. 

You need to install wiredtiger from source. This is very easy. You will
need to install linux headers. On debian amd64 use the following command:

```bash
sudo apt-get install linux-headers-amd64
```

Then download wiredtiger:

```bash
http://source.wiredtiger.com/releases/wiredtiger-2.6.1.tar.bz2
```

And compile and install it with:

```
./configure --enable-python
make
make install
```

You will also need python 2.7 since wiredtiger has binding only for
python 2. To install python dependencies use a virtualenv that has
access to system python packages. Using virtualenvwrapper you can
create one with the following command:

```
mkvirtualenv sotoki --system-site-packages
```

Then install requirements:

```
pip install -r requirements.txt
```
