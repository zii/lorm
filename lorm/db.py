#coding: utf-8
import datetime
import time
import copy
import sys
import logging
import threading

import mysql_pool

__all__ = [
    'Struct',
    'ConnectionProxy',
    'Hub',
]

class Struct(dict):
    """
    - 为字典加上点语法. 例如:
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


class ExecuteLock:
    def __init__(self, proxy):
        self.p = proxy
        self.c = proxy.connect()

    def __enter__(self):
        self.c._lock.acquire()
        return self.c

    def __exit__(self, exc, value, tb):
        self.c._lock.release()
        if not self.p.transacting and self.p.get_autocommit():
            self.p.close()


class ConnectionProxy:
    def __init__(self, creator):
        self.creator = creator
        self.c = None
        self.transacting = False

    def connect(self):
        if self.c:
            return self.c

        conn = self.creator()
        conn._lock = threading.Lock()
        self.c = conn
        return conn

    def close(self):
        if self.c:
            self.c.close()
            self.c = None

    @property
    def open(self):
        """return if connection alive"""
        return self.c is not None and self.c.open

    def character_set_name(self):
        return self.connect().character_set_name()

    def set_character_set(self, charset):
        return self.connect().set_character_set(charset)

    def literal(self, s):
        return self.connect().literal(s)

    def escape_string(self, s):
        return self.connect().escape_string(s)

    def get_autocommit(self):
        return self.connect().get_autocommit()

    def autocommit(self, on):
        return self.connect().autocommit(on)

    def query(self, command):
        return self.connect().query(command)

    def begin(self):
        return self.query("BEGIN")

    def commit(self):
        assert self.c, 'Need connect before commit!'
        self.c.commit()

    def rollback(self):
        assert self.c, 'Need connect before rollback!'
        self.c.rollback()

    def fetchall(self, sql, args=None):
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.execute(sql, args)
            rows = cursor.fetchall()
            cursor.close()
        return rows

    def fetchone(self, sql, args=None):
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.execute(sql, args)
            row = cursor.fetchone()
            cursor.close()
        return row

    def fetchall_dict(self, sql, args=None):
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.execute(sql, args)
            fields = [r[0] for r in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
        return [Struct(zip(fields,row)) for row in rows]

    def fetchone_dict(self, sql, args=None):
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.execute(sql, args)
            row = cursor.fetchone()
            cursor.close()
        if not row:
            return
        fields = [r[0] for r in cursor.description]
        return Struct(zip(fields, row))

    def execute(self, sql, args=None):
        """
        Returns affected rows and lastrowid.
        """
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.execute(sql, args)
            cursor.close()
        return cursor.rowcount, cursor.lastrowid

    def execute_many(self, sql, args=None):
        """
        Execute a multi-row query. Returns affected rows.
        """
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            rows = cursor.executemany(sql, args)
            cursor.close()
        return rows

    def callproc(self, procname, *args):
        """Execute stored procedure procname with args, returns result rows"""
        with ExecuteLock(self) as c:
            cursor = c.cursor()
            cursor.callproc(procname, args)
            rows = cursor.fetchall()
            cursor.close()
        return rows

    def __enter__(self):
        """Begin a transaction"""
        self.transacting = True
        if self.get_autocommit():
            self.begin()
        return self

    def __exit__(self, exc, value, tb):
        """End a transaction"""
        try:
            if exc:
                self.rollback()
            else:
                self.commit()
        finally:
            self.transacting = False
            self.close()

    def __getattr__(self, table_name):
        return QuerySet(self, table_name)

    def __str__(self):
        return '<ConnectionProxy: %x>' % (id(self))


class Hub:
    """
    用法:

    >>> db = Hub()
    >>> db.add_db('default', host='', port=3306, user='', passwd='', db='', 
                    charset='utf8', autocommit=True, pool_size=8, wait_timeout=30)
    >>> db.default.auth_user.get(id=1)

    :param pool_size: 连接池容量
    :param wait_timeout: 连接最大保持时间(秒)
    """
    def __init__(self):
        self.pool_manager = mysql_pool.PoolManager()
        self.creators = {}

    def add_pool(self, alias, **connect_kwargs):
        def creator():
            return self.pool_manager.connect(**connect_kwargs)
        self.creators[alias] = creator

    def get_proxy(self, alias):
        creator = self.creators.get(alias)
        if creator:
            return ConnectionProxy(creator)

    def __getattr__(self, alias):
        """返回一个库的代理连接"""
        return self.get_proxy(alias)

    def __str__(self):
        return '<Hub: %s>' % id(self)


class QuerySet:

    LOOKUP_SEP = '__'

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

    def literal(self, value):
        if hasattr(value, '__iter__'):
            return '(' + ','.join(self.conn.literal(v) for v in value) + ')'
        return self.conn.literal(value)

    def escape_string(self, s):
        if isinstance(s, unicode):
            charset = self.conn.character_set_name()
            s = s.encode(charset)
        return self.conn.escape_string(s)

    def make_select(self, fields):
        if not fields:
            return '*'
        return ','.join(fields)

    def make_expr(self, key, v):
        "filter expression"
        row = key.split(self.LOOKUP_SEP, 1)
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
        elif op == 'ni':  # not in
            if not v:
                return '1'
            return field + ' not in ' + self.literal(v)
        elif op == 'startswith':
            return field + ' like ' + "'%s%%'" % self.escape_string(v)
        elif op == 'endswith':
            return field + ' like ' + "'%%%s'" % self.escape_string(v)
        elif op == 'contains':
            return field + ' like ' + "'%%%s%%'" % self.escape_string(v)
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
        return ', '.join('%s=%s'%(k,self.literal(v)) for k,v in kw.iteritems())

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
            if start and stop is None:
                stop = self.count()
            q.limits = [start, stop]
            return q.flush()

    def __bool__(self):
        return self.exists()

    def __nonzero__(self):      # Python 2 compatibility
        return self.exists()

    def wait(self, *args, **kw):
        "扩展: 重复读取从库直到有数据, 表示数据已同步"
        delays = [0, 0.2, 0.4, 0.8, 1.2, 1.4]
        for dt in delays:
            if dt > 0:
                time.sleep(dt)
            r = self.get(*args, **kw)
            if r:
                return r
        logging.warning('slave db sync timeout: %s' % self.table_name)
