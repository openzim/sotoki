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

from jinja2 import Environment
from jinja2 import FileSystemLoader

from lxml.etree import parse

from wiredtiger.packing import pack
from wiredtiger.packing import unpack
from wiredtiger import wiredtiger_open


class Jinja:
    """Do it all jinja2 helper.

    Should work in any situation."""

    def __init__(self, *paths, **filters):
        paths = map(os.path.abspath, paths)
        self.environment = Environment(
            loader=FileSystemLoader(paths),
        )
        self.environment.filters.update(filters)

    def __call__(self, template, **context):
        template = self.environment.get_template(template)
        out = template.render(**context)
        return out

    @classmethod
    def render(cls, template, *paths, **context):
        filters = dict([e for e in context.items() if callable(e[1])])
        render = cls(*paths, **filters)
        output = render(template, **context)
        return output


def render(output, template, templates, **context):
    # `template` dirname is used to lookup other templates used
    # in `template`. This is done so to simply the signature
    # which is enough for this script.
    with open(output, 'w') as f:
        page = Jinja.render(template, templates, **context)
        f.write(page.encode('utf-8'))


# wiredtiger helper

WT_NOTFOUND = -31803


def iter_cursor(cursor, *key):
    """Iterate a cursor over records matching `key`
    starting near `key`. You *must* finish the iteration
    before reusing `cursor`"""
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
    cursor.reset()


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
        self.index = self.session.open_cursor('index:tuples:index')

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
        def iter():
            for key, value in iter_cursor(self.cursor, uid, ''):
                _, name = key
                yield name, self._unpack_value(*value)

        return dict(iter())

    def close(self):
        self.cursor.close()
        self.index.close()
        self.session.close()
        self.connection.close()


def load(dump, database):
    # init database
    # FIXME: handle error
    os.makedirs(database)
    db = TupleSpace(database)
    # parse Posts
    xml = parse(os.path.join(dump, 'Posts.xml'))
    posts = xml.getroot()
    for post in posts.iterchildren():
        # make sure this is a unique identifier
        uid = 'post:' + post.attrib['Id']
        # populate post attributes
        for key in post.keys():
            db.insert(uid, key, post.attrib[key])
    db.close()


# build

def questions(db):
    # XXX: only one cursor is available, so we must finish
    # the query before starting another one. In this case `db.get`
    def uids():
        for item in iter_cursor(db.index, 'PostTypeId', 2, '1', ''):
            key, _ = item
            name, kind, value, uid = key
            yield uid
    # Consume the generator with list
    uids = list(uids())
    for uid in uids:
        # It's ok to be lazy
        # because `db.get` finish it's query before returning
        yield db.get(uid)


def answers(db, id):
    # retrieve from `db.index` all tuples that have a key `ParentID`
    # and a value that is a string ie. kind `2` and value `id`
    # XXX: last field ie. `uid` is left empty, that's the one we interested in
    records = iter_cursor(db.index, 'ParentID', 2, id, '')
    for key, _ in records:
        name, kind, value, uid = key
        yield db.get(uid)


def build(templates, database, output):
    db = TupleSpace(database)
    os.makedirs(os.path.join(output, 'posts'))
    for question in questions(db):
        id = question['Id']
        print id

        render(
            os.path.join(output, 'posts', '%s.html' % id),
            'post.html',
            templates,
            question=question,
            answers=answers(db, id)
        )


if __name__ == '__main__':
    arguments = docopt(__doc__, version='sotoki 0.1')
    if arguments['load']:
        load(arguments['<dump-directory>'], arguments['<database-directory>'])
    elif arguments['build']:
        build(arguments['<templates>'], arguments['<database>'], arguments['<output>'])
