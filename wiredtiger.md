# wiredtiger

**wiredtiger only works on 64bit**

wiredtiger is key/value column aware key value store. It was chosen because it's
faster than bsddb and offer the features requires to build quickly fine tuned
in process databases. (It also support multithread but it is buggy in Python).

There is two part:

- Getting started present quickly wiredtiger
- TupleSpace: present the implementation of a generic schema-less database
  used in sotoki

## Getting started

A record is made of two parts the key and value. Each of them is subdivided into
a columns

```
key(column-one, column-two) -> value(column-three, column-four)
```

At low level records are ordered using the lexicographic order but at the API
level this looks like the natural order thanks to packing function that do the
job of converting integers into a byte representation that keeps the ordering.

At the very beginning you open a database and create a single session for it:

```python
connection = wiredtiger_open(path, 'create')
session = connection.open_session()
```

Then you can create/open tables and projections. For both you use the same
method `session.create` with different parameters. For instance to create
a table for `posts` that have three columns `uid`, `title`, `body`
and `category`:

```python
self.session.create(
    'table:posts',
    'key_format=S,value_format=SS,columns=(uid,title,body,category)'
)
```

`key_format` and `value_format` takes a column format configuration where each
character configure the type of the column. You can use among other things `S`
and `Q` for 64bit unsigned integers. The columns arguments names every column
this is required to do projections.

You can create a projection of this table to retrieve `post` records
with their category using the following projection:

```python
self.session.create(
    'index:posts:bycategory',
    'columns=(category,uid)'
)
```

This will create automatically a table `index:posts:bycategory` where `posts`
value is associated with the built with the `category` and `uid`. `uid` is added
to the key of the projection so that every record has a unique key.

Then you can open cursors over those tables using the `session.open_cursor(name)`
where `name` is for instance `table:posts` or `index:posts:bycategory`.

The interesting `Cursor` methods are the following:

```python
cursor.get_key()
cursor.set_key()

cursor.get_value()
cursor.set_value()

cursor.search(*key)
cursor.search_near(*key)

cursor.insert(*key)

```

# `TupleSpace`

`TupleSpace` is a generic schema-less in-process database that use the
*Entity-Attribute-Value* pattern aka. `EAV` used in datomic. It's called
in TupleSpace `uid`, `name` and `value`. This is a quick hack to get the
project going and has much improvements ahead to be ready to tackle other
situations but it works good enough for the current problem.

The advantages over raw wiredtiger:

#. not schema, no table to create, less code
#. we can still take advantage of ordering
#. fast enough
