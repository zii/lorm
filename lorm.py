#coding: utf-8
"A light weight python ORM without models."
import copy
import re
import sys
import time
import threading
import random

import pymysql
from pymysql.connections import Connection as BaseConnection
from pymysql.converters import escape_string

__version__ = '0.2.21'
__all__ = [
    'mysql_connect',
    'Struct',
    'MysqlConnection',
    'MysqlPool',
    'SQLError',
    'QuerySet',
]

LOOKUP_SEP = '__'


class Struct(dict):
    """
    Dict to object. e.g.:
    >>> o = Struct({'a':1})
    >>> o.a
    >>> 1
    >>> o.b
    >>> None
    """
    def __init__(self, *e, **f):
        if e:
            self.update(e[0])
        if f:
            self.update(f)

    def __getattr__(self, name):
        # Pickle is trying to get state from your object, and dict doesn't implement it.
        # Your __getattr__ is being called with "__getstate__" to find that magic method,
        # and returning None instead of raising AttributeError as it should.
        if name.startswith('__'):
            raise AttributeError
        return self.get(name)

    def __setattr__(self, name, val):
        self[name] = val

    def __delattr__(self, name):
        self.pop(name, None)

    def __hash__(self):
        return id(self)


def mysql_connect(*args, **kwargs):
    """
    Params:
    host='', port=3306, username='', password='', database='',
    autocommit=True, charset='utf8', autoreconnect=False
    """
    c = MysqlConnection()
    c.connect(*args, **kwargs)
    return c


def mysql_pool(*args, **kwargs):
    p = MysqlPool(*args, **kwargs)
    return p


class SQLError(Exception):
    pass


class PyMysqlConnection(BaseConnection):

    _last_query = ''

    def __init__(self, *args, **kwargs):
        self.auto_reconnect = kwargs.pop('auto_reconnect', False)
        self.lock = threading.Lock()
        self.last_query = ''
        super(PyMysqlConnection, self).__init__(*args, **kwargs)

    def reconnect(self):
        if self._sock is not None:
            self.close()
        try:
            self.connect()
        except:
            return False
        return True

    def reconnect_until_ok(self):
        delay = 1
        while 1:
            #print 'reconnecting..'
            ok = self.reconnect()
            if ok:
                #print 'reconnected.'
                break
            time.sleep(delay)
            if delay < 4:
                delay *= 2

    def safe_ping(self):
        try:
            self.ping(False)
            return True
        except:
            return False

    def do_query(self, sql, unbuffered=False):
        while 1:
            try:
                PyMysqlConnection._last_query = self.last_query = sql
                return super(PyMysqlConnection, self).query(sql, unbuffered)
            except pymysql.err.ProgrammingError as e:
                raise SQLError(e)
            except:
                # closed by hand
                if self._sock is None:
                    raise
                if not self.auto_reconnect:
                    raise
                if self.safe_ping():
                    raise
                self.reconnect_until_ok()

    def query(self, sql, unbuffered=False):
        self.lock.acquire()
        try:
            self.do_query(sql, unbuffered)
        finally:
            self.lock.release()

    @property
    def locked(self):
        return self.lock.locked()


