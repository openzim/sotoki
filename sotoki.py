#!/usr/bin/env python2
"""sotoki.

Usage:
  sotoki.py load <dump-directory> <database-directory>
  sotoki.py build <templates> <database> <output>
  sotoki.py (-h | --help)
  sotoki.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""
import os

from json import dumps
from json import loads

from docopt import docopt

from markdown import markdown

from jinja2 import Environment
from jinja2 import FileSystemLoader

from lxml.etree import parse

from wiredtiger.packing import pack
from wiredtiger.packing import unpack
from wiredtiger import wiredtiger_open


def render(output, template, templates, **context):
    templates = os.path.abspath(templates)
    env = Environment(loader=FileSystemLoader((templates,)))
    filters = dict(markdown=markdown)
    env.filters.update(filters)
    template = env.get_template(template)
    page = template.render(**context)
    with open(output, 'w') as f:
        f.write(page.encode('utf-8'))


# wiredtiger helper

WT_NOTFOUND = -31803


def iter_cursor(db, *key):
    """Iterate a cursor over records matching `key`
    starting near `key`. You *must* finish the iteration
    before reusing `cursor`"""
    cursor = db.index()
    cursor.set_key(key)
    match = [e for e in key if e]
    ok = cursor.search_near()
    if ok == WT_NOTFOUND:
        raise Exception('nothing found')
    if ok == -1:
        cursor.next()
    while True:
        other = cursor.get_key()
        ok = reduce(
            lambda x, y: (cmp(*y) == 0) and y,
            zip(match, other),
            True
        )
        if ok:
            yield other, cursor.get_value()
            if cursor.next() == WT_NOTFOUND:
                break
            else:
                continue
        else:
            break
    cursor.close()


class TupleSpace(object):
    """Generic database"""

    def __init__(self, path):
        self.connection = wiredtiger_open(path, 'create')
        self.session = self.connection.open_session()
        self.session.create(
            'table:tuples',
            'key_format=SS,value_format=QS,columns=(uid,name,kind,value)'
        )
        self.session.create(
            'index:tuples:index',
            'columns=(name,kind,value,uid)'
        )
        self.cursor = self.session.open_cursor('table:tuples')

    def index(self):
        return self.session.open_cursor('index:tuples:index')

    def insert(self, uid, name, value):
        # set key
        self.cursor.set_key(uid, name)

        # pack and set value
        if type(value) is int:
            self.cursor.set_value(1, pack('Q', value))
        elif type(value) is str:
            self.cursor.set_value(2, value)
        else:
            self.cursor.set_value(3, dumps(value))

        self.cursor.insert()
        self.cursor.reset()

    def _unpack_value(self, kind, value):
        if kind == 1:
            return unpack('Q', value)[0]
        elif kind == 2:
            return value
        else:
            return loads(value)

    def get(self, uid):
        def __get():
            self.cursor.set_key(uid, '')
            ok = self.cursor.search_near()
            if ok == WT_NOTFOUND:
                raise Exception('nothing found')
            if ok == -1:
                self.cursor.next()
            while True:
                other = self.cursor.get_key()
                ok = reduce(
                    lambda x, y: (cmp(*y) == 0) and y,
                    zip((uid,), other),
                    True
                )
                if ok:
                    _, name = other
                    value = self.cursor.get_value()
                    yield name, self._unpack_value(*value)

                    if self.cursor.next() == WT_NOTFOUND:
                        break
                    else:
                        continue
                else:
                    break

        return dict(__get())

    def close(self):
        self.cursor.close()
        self.session.close()
        self.connection.close()


def load(dump, database):
    # init database
    os.makedirs(database)
    db = TupleSpace(database)

    # parse Posts
    def to_db(filename):
        name = filename.split('.')[0].lower()
        xml = parse(os.path.join(dump, filename))
        posts = xml.getroot()
        for post in posts.iterchildren():
            # make sure this is a unique identifier
            uid = '%s:%s' % (name, post.attrib['Id'])
            # populate post attributes
            for key in post.keys():
                db.insert(uid, key, post.attrib[key])

    to_db('Posts.xml')
    to_db('Comments.xml')
    to_db('PostLinks.xml')

    db.close()

# build


def comments(db, id):
    records = iter_cursor(db, 'PostID', 2, id, '')
    for key, _ in records:
        name, kind, value, uid = key
        yield db.get(uid)


def questions(db):
    def uids():
        for item in iter_cursor(db, 'PostTypeId', 2, '1', ''):
            key, _ = item
            name, kind, value, uid = key
            yield uid
    # Consume the generator with list
    uids = uids()
    for uid in uids:
        yield db.get(uid)


def answers(db, id):
    # retrieve from `db` all tuples that have a key `ParentID`
    # and a value that is a string ie. kind `2` and value `id`
    records = iter_cursor(db, 'ParentID', 2, id, '')
    for key, _ in records:
        name, kind, value, uid = key
        answer = db.get(uid)
        yield answer, comments(db, answer['Id'])


def build(templates, database, output):
    db = TupleSpace(database)
    os.makedirs(os.path.join(output, 'posts'))
    for question in questions(db):
        id = question['Id']
        coms = list(comments(db, question['Id']))
        render(
            os.path.join(output, 'posts', '%s.html' % id),
            'post.html',
            templates,
            question=question,
            comments=coms,
            answers=answers(db, id)
        )
        break

if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['build']:
        build(arguments['<templates>'], arguments['<database>'], arguments['<output>'])
