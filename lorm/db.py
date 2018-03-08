#coding: utf-8
import sys
import datetime
import time
import copy
import sys
import logging
import threading

from . import mysql_pool

py3k = sys.version_info.major > 2

if py3k:
    IntType = int
else:
    IntType = (int, long)


__all__ = [
    'Struct',
    'ConnectionProxy',
    'Hub',
]

class Struct(dict):
    """
    Object-Dict

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


class Executer:
    def __init__(self, proxy):
        self.p = proxy
        self.c = proxy.connect()
        self.cursor = None

    def __enter__(self):
        self.c._lock.acquire()
        self.cursor = self.c.cursor()
        return self.cursor

    def __exit__(self, exc, value, tb):
        self.p.last_executed = getattr(self.cursor, '_last_executed', None)
        self.cursor.close()
        self.c._lock.release()
        if not self.p.transacting and self.p.get_autocommit():
            self.p.close()


class ConnectionProxy:
    def __init__(self, creator):
        self.creator = creator
        self.c = None
        self.transacting = False
        self.last_executed = None

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
        return self.query('BEGIN')

    def commit(self):
        assert self.c, 'Need connect before commit!'
        self.c.commit()

    def rollback(self):
        assert self.c, 'Need connect before rollback!'
        self.c.rollback()

    def fetchall(self, sql, *args):
        args = args or None
        with Executer(self) as cursor:
            cursor.execute(sql, args)
            rows = cursor.fetchall()
        return rows

    def fetchone(self, sql, *args):
        args = args or None
        with Executer(self) as cursor:
            cursor.execute(sql, args)
            row = cursor.fetchone()
        return row

    def fetchall_dict(self, sql, *args):
        args = args or None
        with Executer(self) as cursor:
            cursor.execute(sql, args)
            fields = [r[0] for r in cursor.description]
            rows = cursor.fetchall()
        return [Struct(zip(fields,row)) for row in rows]

    def fetchone_dict(self, sql, *args):
        args = args or None
        with Executer(self) as cursor:
            cursor.execute(sql, args)
            row = cursor.fetchone()
        if not row:
            return
        fields = [r[0] for r in cursor.description]
        return Struct(zip(fields, row))

    def execute(self, sql, *args):
        """
        Returns affected rows and lastrowid.
        """
        args = args or None
        with Executer(self) as cursor:
            cursor.execute(sql, args)
        return cursor.rowcount, cursor.lastrowid

    def execute_many(self, sql, args=None):
        """
        Execute a multi-row query. Returns affected rows.
        """
        args = args or None
        with Executer(self) as cursor:
            rows = cursor.executemany(sql, args)
        return rows

    def callproc(self, procname, *args):
        """Execute stored procedure procname with args, returns result rows"""
        with Executer(self) as cursor:
            cursor.callproc(procname, args)
            rows = cursor.fetchall()
        return rows

    def __enter__(self):
        """Begin a transaction"""
        self.transacting = True
        if self.get_autocommit():
            self.begin()
        self.c._transacting = True
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
            self.c._transacting = False
            self.close()

    def __getattr__(self, table_name):
        return QuerySet(self, table_name)

    def __getitem__(self, table_name):
        return QuerySet(self, table_name)

    def __str__(self):
        return "<ConnectionProxy: %x>" % (id(self))


class Hub:
    """
    Usage:

    >>> db = Hub(pymysql)
    >>> db.add_db('default', host='', port=3306, user='', passwd='', db='', 
                    charset='utf8', autocommit=True, pool_size=8, wait_timeout=30)
    >>> db.default.auth_user.get(id=1)

    :param driver: MySQLdb or pymysql
    """
    def __init__(self, driver):
        self.pool_manager = mysql_pool.PoolManager(driver)
        self.creators = {}

    def add_pool(self, alias, **connect_kwargs):
        """
        :param pool_size: (optional)Connection pool capacity
        :param wait_timeout: (optional)Maximum retention time (SEC)
        """
        def creator():
            # Timeout before throwing an exception when connecting. 
            # (default: 10, min: 1, max: 31536000)
            if 'connect_timeout' not in connect_kwargs:
                connect_kwargs['connect_timeout'] = 10
            return self.pool_manager.connect(**connect_kwargs)
        self.creators[alias] = creator

    def get_proxy(self, alias):
        creator = self.creators.get(alias)
        if creator:
            return ConnectionProxy(creator)

    def __getattr__(self, alias):
        return self.get_proxy(alias)

    def __getitem__(self, alias):
        return self.get_proxy(alias)

    def __str__(self):
        return "<Hub: {}>".format(id(self))


class QuerySet:

    LOOKUP_SEP = '__'

    def __init__(self, conn, table_name, db_name=''):
        "conn: a Connection object"
        self.conn = conn
        self.db_name = db_name
        self.table_name = u"{}.{}".format(db_name, table_name) if db_name else table_name
        self.select_list = []
        self.cond_list = []
        self.cond_dict = {}
        self.exclude_list = []
        self.exclude_dict = {}
        self.order_list = []
        self.group_list = []
        self.ondup_list = []
        self.ondup_dict = {}
        self.having = ''
        self.limits = []
        self.row_style = 0 # Element type, 0:dict, 1:2d list 2:flat list
        self._result = None

    def literal(self, object):
        return self.conn.literal(object)

    def escape_string(self, s):
        return self.conn.escape_string(s)

    def make_select(self, fields):
        if not fields:
            return u'*'
        return u','.join(fields)

    def make_expr(self, key, v):
        "filter expression"
        row = key.split(self.LOOKUP_SEP, 1)
        field = u"`{}`".format(row[0])
        op = row[1] if len(row)>1 else ''
        if not op:
            if v is None:
                return u"{} is null".format(field), []
            else:
                return u"{}=%s".format(field), [v] 
        if op == u'gt':
            return u"{}>%s".format(field), [v]
        elif op == u'gte':
            return u"{}>=%s".format(field), [v]
        elif op == u'lt':
            return u"{}<%s".format(field), [v]
        elif op == u'lte':
            return u"{}<=%s".format(field), [v]
        elif op == u'ne':
            if v is None:
                return u"{} is not null".format(field), []
            else:
                return u"{}!=%s".format(field), [v]
        elif op == u'in':
            if not v:
                return u'0', []
            return u"{} in %s".format(field), [v]
        elif op == u'ni':  # not in
            if not v:
                return u'1', []
            return u"{} not in %s".format(field), [v]
        elif op == u'startswith':
            v = u"{}%".format(v)
            return r"{} like %s".format(field), [v]
        elif op == u'endswith':
            v = u"%{}".format(v)
            return r"{} like %s".format(field), [v]
        elif op == u'contains':
            v = u"%{}%".format(v)
            return r"{} like %s".format(field), [v]
        elif op == u'range':
            return u"{} between %s and %s".format(field), [v[0], v[1]]
        return u"{}=%s".format(key), [v]

    def make_cond(self, args, kw):
        # field loopup
        a = u' and '.join(u"({})".format(s) for s in args)
        exprs = [self.make_expr(k, v) for k,v in kw.items()]
        b_list = [e[0] for e in exprs]
        vals = []
        for e in exprs:
            vals += e[1]
        b = u' and '.join(b_list)
        if a and b:
            s = a + u' and ' + b
        elif a:
            s = a
        elif b:
            s = b
        else:
            s = ''
        s = s or ''
        return s, vals

    def make_where(self, cond_list, cond_dict, exclude_list, exclude_dict):
        cond, cond_vals = self.make_cond(cond_list, cond_dict)
        exclude, ex_vals = self.make_cond(exclude_list, exclude_dict)
        vals = cond_vals + ex_vals
        if cond and exclude:
            return u"where {} and not ({})".format(cond, exclude), vals
        elif cond:
            return u"where {}".format(cond), vals
        elif exclude:
            return u"where not ({})".format(exclude), vals
        return '', []

    def make_order_by(self, fields):
        if not fields:
            return ''
        real_fields = []
        for f in fields:
            if f == u'?':
                f = u'rand()'
            elif f.startswith(u'-'):
                f = f[1:] + u' desc'
            real_fields.append(f)
        return u'order by ' + u','.join(real_fields)

    def reverse_order_list(self):
        if not self.order_list:
            self.order_list = [u'-id']
        else:
            orders = []
            for s in self.order_list:
                if s == u'?':
                    pass
                elif s.startswith(u'-'):
                    s = s[1:]
                else:
                    s = u'-' + s
                orders.append(s)
            self.order_list = orders

    def make_group_by(self, fields):
        if not fields:
            return ''
        having = u" having {}".format(self.having) if self.having else ''
        return u'group by ' + u','.join(fields) + having

    def make_limit(self, limits):
        if not limits:
            return ''
        start, stop = limits
        if not stop:
            return ''
        if not start:
            return u"limit {}".format(stop)
        return u"limit {}, {}".format(start, stop-start)

    def make_query(self, select_list=None, cond_list=None, cond_dict=None,
                   exclude_list=None, exclude_dict=None,
                   group_list=None, order_list=None, limits=None):
        if select_list is None:
            select_list = self.select_list
        if cond_list is None:
            cond_list = self.cond_list
        if cond_dict is None:
            cond_dict = self.cond_dict
        if exclude_list is None:
            exclude_list = self.exclude_list
        if exclude_dict is None:
            exclude_dict = self.exclude_dict
        if order_list is None:
            order_list = self.order_list
        if group_list is None:
            group_list = self.group_list
        if limits is None:
            limits = self.limits
        select = self.make_select(select_list)
        cond, cond_vals = self.make_where(cond_list, cond_dict, exclude_list, exclude_dict)
        order = self.make_order_by(order_list)
        group = self.make_group_by(group_list)
        limit = self.make_limit(limits)
        sql = u"select {} from {} {} {} {} {}".format(select, self.table_name, cond, group, order, limit)
        return sql, cond_vals

    @property
    def sql(self):
        return self.make_query()

    def flush(self):
        if self._result:
            return self._result
        sql, args = self.make_query()
        if self.row_style == 1:
            self._result = self.conn.fetchall(sql, *args)
        elif self.row_style == 2:
            rows = self.conn.fetchall(sql, *args)
            vals = []
            for row in rows:
                vals += row
            self._result = vals
        else:
            self._result = self.conn.fetchall_dict(sql, *args)
        return self._result

    def clone(self):
        new = copy.copy(self)
        new_dict = new.__dict__
        for k, v in self.__dict__.items():
            if isinstance(v, list):
                new_dict[k] = list(v)
            elif isinstance(v, dict):
                new_dict[k] = dict(v)
        new._result = None
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
        sql, vals = self.make_query(cond_list=cond_list, cond_dict=cond_dict, limits=(None,1))
        if self.row_style == 1:
            return self.conn.fetchone(sql, *vals)
        else:
            return self.conn.fetchone_dict(sql, *vals)

    def filter(self, *args, **kw):
        q = self.clone()
        q.cond_dict.update(kw)
        q.cond_list += args
        return q

    def exclude(self, *args, **kw):
        q = self.clone()
        q.exclude_dict.update(kw)
        q.exclude_list += args
        return q

    def first(self):
        return self[0]

    def last(self):
        return self[-1]

    def ondup(self, *args, **kw):
        """
        MySQL feature: INSERT...ON DUPLICATE KEY UPDATE...
        """
        q = self.clone()
        q.ondup_list = args
        q.ondup_dict = kw
        return q

    def create(self, ignore=False, **kw):
        "Returns lastrowid"
        tokens = u','.join([u'%s']*len(kw))
        fields = [u"`{}`".format(k) for k in kw.keys()]
        fields = u','.join(fields)
        ignore_s = u' IGNORE' if ignore else ''
        ondup_s = ''
        ondup_vals = []
        if self.ondup_list or self.ondup_dict:
            statement, ondup_vals = self.make_update_fields(self.ondup_list, self.ondup_dict)
            ondup_s = u' ON DUPLICATE KEY UPDATE ' + statement
        sql = u"insert{} into {} ({}) values ({}){}".format(ignore_s, self.table_name, fields, tokens, ondup_s)
        values = kw.values() + ondup_vals
        _, lastid = self.conn.execute(sql, *values)
        return lastid

    def bulk_create(self, obj_list, ignore=False):
        "Returns affectrows"
        if not obj_list:
            return
        kw = obj_list[0]
        tokens = u','.join(['%s']*len(kw))
        fields = [u"`{}`".format(k) for k in kw.keys()]
        fields = u','.join(fields)
        ignore_s = u' IGNORE' if ignore else ''
        ondup_s = ''
        ondup_vals = []
        if self.ondup_list or self.ondup_dict:
            update_fields, ondup_vals = self.make_update_fields(self.ondup_list, self.ondup_dict)
            ondup_s = u' ON DUPLICATE KEY UPDATE ' + update_fields
            sql = u"insert{} into {} ({}) values ({}){}".format(ignore_s, self.table_name, fields, tokens, ondup_s)
            affected_rows = 0
            for o in obj_list:
                vals = o.values() + ondup_vals
                n, _ = self.conn.execute(sql, *vals)
                affected_rows += n
            return affected_rows
        else:
            sql = u"insert{} into {} ({}) values ({})".format(ignore_s, self.table_name, fields, tokens)
            args = [o.values() for o in obj_list]
            return self.conn.execute_many(sql, args)

    def count(self):
        if self._result is not None:
            return len(self._result)
        sql, vals = self.make_query(select_list=[u'count(*) n'], order_list=[], limits=[None,1])
        row = self.conn.fetchone(sql, *vals)
        n = row[0] if row else 0
        return n

    def exists(self):
        if self._result is not None:
            return True
        sql, vals = self.make_query(select_list=[u'1'], order_list=[], limits=[None,1])
        row = self.conn.fetchone(sql, *vals)
        b = bool(row)
        return b

    def make_update_fields(self, args=[], kw={}):
        f1 = u', '.join(args)
        f2 = u', '.join(u"`{}`=%s".format(k) for k in kw.keys())
        if f1 and f2:
            return f1 + u', ' + f2, kw.values()
        elif f1:
            return f1, []
        return f2, kw.values()

    def update(self, *args, **kw):
        "return affected rows"
        if not args and not kw:
            return 0
        vals = []
        cond, cond_vals = self.make_where(self.cond_list, self.cond_dict, self.exclude_list, self.exclude_dict)
        update_fields, update_vals = self.make_update_fields(args, kw)
        vals = update_vals + cond_vals 
        sql = u"update {} set {} {}".format(self.table_name, update_fields, cond)
        n, _ = self.conn.execute(sql, *vals)
        return n

    def delete(self, *names):
        "return affected rows"
        cond, vals = self.make_where(self.cond_list, self.cond_dict, self.exclude_list, self.exclude_dict)
        limit = self.make_limit(self.limits)
        d_names = u','.join(names)
        sql = u"delete {} from {} {} {}".format(d_names, self.table_name, cond, limit)
        n, _ = self.conn.execute(sql, *vals)
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
        if isinstance(k, IntType):
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
            if start and stop is None:
                stop = self.count()
            q.limits = [start, stop]
            return q.flush()

    def __bool__(self):
        return self.exists()

    def __nonzero__(self):      # Python 2 compatibility
        return self.exists()