class ProxyConnection:

    def __init__(self, c, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.c = c

    def __getattr__(self, table_name):
        "return a queryset"
        if table_name.startswith('__'):
            raise AttributeError
        return QuerySet(self.c, table_name, *self.args, **self.kwargs)


class MysqlConnection:

    def __init__(self):
        self.conn = None
        self.conn_args = None

    def connect(self, host='', port=3306, username='', password='', database='',
                autocommit=True, charset='utf8', autoreconnect=False):
        args = locals()
        args.pop('self')
        self.conn_args = args
        c = PyMysqlConnection(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            charset=charset,
            autocommit=autocommit,
            auto_reconnect=autoreconnect,
        )
        self.conn = c
        return c

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def dup(self, **kwargs):
        """Create a new connection with same arguments."""
        o = MysqlConnection()
        assert self.conn_args, 'Connection is not established.'
        args = dict(self.conn_args)
        args.update(kwargs)
        o.connect(**args)
        return o

    @property
    def locked(self):
        return self.conn.locked if self.conn else False

    @property
    def last_query(self):
        return self.conn.last_query if self.conn else ''

    def set_charset(self, charset):
        self.conn.set_charset(charset)

    @property
    def charset(self):
        return self.conn.charset

    def literal(self, value):
        return self.conn.literal(value)

    def escape(self, value):
        return self.conn.escape(value)

    def fetchall(self, sql, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def fetchone(self, sql, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchone()

    def fetchall_dict(self, sql, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            fields = [r[0] for r in cursor.description]
            rows = cursor.fetchall()
            return [Struct(zip(fields,row)) for row in rows]

    def fetchone_dict(self, sql, args=()):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            row = cursor.fetchone()
            if not row:
                return
            fields = [r[0] for r in cursor.description]
            return Struct(zip(fields, row))

    def execute(self, sql, args=()):
        """
        Returns affected rows and lastrowid.
        """
        with self.conn.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.rowcount, cursor.lastrowid

    def execute_many(self, sql, args=()):
        """
        Execute a multi-row query. Returns affected rows.
        """
        with self.conn.cursor() as cursor:
            return cursor.executemany(sql, args)

    def callproc(self, procname, *args):
        """Execute stored procedure procname with args, returns result rows"""
        with self.conn.cursor() as cursor:
            cursor.callproc(procname, args)
            return cursor.fetchall()

    def begin(self):
        """Begin transaction."""
        self.conn.begin()

    def commit(self):
        """Commit changes to stable storage"""
        self.conn.commit()

    def autocommit(self, b):
        self.conn_args['autocommit'] = b
        self.conn.autocommit(b)

    def get_autocommit(self):
        return self.conn.get_autocommit()

    def rollback(self):
        """Roll back the current transaction"""
        self.conn.rollback()

    def ping(self):
        """Check if the server is alive"""
        try:
            return self.conn.ping(False)
        except:
            return False

    def select_db(self, db):
        """Set current db"""
        self.conn.select_db(db)
        self.conn.db = db

    def __getattr__(self, table_name):
        """Returns a queryset"""
        if table_name.startswith('__'):
            raise AttributeError
        return QuerySet(self, table_name)

    def __getitem__(self, db_name):
        """Use other db"""
        p = ProxyConnection(self, db_name=db_name)
        return p


class MysqlPool:

    def __init__(self, *args, **kwargs):
        self.max_connections = kwargs.pop('max_connections', 0)
        self.args = args
        self.kwargs = kwargs
        self.connections = []
        self._lock = threading.Lock() # connecting lock

    def do_connect(self):
        for c in self.connections:
            if not c.locked:
                return c
        if self.full:
            return random.choice(self.connections)
        c = mysql_connect(*self.args, **self.kwargs)
        self.connections.append(c)
        return c

    def connect(self):
        self._lock.acquire()
        try:
            return self.do_connect()
        finally:
            self._lock.release()

    c = property(connect)

    @property
    def last_query(self):
        return PyMysqlConnection._last_query

    def size(self):
        return len(self.connections)

    @property
    def full(self):
        return len(self.connections) >= self.max_connections > 0


class QuerySet:

    def __init__(self, conn, table_name, db_name=''):
        "conn: a Connection object"
        self.conn = conn
        self.db_name = db_name
        self.table_name = "%s.%s" % (db_name, table_name) if db_name else table_name
        self.select_list = []
        self.cond_list = []
        self.cond_dict = {}
        self.order_list = []
        self.group_list = []
        self.having = ''
        self.limits = []
        self.row_style = 0 # Element type, 0:dict, 1:2d list 2:flat list
        self._result = None
        self._exists = None
        self._count  = None

    def escape(self, value):
        return self.conn.escape(value)

    def literal(self, value):
        return self.conn.literal(value)

    def make_select(self, fields):
        if not fields:
            return '*'
        return ','.join(fields)

    def make_expr(self, key, v):
        "filter expression"
        row = key.split(LOOKUP_SEP, 1)
        field = row[0]
        op = row[1] if len(row)>1 else ''
        if not op:
            if v is None:
                return field + ' is null'
            else:
                return field + '=' + self.literal(v)
        if op == 'gt':
            return field + '>' + self.literal(v)
        elif op == 'gte':
            return field + '>=' + self.literal(v)
        elif op == 'lt':
            return field + '<' + self.literal(v)
        elif op == 'lte':
            return field + '<=' + self.literal(v)
        elif op == 'ne':
            if v is None:
                return field + ' is not null'
            else:
                return field + '!=' + self.literal(v)
        elif op == 'in':
            if not v:
                return '0'
            return field + ' in ' + self.literal(v)
        elif op == 'startswith':
            return field + ' like ' + "'%s%%%%'" % escape_string(str(v))
        elif op == 'endswith':
            return field + ' like ' + "'%%%%%s'" % escape_string(str(v))
        elif op == 'contains':
            return field + ' like ' + "'%%%%%s%%%%'" % escape_string(str(v))
        elif op == 'range':
            return field + ' between ' + "%s and %s" % (self.literal(v[0]), self.literal(v[1]))
        return key + '=' + self.literal(v)

    def make_where(self, args, kw):
        # field loopup
        a = ' and '.join('(%s)'%v for v in args)
        b_list = [self.make_expr(k, v) for k,v in kw.iteritems()]
        b_list = [s for s in b_list if s]
        b = ' and '.join(b_list)
        if a and b:
            s = a + ' and ' + b
        elif a:
            s = a
        elif b:
            s = b
        else:
            s = ''
        return "where %s" % s if s else ''

    def make_order_by(self, fields):
        if not fields:
            return ''
        real_fields = []
        for f in fields:
            if f == '?':
                f = 'rand()'
            elif f.startswith('-'):
                f = f[1:] + ' desc'
            real_fields.append(f)
        return 'order by ' + ','.join(real_fields)

    def reverse_order_list(self):
        if not self.order_list:
            self.order_list = ['-id']
        else:
            orders = []
            for s in self.order_list:
                if s == '?':
                    pass
                elif s.startswith('-'):
                    s = s[1:]
                else:
                    s = '-' + s
                orders.append(s)
            self.order_list = orders

    def make_group_by(self, fields):
        if not fields:
            return ''
        having = ' having %s'%self.having if self.having else ''
        return 'group by ' + ','.join(fields) + having

    def make_limit(self, limits):
        if not limits:
            return ''
        start, stop = limits
        if not stop:
            return ''
        if not start:
            return 'limit %s' % stop
        return 'limit %s, %s' % (start, stop-start)

    def make_query(self, select_list=None, cond_list=None, cond_dict=None,
                   group_list=None, order_list=None, limits=None):
        if select_list is None:
            select_list = self.select_list
        if cond_list is None:
            cond_list = self.cond_list
        if cond_dict is None:
            cond_dict = self.cond_dict
        if order_list is None:
            order_list = self.order_list
        if group_list is None:
            group_list = self.group_list
        if limits is None:
            limits = self.limits
        select = self.make_select(select_list)
        cond = self.make_where(cond_list, cond_dict)
        order = self.make_order_by(order_list)
        group = self.make_group_by(group_list)
        limit = self.make_limit(limits)
        sql = "select %s from %s %s %s %s %s" % (select, self.table_name, cond, group, order, limit)
        return sql

    @property
    def sql(self):
        return self.make_query()

    def flush(self):
        if self._result:
            return self._result
        sql = self.make_query()
        if self.row_style == 1:
            self._result = self.conn.fetchall(sql)
        elif self.row_style == 2:
            rows = self.conn.fetchall(sql)
            vals = []
            for row in rows:
                vals += row
            self._result = vals
        else:
            self._result = self.conn.fetchall_dict(sql)
        return self._result

    def clone(self):
        new = copy.copy(self)
        new._result = None
        new._exists = None
        new._count  = None
        return new

    def group_by(self, *fields, **kw):
        q = self.clone()
        q.group_list += fields
        q.having = kw.get('having') or ''
        return q

    def order_by(self, *fields):
        q = self.clone()
        q.order_list = fields
        return q

    def select(self, *fields):
        q = self.clone()
        q.row_style = 0
        if fields:
            q.select_list = fields
        return q

    def values(self, *fields):
        q = self.clone()
        q.row_style = 1
        if fields:
            q.select_list = fields
        return q

    def flat(self, *fields):
        q = self.clone()
        q.row_style = 2
        if fields:
            q.select_list = fields
        return q

    def get(self, *args, **kw):
        cond_dict = dict(self.cond_dict)
        cond_dict.update(kw)
        cond_list = self.cond_list + list(args)
        sql = self.make_query(cond_list=cond_list, cond_dict=cond_dict, limits=(None,1))
        if self.row_style == 1:
            return self.conn.fetchone(sql)
        else:
            return self.conn.fetchone_dict(sql)

    def filter(self, *args, **kw):
        q = self.clone()
        q.cond_dict.update(kw)
        q.cond_list += args
        return q

    def first(self):
        return self[0]

    def last(self):
        return self[-1]

    def create(self, ignore=False, **kw):
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        ignore_s = ' IGNORE' if ignore else ''
        sql = "insert%s into %s (%s) values (%s)" % (ignore_s, self.table_name, fields, tokens)
        _, lastid = self.conn.execute(sql, kw.values())
        return lastid

    def bulk_create(self, obj_list, ignore=False):
        "Returns affectrows"
        if not obj_list:
            return
        kw = obj_list[0]
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        ignore_s = ' IGNORE' if ignore else ''
        sql = "insert%s into %s (%s) values (%s)" % (ignore_s, self.table_name, fields, tokens)
        args = [o.values() for o in obj_list]
        return self.conn.execute_many(sql, args)

    def count(self):
        if self._count is not None:
            return self._count
        if self._result is not None:
            return len(self._result)
        sql = self.make_query(select_list=['count(*) n'], order_list=[], limits=[None,1])
        row = self.conn.fetchone(sql)
        n = row[0] if row else 0
        self._count = n
        return n

    def exists(self):
        if self._result is not None:
            return True
        if self._exists is not None:
            return self._exists
        sql = self.make_query(select_list=['1'], order_list=[], limits=[None,1])
        row = self.conn.fetchone(sql)
        b = bool(row)
        self._exists = b
        return b

    def make_update_fields(self, kw):
        return ','.join('%s=%s'%(k,self.literal(v)) for k,v in kw.iteritems())

    def update(self, **kw):
        "return affected rows"
        if not kw:
            return 0
        cond = self.make_where(self.cond_list, self.cond_dict)
        update_fields = self.make_update_fields(kw)
        sql = "update %s set %s %s" % (self.table_name, update_fields, cond)
        n, _ = self.conn.execute(sql)
        return n

    def delete(self, *names):
        "return affected rows"
        cond = self.make_where(self.cond_list, self.cond_dict)
        limit = self.make_limit(self.limits)
        d_names = ','.join(names)
        sql = "delete %s from %s %s %s" % (d_names, self.table_name, cond, limit)
        n, _ = self.conn.execute(sql)
        return n

    def __iter__(self):
        rows = self.flush()
        return iter(rows)

    def __len__(self):
        return self.count()

    def __getitem__(self, k):
        if self._result is not None:
            return self._result.__getitem__(k)
        q = self.clone()
        if isinstance(k, (int, long)):
            if k < 0:
                k = -k - 1
                q.reverse_order_list()
            q.limits = [k, k+1]
            rows = q.flush()
            return rows[0] if rows else None
        elif isinstance(k, slice):
            start = None if k.start is None else int(k.start)
            stop = None if k.stop is None else int(k.stop)
            assert k.step is None, 'Slice step is not supported.'
            if stop == sys.maxint:
                stop = None
            if start is not None and stop is None:
                stop = len(self)
            q.limits = [start, stop]
            return q.flush()

    def __bool__(self):
        return self.exists()

    def __nonzero__(self):      # Python 2 compatibility
        return self.exists()
