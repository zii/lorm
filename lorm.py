#coding: utf-8
"A light weight python ORM without models."
import copy
import re
import sys
import time
import threading

import pymysql
from pymysql.connections import Connection as BaseConnection


__version__ = '0.2.0'
__all__ = [
    'mysql_connect',
    'Struct',
    'MysqlConnection',
    'MysqlPool',
    'SQLError',
    'QuerySet',
]

LOOKUP_SEP = '__'

RE_JOIN_ALIAS = re.compile(r'^(.+?)\..+?\s*=\s*(.+?)\.')


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
    c = MysqlConnection()
    c.connect(*args, **kwargs)
    return c


class SQLError(Exception):
    pass


class PyMysqlConnection(BaseConnection):
    
    def __init__(self, *args, **kwargs):
        self.auto_reconnect = kwargs.get('auto_reconnect', False)
        kwargs.pop('auto_reconnect', None)
        self.lock = threading.Lock()
        self.last_query = ''
        super(PyMysqlConnection, self).__init__(*args, **kwargs)
        
    def reconnect(self):
        delay = 1
        while 1:
            #print 'reconnecting..'
            if self._sock is not None:
                self.close()
            try:
                self.connect()
                break
            except:
                pass
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
                self.last_query = sql
                return super(PyMysqlConnection, self).query(sql, unbuffered)
            except pymysql.err.ProgrammingError, e:
                raise SQLError(e)
            except:
                if not self.auto_reconnect or self.safe_ping():
                    raise
                self.reconnect()
    
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
    
    def connect(self, host='', port=3306, username='', password='', database='', 
                autocommit=True, charset='utf8', autoreconnect=True):
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
    
    @property
    def locked(self):
        return self.conn.locked if self.conn else False
    
    @property
    def last_query(self):
        return self.conn.last_query if self.conn else ''
    
    @property
    def charset(self):
        return self.conn.charset if self.conn else 'utf8'
    
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
        Execute a multi-row query.
        """
        with self.conn.cursor() as cursor:
            cursor.executemany(sql, args)
    
    def callproc(self, procname, *args):
        "Execute stored procedure procname with args, returns result rows"
        with self.conn.cursor() as cursor:
            cursor.callproc(procname, args)
            return cursor.fetchall()
    
    def __getattr__(self, table_name):
        "return a queryset"
        if table_name.startswith('__'):
            raise AttributeError
        return QuerySet(self, table_name)

    def __getitem__(self, db_name):
        "set new db"
        p = ProxyConnection(self, db_name=db_name)
        return p


class MysqlPool:
    
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.connections = []
        self.last_conn = None
    
    def connect(self):
        r = None
        for c in self.connections:
            if not c.locked:
                r = c
                break
        else:
            c = mysql_connect(*self.args, **self.kwargs)
            self.connections.append(c)
            r = c
        self.last_conn = r
        return r
    
    def size(self):
        return len(self.connections)
    
    @property
    def last_query(self):
        return self.last_conn.last_query if self.last_conn else ''
    
    def fetchall(self, sql, args=()):
        c = self.connect()
        return c.fetchall(sql, args)
    
    def fetchone(self, sql, args=()):
        c = self.connect()
        return c.fetchone(sql, args)
    
    def fetchall_dict(self, sql, args=()):
        c = self.connect()
        return c.fetchall_dict(sql, args)
    
    def fetchone_dict(self, sql, args=()):
        c = self.connect()
        return c.fetchone_dict(sql, args)
    
    def execute(self, sql, args=()):
        c = self.connect()
        return c.execute(sql, args)
    
    def execute_many(self, sql, args=()):
        c = self.connect()
        return c.execute_many(sql, args)
    
    def callproc(self, procname, *args):
        "Execute stored procedure procname with args, returns cursor"
        c = self.connect()
        return c.callproc(procname, *args)
    
    def __len__(self):
        return len(self.connections)
    
    def __getattr__(self, table_name):
        "return a queryset"
        if table_name.startswith('__'):
            raise AttributeError
        c = self.connect()
        return QuerySet(c, table_name)

    def __getitem__(self, db_name):
        "set new db"
        c = self.connect()
        p = ProxyConnection(c, db_name=db_name)
        return p


def make_tablename(db_name, table_name):
    return "%s.%s" % (db_name, table_name) if db_name else table_name

    
class QuerySet:
    
    def __init__(self, conn, table_name, db_name=''):
        "conn: a Connection object"
        self.conn = conn
        self.db_name = db_name
        table_name = make_tablename(db_name, table_name)
        self.tables = [table_name]
        self.aliases = {}
        self.join_list = []
        self.select_list = []
        self.cond_list = []
        self.cond_dict = {}
        self.order_list = []
        self.group_list = []
        self.having = ''
        self.limits = []
        self.row_style = 0 # Element type, 0:dict, 1:list
        self._result = None
        self._exists = None
    
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
            return field + ' in ' + self.literal(v)
        elif op == 'startswith':
            return field + ' like ' + "'%s%%%%'" % self.escape(v)
        elif op == 'endswith':
            return field + ' like ' + "'%%%%%s'" % self.escape(v)
        elif op == 'contains':
            return field + ' like ' + "'%%%%%s%%%%'" % self.escape(v)
        elif op == 'range':
            return field + ' between ' + "%s and %s" % (self.literal(v[0]), self.literal(v[1]))
        return key + '=' + self.literal(v)
    
    def make_where(self, args, kw):
        # field loopup
        a = ' and '.join('(%s)'%v for v in args)
        b = ' and '.join(self.make_expr(k, v) for k,v in kw.iteritems())
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
    
    def make_join(self, join_list):
        if not join_list:
            return ''
        return '\n '.join(join_list)
    
    def make_query(self, select_list=None, cond_list=None, cond_dict=None, 
                   join_list=None, group_list=None, order_list=None, limits=None):
        select = self.make_select(select_list or self.select_list)
        cond = self.make_where(cond_list or self.cond_list, cond_dict or self.cond_dict)
        order = self.make_order_by(order_list or self.order_list)
        group = self.make_group_by(group_list or self.group_list)
        limit = self.make_limit(limits or self.limits)
        join = self.make_join(join_list or self.join_list)
        table_name = self.tables[0]
        alias = self.aliases.get(table_name) or ''
        if alias:
            table_name += ' ' + alias
        sql = "select %s from %s %s %s %s %s %s" % (select, table_name, join, cond, group, order, limit)
        return sql
    
    @property
    def query(self):
        return self.make_query()

    def flush(self):
        if self._result:
            return self._result
        sql = self.make_query()
        if self.row_style == 1:
            self._result = self.conn.fetchall(sql)
        else:
            self._result = self.conn.fetchall_dict(sql)
        return self._result
    
    def clone(self):
        return copy.copy(self)
    
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
        q.select_list = fields
        return q

    def rows(self):
        q = self.clone()
        q.row_style = 1
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
    
    def delete(self):
        cond = self.make_where(self.cond_list, self.cond_dict)
        sql = "delete from %s %s" % (self.tables[0], cond)
        return self.conn.execute(sql)
    
    def create(self, **kw):
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        sql = "insert into %s (%s) values (%s)" % (self.tables[0], fields, tokens)
        _, lastid = self.conn.execute(sql, kw.values())
        return lastid
    
    def bulk_create(self, obj_list):
        "Returns (affectrows, first_insert_id)"
        if not obj_list:
            return
        kw = obj_list[0]
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        sql = "insert into %s (%s) values (%s)" % (self.tables[0], fields, tokens)
        args = [o.values() for o in obj_list]
        return self.conn.execute_many(sql, args)
    
    def count(self):
        sql = self.make_query(select_list=['count(*) n'])
        row = self.conn.fetchone(sql)
        return row[0] if row else 0
    
    def exists(self):
        if self._exists is not None:
            return self._exists
        sql = self.make_query(select_list=['1'], limits=[None,1])
        row = self.conn.fetchone(sql)
        b = bool(row)
        self._exists = b
        return b
    
    def allot_alias(self, names):
        "allocate alias to tables in sequence"
        names = [s for s in names if s not in self.aliases.values()]
        names = reversed(names)
        for name in names:
            for t in self.tables:
                if t not in self.aliases:
                    self.aliases[t] = name
                    break
    
    def join(self, table_name, cond, op='inner'):
        "cond: a.id=b.id, 这里a必须是table_name的别名, 也就是说新加入的表的别名必须写在前面."
        m = RE_JOIN_ALIAS.search(cond)
        assert m, "Can't recognize table aliases."
        aliases = m.groups()
        q = self.clone()
        if table_name.find('.') < 0:
            table_name = make_tablename(self.db_name, table_name)
        q.tables.append(table_name)
        q.allot_alias(aliases)
        alias = aliases[0]
        sql = "%s join %s %s on %s" % (op, table_name, alias, cond)
        q.join_list.append(sql)
        return q
    
    def ljoin(self, table_name, cond):
        return self.join(table_name, cond, 'left')
    
    def rjoin(self, table_name, cond):
        return self.join(table_name, cond, 'right')
    
    def __iter__(self):
        rows = self.flush()
        return iter(rows)
    
    def __len__(self):
        rows = self.flush()
        return len(rows)

    def __getitem__(self, k):
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
            if stop == sys.maxint:
                stop = None
            q.limits = [start, stop]
            return q.flush()

    def __bool__(self):
        return self.exists()
    
    def __nonzero__(self):      # Python 2 compatibility
        return self.exists()
    

if __name__ == '__main__':
    "test"
    #c = mysql_connect('192.168.0.130', 3306, 'dba_user', 'tbkt123456', 'tbkt')
    #c = mysql_connect('121.40.85.144', 3306, 'root', 'aa131415', 'crawler')
    c = MysqlPool('121.40.85.144', 3306, 'root', 'aa131415', 'crawler', charset='utf8', autocommit=True, autoreconnect=1)
    
    #print c['crawler'].goods.rows()[0]
    #print c.goods.get(id=1)
    #import datetime
    #print c.goods.filter(add_time=datetime.datetime(2016, 8, 12, 10, 48, 29)).first()
    #print c.goods.filter(id__in=[1,2,3,4])[:]
    #print c.goods.count()
    #print c.fetchall("select * from goods2 limit 2")
    #print c.auth_user.get(id=1)
    #print c.auth_user[0]
    #print c.auth_user.filter(id=-1).exists()
    #if c.auth_user.filter(id=1):
    #    print 'exists'
    #print c['ziyuan_new'].yy_question.select('id', 'number')[-1]
    #print c.auth_user[1:3]
    #print c.auth_user.filter(username="1'356'5422119js").first()
    #print c.auth_user.order_by('-id').select('id', 'username').last()
    #print c.auth_user.count()
    #print c.auth_user.select('count(*) n', 'id')[0]
    #print c.tmp_id[:]
    #print c.tmp_id.order_by('?').first()
    #print c.auth_user.order_by('-id').get(is_active=1)
    #print c.auth_user[-727011]
    #print c.auth_user.filter(is_active=1).order_by('-id').query
    #print c.word2.filter(id=3).delete()
    #sql = "insert into word2 set text=%s" % literal("c'a't")
    #print c.execute(sql)
    #print c.word2.create(text="x'x'yy", phoneticy='a', phoneticm='b')
    #print list(c.tmp_id.order_by('-id'))
    #print len(c.tmp_id)
    #print c.auth_user.filter(id=1).rows()[:2]
    #print c.execute_many("insert into word2 (text, phoneticy) values (%s, %s)", (('cat2', 'xxx'), ('cat3', 'xxx'),))
    #word = {"text":"cat4", "phoneticy":"dd"}
    #c.word2.bulk_create([word]*2)
    #print c.u_task.group_by('type', having='n>100').select('type', 'count(*) n').rows()[:]
    #print c.auth_user.filter(id__gt=1).first()
    #print c.auth_user.filter(id__in=(1,378364))[:]
    #print c.auth_user.filter(date_joined__in=('2009-08-24 17:26:26', '2012-06-13 11:48:39'))[:]
    #print c.auth_user.filter("id=-1 or id>3", is_active=1)[:2]
    #print c.last_query
    #print c.auth_user.filter(username__contains='000js')[0]
    #start = datetime(2016,1,1)
    #end = datetime(2016,5,5)
    #print c.auth_user.filter(last_login__range=[start, end])[:2]
    #print c.auth_user.filter(id__ne=None)[0] # is not null
    #c.goods.filter(id=3).delete()
    #print c.goods.join('search_keywords', "s.keyword=g.keyword").select('g.title', 's.max_price')[2:5]
    #print c.goods.rjoin('goods', "g2.keyword=g1.keyword").select('g1.id', 'g2.id')[:2]
    print c.last_query
    