Lorm: A light weight mysql client library.
==========================================

.. image:: https://img.shields.io/pypi/v/lorm.svg
    :target: https://pypi.python.org/pypi/lorm

Lorm is a light weight mysql client library for Python.
Built-in connection pool, Django style lookup expressions.


Installation
------------
The last stable release is available on PyPI and can be installed with ``pip``::

    $ pip install lorm

Example
--------
.. code:: sql

    CREATE TABLE `pets` (
      `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
      `name` varchar(20) NOT NULL DEFAULT '',
      `add_time` datetime DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

**Connect to Mysql**

.. code:: python

    >>> import pymysql
    >>> import lorm
    >>> db = lorm.Hub(pymysql)
    >>> db.add_pool('default', host='localhost', port=3306, user='root', 
        passwd='root', db='test', autocommit=True, pool_size=8, wait_timeout=30)

**Insert**

.. code:: python

    >>> db.default.pets.create(name='cat')
    1

**Query**

.. code:: python

    >>> db.default.pets.get(id=1)
    {u'id': 2, u'name': u'cat'}

**Row Style**

.. code:: python

    >>> db.default.pets.filter(id__lt=10).select('id')[:]
    [{u'id': 1}, {u'id': 2}, {u'id': 4}, {u'id': 5}, {u'id': 6}, {u'id': 7}, {u'id': 8}, {u'id': 9}]
    >>> db.default.pets.filter(id__lt=10).values('id')[:]
    ((1,), (2,), (4,), (5,), (6,), (7,), (8,), (9,))
    >>> db.default.pets.filter(id__lt=10).flat('id')[:]
    [1, 2, 4, 5, 6, 7, 8, 9]

**Raw SQL**

.. code:: python

    >>> db.default.fetchall("select * from pets")
    ((1, u'cat'), (2, u'dog'), (3, u'bird'))

**Transaction**

.. code:: python

    >>> with db.default as c:
    >>>     print c.pets.create(name='fish')

For more examples, see `example.py <https://github.com/zii/lorm/blob/master/example.py>`_

Features
--------
- Built-in Connection pool
- Django style lookup expressions
- Concurrent safe
- Gevent friendly
- Dynamically driver
