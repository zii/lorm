#coding: utf-8
"A light weight python ORM"

import umysql
import copy
import re
import sys
from datetime import datetime
import time


__version__ = '0.1.8'
__all__ = [
    'mysql_connect',
    'Struct',
    'MysqlConnection',
    'escape',
    'literal',
    'QuerySet',
]

LOOKUP_SEP = '__'
RECONNECT_INTERVAL = 5

# Regular expression for executemany.
# From MySQLdb's source code.
restr = r"""
    \s
    values
    \s*
    (
        \(
            [^()']*
            (?:
                (?:
                        (?:\(
                            # ( - editor hightlighting helper
                            .*
                        \))
                    |
                        '
                            [^\\']*
                            (?:\\.[^\\']*)*
                        '
                )
                [^()']*
            )*
        \)
    )
"""

insert_values = re.compile(restr, re.S | re.I | re.X)

RE_JOIN_ALIAS = re.compile(r'^(.+?)\..+?\s*=\s*(.+?)\.')


def mysql_connect(*args, **kwargs):
    c = MysqlConnection()
    c.connect(*args, **kwargs)
    return c


class Struct(dict):
    """
    Dict to object. e.g.:
    >>> o = Struct({'a':1})
    >>> o.a
    >>> 1
    >>> o.b
    >>> None
    """
    def __init__(self, dictobj={}):
        self.update(dictobj)

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


class MysqlConnection:
    
    def __init__(self, auto_reconnect=1):
        self.conn = None
        self.conn_args = {}
        self.auto_reconnect = auto_reconnect
    
    def connect(self, host='', port=3306, username='', password='', datebase='', autocommit=1):
        c = umysql.Connection()
        charset = 'utf8'
        c.connect(host, port, username, password, datebase, autocommit, charset)
        self.conn = c
        self.conn_args = (host, port, username, password, datebase, autocommit, charset)
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def reconnect(self):
        while 1:
            #print 'reconnecting..'
            self.close()
            c = umysql.Connection()
            try:
                c.connect(*self.conn_args)
            except:
                pass
            else:
                self.conn = c
                #print 'reconnected.'
                break
            time.sleep(RECONNECT_INTERVAL)
    
    def ping(self):
        if not self.conn:
            return False
        try:
            print 'ping'
            r = self.conn.query("select 1")
            return True
        except:
            return False
        
    def query(self, sql, args=()):
        while 1:
            try:
                return self.conn.query(sql, args)
            except umysql.SQLError:
                raise
            except:
                if not self.auto_reconnect or self.ping():
                    raise
                self.reconnect()
        
    def fetchall(self, sql, args=()):
        r = self.query(sql, args)
        return r.rows
    
    def fetchone(self, sql, args=()):
        r = self.query(sql, args)
        return r.rows[0] if r.rows else None
    
    def fetchall_dict(self, sql, args=()):
        r = self.query(sql, args)
        fields = [f[0] for f in r.fields]
        rows = [Struct(zip(fields, row)) for row in r.rows]
        return rows
    
    def fetchone_dict(self, sql, args=()):
        r = self.query(sql, args)
        if not r.rows:
            return
        fields = [f[0] for f in r.fields]
        return Struct(zip(fields, r.rows[0]))
    
    def execute(self, sql, args=()):
        """
        Returns affected rows and lastrowid.
        """
        return self.query(sql, args)
    
    def execute_many(self, sql, args=()):
        """
        Execute a multi-row query.
        
        query -- string, query to execute on server

        args

            Sequence of sequences or mappings, parameters to use with
            query.
            
        Returns long integer rows affected, if any.
        
        This method improves performance on multiple-row INSERT and
        REPLACE. Otherwise it is equivalent to looping over args with
        execute().
        """
        m = insert_values.search(sql)
        if not m:
            affected = 0
            for arg in args:
                r = self.execute(sql, arg)
                affected += r[0]
            return affected, 0
        p = m.start(1)
        e = m.end(1)
        qv = m.group(1)
        values = []
        for arg in args:
            arg = [literal(s) for s in arg]
            v = qv % tuple(arg)
            values.append(v)
        sql = sql[:p] + ','.join(values) + sql[e:]
        return self.execute(sql)
    
    def __getattr__(self, table_name):
        "return a queryset"
        if table_name.startswith('__'):
            raise AttributeError
        return QuerySet(self, table_name)


def escape(s):
    "From pymysql's source code."
    s = str(s)
    assert isinstance(s, (bytes, bytearray))
    s = s.replace('\\', '\\\\')
    s = s.replace('\0', '\\0')
    s = s.replace('\n', '\\n')
    s = s.replace('\r', '\\r')
    s = s.replace('\032', '\\Z')
    s = s.replace("'", "\\'")
    s = s.replace('"', '\\"')
    return s

def literal(o):
    if o is None:
        return 'null'
    elif isinstance(o, (int, long, float)):
        return str(o)
    elif isinstance(o, (tuple, list)):
        return '(' + ','.join(literal(s) for s in o) + ')'
    elif isinstance(o, datetime):
        return "'" + o.strftime('%Y-%m-%d %H:%M:%S') + "'"
    s = str(o)
    return "'" + escape(s) + "'"

