import os
import struct

from msgpack import dumps
from msgpack import loads

from plyvel import DB


class AjguDBException(Exception):
    pass


def pack(*values):
    def __pack(value):
        if type(value) is int:
            return '1' + struct.pack('>q', value)
        elif type(value) is str:
            return '2' + struct.pack('>q', len(value)) + value
        else:
            data = dumps(value, encoding='utf-8')
            return '3' + struct.pack('>q', len(data)) + data
    return ''.join(map(__pack, values))


def unpack(packed):
    kind = packed[0]
    if kind == '1':
        value = struct.unpack('>q', packed[1:9])[0]
        packed = packed[9:]
    elif kind == '2':
        size = struct.unpack('>q', packed[1:9])[0]
        value = packed[9:9+size]
        packed = packed[size+9:]
    else:
        size = struct.unpack('>q', packed[1:9])[0]
        value = loads(packed[9:9+size])
        packed = packed[size+9:]
    if packed:
        values = unpack(packed)
        values.insert(0, value)
    else:
        values = [value]
    return values


class TupleSpace(object):
    """Generic database"""

    def __init__(self, path):
        self.db = DB(
            os.path.join(path, 'tuples'),
            create_if_missing=True,
            lru_cache_size=10*10,
            bloom_filter_bits=64,
        )
        self.tuples = self.db.prefixed_db(b'tuples')
        self.index = self.db.prefixed_db(b'index')

    def close(self):
        self.db.close()

    def get(self, uid):
        def __get():
            for key, value in self.tuples.iterator(start=pack(uid)):
                other, key = unpack(key)
                if other == uid:
                    value = unpack(value)[0]
                    yield key, value
                else:
                    break

        tuples = dict(__get())
        return tuples

    def add(self, uid, **properties):
        tuples = self.tuples.write_batch(transaction=True)
        index = self.index.write_batch(transaction=True)
        for key, value in properties.items():
            tuples.put(pack(uid, key), pack(value))
            index.put(pack(key, value, uid), '')
        tuples.write()
        index.write()

    def delete(self, uid):
        tuples = self.tuples.write_batch(transaction=True)
        index = self.index.write_batch(transaction=True)
        for key, value in self.tuples.iterator(start=pack(uid)):
            other, name = unpack(key)
            if uid == other:
                tuples.delete(key)
                value = unpack(value)[0]
                index.delete(pack(name, value, uid))
            else:
                break
        tuples.write()
        index.write()

    def update(self, uid, **properties):
        self.delete(uid)
        self.add(uid, **properties)

    def debug(self):
        for key, value in self.tuples.iterator():
            uid, key = unpack(key)
            value = unpack(value)[0]
            print(uid, key, value)

    def query(self, key, value=''):
        match = (key, value) if value else (key,)

        iterator = self.index.iterator(start=pack(key, value))
        for key, value in iterator:
            other = unpack(key)
            ok = reduce(
                lambda previous, x: (cmp(*x) == 0) and previous,
                zip(match, other),
                True
            )
            if ok:
                yield other
            else:
                break


class Vertex(dict):

    def __init__(self, graphdb, uid, properties):
        self._graphdb = graphdb
        self.uid = uid
        super(Vertex, self).__init__(properties)

    def __eq__(self, other):
        return self.uid == other.uid

    def _iter_edges(self, _vertex, **filters):
        def __edges():
            key = '_meta_%s' % _vertex
            records = self._graphdb._tuples.query(key, self.uid)
            for key, name, uid in records:
                properties = self._graphdb._tuples.get(uid)
                yield Edge(self._graphdb, uid, properties)

        def __filter(edges):
            items = set(list(filters.items()))
            for edge in edges:
                if items.issubset(edge.items()):
                    yield edge

        query = dict(property='_meta_' + _vertex, uid=self.uid)
        return ImprovedIterator(__filter(__edges()), query)

    def incomings(self, **filters):
        return self._iter_edges('end', **filters)

    def outgoings(self, **filters):
        return self._iter_edges('start', **filters)

    def save(self):
        self._graphdb._tuples.update(
            self.uid,
            _meta_type='vertex',
            **self
        )
        return self

    def delete(self):
        self._graphdb._tuples.delete(self.uid)


class Edge(dict):

    def __init__(self, graphdb, uid, properties):
        self._graphdb = graphdb
        self.uid = uid
        self._start = properties.pop('_meta_start')
        self._end = properties.pop('_meta_end')
        super(Edge, self).__init__(properties)

    def __eq__(self, other):
        return self.uid == other.uid

    def start(self):
        properties = self._graphdb._tuples.get(self._start)
        return Vertex(self._graphdb, self._start, properties)

    def end(self):
        properties = self._graphdb._tuples.get(self._end)
        return Vertex(self._graphdb, self._end, properties)

    def save(self):
        self._graphdb._tuples.update(
            self.uid,
            _meta_type='edge',
            _meta_start=self._start,
            _meta_end=self._end,
            **self
        )
        return self

    def delete(self):
        self._graphdb._tuples.delete(self.uid)


class ImprovedIterator(object):

    sentinel = object()

    def __init__(self, iterator, query):
        self.iterator = iterator
        self.query = query

    def __iter__(self):
        return self.iterator

    def one(self, default=sentinel):
        try:
            return next(self.iterator)
        except StopIteration:
            if default is self.sentinel:
                msg = 'not found. Query: %s' % self.query
                raise AjguDBException(msg)
            else:
                return default

    def all(self):
        return list(self.iterator)

    def count(self):
        return reduce(lambda x, y: x+1, self.iterator, 0)

    def end(self):
        def __iter():
            for item in self.iterator:
                if item:
                    yield item.end()
        query = dict(self.query)
        query['end'] = True
        return type(self)(__iter(), query)

    def start(self):
        def __iter():
            for item in self.iterator:
                if item:
                    yield item.start()
        query = dict(self.query)
        query['start'] = True
        return type(self)(__iter(), query)

    def descending(self, key):
        return sorted(self.iterator, key=lambda x: x[key], reverse=True)


class AjguDB(object):

    def __init__(self, path):
        self._tuples = TupleSpace(path)

    def close(self):
        self._tuples.close()

    def _uid(self):
        try:
            counter = self._tuples.get(0)['counter']
        except:
            self._tuples.add(0, counter=1)
            counter = 1
        else:
            counter += 1
            self._tuples.update(0, counter=counter)
        finally:
            return counter

    def transaction(self):
        return self._tuples.transaction()

    def get(self, uid):
        properties = self._tuples.get(uid)
        if properties:
            meta_type = properties.pop('_meta_type')
            if meta_type == 'vertex':
                return Vertex(self, uid, properties)
            else:
                return Edge(self, uid, properties)
        else:
            raise AjguDBException('not found')

    def vertex(self, **properties):
        uid = self._uid()
        self._tuples.add(uid, _meta_type='vertex', **properties)
        return Vertex(self, uid, properties)

    def edge(self, start, end, **properties):
        uid = self._uid()
        properties['_meta_start'] = start.uid
        properties['_meta_end'] = end.uid
        self._tuples.add(uid, _meta_type='edge', **properties)
        return Edge(self, uid, properties)

    def filter(self, **filters):
        def __iter():
            items = set(list(filters.items()))
            key, value = filters.items()[0]
            for _, _, uid in self._tuples.query(key, value):
                element = self.get(uid)
                if items.issubset(element.items()):
                    yield element

        return ImprovedIterator(__iter(), filters)
