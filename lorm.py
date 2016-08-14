#coding: utf-8
"A light python ORM"

import umysql
import copy
import re
from datetime import datetime


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


class Connection:
    
    def __init__(self):
        self.conn = None
    
    def connect(self, host, port, username, password, datebase, autocommit=1):
        c = umysql.Connection()
        c.connect(host, port, username, password, datebase, autocommit, 'utf8')
        self.conn = c
    
    @property
    def is_connected(self):
        return self.conn.is_connected if self.conn else False
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def fetchall(self, sql, args=()):
        r = self.conn.query(sql, args)
        return r.rows
    
    def fetchone(self, sql, args=()):
        r = self.conn.query(sql, args)
        return r.rows[0] if r.rows else None
    
    def fetchall_dict(self, sql, args=()):
        r = self.conn.query(sql, args)
        fields = [f[0] for f in r.fields]
        rows = [Struct(zip(fields, row)) for row in r.rows]
        return rows
    
    def fetchone_dict(self, sql, args=()):
        r = self.conn.query(sql, args)
        if not r.rows:
            return
        fields = [f[0] for f in r.fields]
        return Struct(zip(fields, r.rows[0]))
    
    def execute(self, sql, args=()):
        """
        Returns: rowcount, lastrowid
        """
        return self.conn.query(sql, args)
    
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
    return s.replace("'", "\\'")

def literal(o):
    if isinstance(o, (int, long, float)):
        return str(o)
    elif isinstance(o, datetime):
        return "'" + o.strftime('%Y-%m-%d %H:%M') + "'"
    s = str(o)
    return "'" + escape(s) + "'"

class QuerySet:
    
    def __init__(self, conn, table_name):
        self.conn = conn
        self.table_name = table_name
        self.select_list = []
        self.cond_dict = {}
        self.order_list = []
        self.limits = []
        self._result = None
    
    def make_select(self, fields):
        if not fields:
            return '*'
        return ','.join(fields)
    
    def make_where(self, kw):
        # TODO: logic
        s = ' and '.join('%s=%s'%(k,literal(v)) for k,v in kw.iteritems())
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
    
    def make_limit(self, limits):
        if not limits:
            return ''
        start, stop = limits
        if stop is None:
            return ''
        if limits[0] is None:
            return 'limit %s' % stop
        return 'limit %s, %s' % (start, stop-start)
    
    def make_query(self, select_list=None, cond_dict=None, order_list=None, limits=None):
        select = self.make_select(select_list or self.select_list)
        cond = self.make_where(cond_dict or self.cond_dict)
        order = self.make_order_by(order_list or self.order_list)
        limit = self.make_limit(limits or self.limits)
        sql = "select %s from %s %s %s %s" % (select, self.table_name, cond, order, limit)
        return sql
    
    @property
    def query(self):
        return self.make_query()
    
    @property
    def rows(self):
        sql = self.query
        return self.conn.fetchall(sql)
    
    def flush(self):
        if self._result:
            return self._result
        sql = self.make_query()
        #print '[debug]'+sql
        self._result = self.conn.fetchall_dict(sql)
        return self._result
    
    def clone(self):
        return copy.copy(self)
    
    def order_by(self, *fields):
        q = self.clone()
        q.order_list = fields
        return q

    def select(self, *fields):
        q = self.clone()
        q.select_list = fields
        return q
    
    def get(self, **kw):
        cond_dict = dict(self.cond_dict)
        cond_dict.update(kw)
        sql = self.make_query(cond_dict=cond_dict, limits=(None,1))
        return self.conn.fetchone_dict(sql)
    
    def filter(self, **kw):
        q = self.clone()
        q.cond_dict.update(kw)
        return q
    
    def first(self):
        return self[0]
    
    def last(self):
        return self[-1]
    
    def delete(self, **kw):
        cond = self.make_where(kw)
        sql = "delete from %s %s" % (self.table_name, cond)
        return self.conn.execute(sql)
    
    def create(self, **kw):
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        sql = "insert into %s (%s) values (%s)" % (self.table_name, fields, tokens)
        n, lastid = self.conn.execute(sql, kw.values())
        if lastid:
            return self.get(id=lastid)
    
    def bulk_create(self, obj_list):
        "Returns (affectrows, first_insert_id)"
        if not obj_list:
            return
        kw = obj_list[0]
        tokens = ','.join(['%s']*len(kw))
        fields = ','.join(kw.iterkeys())
        sql = "insert into %s (%s) values (%s)" % (self.table_name, fields, tokens)
        args = [o.values() for o in obj_list]
        return self.conn.execute_many(sql, args)
    
    def count(self):
        self.select_list = ['count(*)']
        rows = self.rows
        return rows[0][0] if rows else 0
    
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
            q.limits = [start, stop]
            return q.flush()


if __name__ == '__main__':
    c = Connection()
    c.connect('192.168.0.130', 3306, 'dba_user', 'tbkt123456', 'tbkt')

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
    #print c.word2.delete(id=3)
    #sql = "insert into word2 set text=%s" % literal("c'a't")
    #print c.execute(sql)
    #print c.word2.create(text="x'x'yy", phoneticy='a', phoneticm='b')
    #print list(c.tmp_id.order_by('-id'))
    #print len(c.tmp_id)
    #print c.auth_user.filter(id=1).rows
    #print c.execute_many("insert into word2 (text, phoneticy) values (%s, %s)", (('cat2', 'xxx'), ('cat3', 'xxx'),))
    #word = {"text":"cat4", "phoneticy":"dd"}
    #c.word2.bulk_create([word]*2)
    