def make_expr(key, v):
    "filter expression"
    row = key.split(LOOKUP_SEP, 1)
    field = row[0]
    op = row[1] if len(row)>1 else ''
    if not op:
        if v is None:
            return field + ' is null'
        else:
            return field + '=' + literal(v)
    if op == 'gt':
        return field + '>' + literal(v)
    elif op == 'gte':
        return field + '>=' + literal(v)
    elif op == 'lt':
        return field + '<' + literal(v)
    elif op == 'lte':
        return field + '<=' + literal(v)
    elif op == 'ne':
        if v is None:
            return field + ' is not null'
        else:
            return field + '!=' + literal(v)
    elif op == 'in':
        return field + ' in ' + literal(v)
    elif op == 'startswith':
        return field + ' like ' + "'%s%%%%'" % escape(v)
    elif op == 'istartswith':
        return field + ' ilike ' + "'%s%%%%'" % escape(v)
    elif op == 'endswith':
        return field + ' like ' + "'%%%%%s'" % escape(v)
    elif op == 'iendswith':
        return field + ' ilike ' + "'%%%%%s'" % escape(v)
    elif op == 'contains':
        return field + ' like ' + "'%%%%%s%%%%'" % escape(v)
    elif op == 'icontains':
        return field + ' ilike ' + "'%%%%%s%%%%'" % escape(v)
    elif op == 'range':
        return field + ' between ' + "%s and %s" % (literal(v[0]), literal(v[1]))
    return key + '=' + literal(v)


class QuerySet:
    
    def __init__(self, conn, table_name):
        self.conn = conn
        self.tables = [table_name]
        self.aliases = {}
        self.join_list = []
        self.select_list = []
        self.cond_list = []
        self.cond_dict = {}
        self.order_list = []
        self.group_list = []
        self.limits = []
        self._result = None
    
    def make_select(self, fields):
        if not fields:
            return '*'
        return ','.join(fields)
    
    def make_where(self, args, kw):
        # field loopup
        a = ' and '.join('(%s)'%v for v in args)
        b = ' and '.join(make_expr(k, v) for k,v in kw.iteritems())
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
        return 'group by ' + ','.join(fields)
    
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
        sql = "select %s from %s %s %s %s %s %s" % (select, table_name, cond, join, group, order, limit)
        print '[debug]', sql
        return sql
    
    @property
    def query(self):
        return self.make_query()
    
    def rows(self, start=None, n=None):
        if n:
            self.limits = [start, (start or 0)+n]
        sql = self.query
        return self.conn.fetchall(sql)
    
    def flush(self):
        if self._result:
            return self._result
        sql = self.make_query()
        self._result = self.conn.fetchall_dict(sql)
        return self._result
    
    def clone(self):
        return copy.copy(self)
    
    def group_by(self, *fields):
        q = self.clone()
        q.group_list += fields
        return q
    
    def order_by(self, *fields):
        q = self.clone()
        q.order_list = fields
        return q

    def select(self, *fields):
        q = self.clone()
        q.select_list = fields
        return q
    
    def get(self, *args, **kw):
        cond_dict = dict(self.cond_dict)
        cond_dict.update(kw)
        cond_list = self.cond_list + list(args)
        sql = self.make_query(cond_list=cond_list, cond_dict=cond_dict, limits=(None,1))
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
        self.select_list = ['count(*)']
        rows = self.rows()
        return rows[0][0] if rows else 0
    
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


if __name__ == '__main__':

    #c = mysql_connect('192.168.0.130', 3306, 'dba_user', 'tbkt123456', 'tbkt')
    c = mysql_connect('121.40.85.144', 3306, 'root', 'aa131415', 'crawler')
    
    #c.goods.filter(id=3).delete()
    #print c.goods.join('search_keywords', "s.keyword=g.keyword").select('g.title', 's.max_price')[2:4]
    #print c.goods.rjoin('goods', "g2.keyword=g1.keyword").select('g1.id', 'g2.id')[:2]
    #print c.goods.rows(0,2)
    #print c.goods.get(id=1)
    #print c.auth_user.get(id=1)
    #print c.auth_user[0]
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
    #print c.auth_user.filter(id=1).rows()
    #print c.execute_many("insert into word2 (text, phoneticy) values (%s, %s)", (('cat2', 'xxx'), ('cat3', 'xxx'),))
    #word = {"text":"cat4", "phoneticy":"dd"}
    #c.word2.bulk_create([word]*2)
    #print c.u_task.group_by('type').select('type', 'count(*) n').rows()
    #print c.auth_user.filter(id__gt=1).first()
    #print c.auth_user.filter(id__in=(1,378364))[:]
    #print c.auth_user.filter(date_joined__in=('2009-08-24 17:26:26', '2012-06-13 11:48:39'))[:]
    #print c.auth_user.filter("id=-1 or id>3", is_active=1)[:2]
    #print c.auth_user.filter(username__icontains='000js')[0]
    #start = datetime(2016,1,1)
    #end = datetime(2016,5,5)
    #print c.auth_user.filter(last_login__range=[start, end])[:2]
    #print c.auth_user.filter(id__ne=None)[0] # is not null
    