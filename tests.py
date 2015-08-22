#!/usr/bin/env python
import os
from shutil import rmtree
from unittest import TestCase

from ajgudb import pack
from ajgudb import unpack
from ajgudb import AjguDB
from ajgudb import TupleSpace
from ajgudb import AjguDBException


class TestPacking(TestCase):

    def test_pack_str(self):
        packed = pack('foobar')
        unpacked = unpack(packed)
        self.assertEqual(unpacked[0], 'foobar')

    def test_pack_multi_str(self):
        packed = pack('foobar', 'spam', 'egg')
        unpacked = unpack(packed)
        self.assertEqual(unpacked, ['foobar', 'spam', 'egg'])

    def test_pack_int(self):
        packed = pack(123)
        unpacked = unpack(packed)
        self.assertEqual(unpacked[0], 123)

    def test_pack_dict(self):
        packed = pack(dict(a=1))
        unpacked = unpack(packed)
        self.assertEqual(unpacked[0], dict(a=1))

    def test_pack_float(self):
        packed = pack(3.14)
        unpacked = unpack(packed)
        self.assertEqual(unpacked[0], 3.14)

    def test_pack_multi(self):
        packed = pack(123, 'foobar', 3.14, dict(a='b'))
        unpacked = unpack(packed)
        self.assertEqual(unpacked, [123, 'foobar', 3.14, dict(a='b')])


class TestTupleSpace(TestCase):

    def setUp(self):
        os.makedirs('/tmp/tuplespace')
        self.tuplespace = TupleSpace('/tmp/tuplespace')

    def tearDown(self):
        self.tuplespace.close()
        rmtree('/tmp/tuplespace')

    def test_add_and_get(self):
        self.tuplespace.add(1, key='value')
        self.assertEqual(self.tuplespace.get(1), dict(key='value'))

    def test_add_and_query(self):
        self.tuplespace.add(1, key='value')
        self.tuplespace.add(2, key='value')
        out = list(self.tuplespace.query('key', 'value'))
        self.assertEqual(out, [['key', 'value', 1], ['key', 'value', 2]])

    def test_add_and_query_key_only(self):
        self.tuplespace.add(1, key='value')
        self.tuplespace.add(2, key='something')
        out = list(self.tuplespace.query('key'))
        self.assertEqual(out, [['key', 'value', 1], ['key', 'something', 2]])

    def test_delete(self):
        self.tuplespace.add(1, key='value')
        self.tuplespace.delete(1)
        out = list(self.tuplespace.query('key'))
        self.assertEqual(out, [])


class DatabaseTestCase(TestCase):

    def setUp(self):
        os.makedirs('/tmp/ajgudb')
        self.graph = AjguDB('/tmp/ajgudb')

    def tearDown(self):
        self.graph.close()
        rmtree('/tmp/ajgudb')


def debug(self):
    self.graph._tuples.debug()


class TestGraphDatabase(DatabaseTestCase):

    def test_create_vertex(self):

        v = self.graph.vertex(label='test')
        self.assertTrue(v)

    def test_create_and_get_vertex(self):

        v = self.graph.vertex(label='test')

        v = self.graph.get(v.uid)

        self.assertTrue(v['label'], 'test')

    def test_create_modify_and_get_vertex(self):
        v = self.graph.vertex(label='test')
        v['value'] = 'key'
        v.save()

        v = self.graph.get(v.uid)

        self.assertTrue(v['value'] == 'key')

    def test_create_and_get_modify_and_get_again_vertex(self):

        v = self.graph.vertex(label='test')

        v = self.graph.get(v.uid)
        v['value'] = 'key'
        v.save()

        v = self.graph.get(v.uid)

        self.assertTrue(v['value'] == 'key')

    def test_create_modify_and_get_edge(self):

        start = self.graph.vertex(label='test')
        end = self.graph.vertex(label='test')
        edge = self.graph.edge(start, end)
        edge['hello'] = 'world'
        edge.save()

        edge = self.graph.get(edge.uid)

        self.assertTrue(edge['hello'] == 'world')

    def test_create_edge_and_checkout_vertex(self):

        start = self.graph.vertex(label='start')
        end = self.graph.vertex(label='end')
        self.graph.edge(start, end)

        # retrieve start and end
        start = self.graph.get(start.uid)
        end = self.graph.get(end.uid)
        self.assertTrue(list(start.outgoings()) and list(end.incomings()))

    def test_delete_vertex(self):

        v = self.graph.vertex(label='delete-node')
        v['value'] = 'key'
        v.save()

        # retrieve it
        self.graph.get(v.uid)

        v.delete()

        self.assertRaises(AjguDBException, self.graph.get, v.uid)

    def test_delete_edge(self):

        # vertices
        start = self.graph.vertex(label='start')
        end = self.graph.vertex(label='end')
        # first edge
        edge = self.graph.edge(start, end)

        # delete edge
        edge = self.graph.get(edge.uid)
        edge.delete()

        self.assertRaises(AjguDBException, self.graph.get, edge.uid)

        # check end and start vertex are up-to-date
        start = self.graph.get(start.uid)
        self.assertEquals(len(list(start.outgoings())), 0)
        end = self.graph.get(end.uid)
        self.assertEquals(len(list(end.incomings())), 0)


class TestGraphFiltering(DatabaseTestCase):

    def test_simple_filter(self):
        self.graph.vertex(label='test', foo='bar')
        self.graph.vertex(label='test', foo='bar')
        self.graph.vertex(label='another', foo='bar')
        self.assertEqual(self.graph.filter(label='test').count(), 2)

    def test_two_filters(self):
        self.graph.vertex(label='test', value=1, foo='bar')
        self.graph.vertex(label='test', value=2, foo='bar')
        self.graph.vertex(label='another', value=3, foo='bar')
        self.assertEqual(self.graph.filter(label='test', value=1).count(), 1)
