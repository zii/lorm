Lorm: Python ORM without models.
=================================

.. image:: https://img.shields.io/pypi/v/lorm.svg
    :target: https://pypi.python.org/pypi/lorm

Lorm is a light weight ORM library for Python, model-less, Django style lookup expressions. It's very suitable for small scripts. 


Installation
------------
The last stable release is available on PyPI and can be installed with ``pip``::

    $ pip install lorm

Example
-------
.. code:: sql

    CREATE TABLE `pets` (
      `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
      `name` varchar(20) NOT NULL DEFAULT '',
      `add_time` datetime DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

.. code:: python

    import lorm

    c = lorm.mysql_connect('localhost', 3306, 'root', '******', 'test')

    print c.user.get(host='localhost')

For more examples, see `test.py <https://github.com/zii/lorm/blob/master/test.py>`_.

Features
--------
- No Model, use table name directly.
- Auto reconnect
- Connection pool
- Django style lookup expressions
- Threading safe

Requirements
------------
- pymysql
