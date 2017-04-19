# coding: utf-8
"Inspired by sqlalchemy/pool.py"
import time
import threading
import logging
import Queue
import types

# compatible with pymysql
try:
    import pymysql; pymysql.install_as_MySQLdb()
except:
    pass
import MySQLdb
from MySQLdb import Error
from MySQLdb.connections import Connection 


class TimeoutError(Exception):
    pass


class QueuePool:
    def __init__(self, creator, pool_size=5, timeout=2.0, recycle=None):
        """
        :param creator: 回调函数, 返回值为连接对象
        :param pool_size: 连接池大小, 最多保持几个连接
        :param timeout: 队列阻塞超时时间(秒), 为了防止大量突发连接造成(1040, 'Too many connections')
        :param recycle: 连接保持时间(秒), 不能超过mysql的wait_timeout.
                        查看wait_timeout的方法: show variables like 'wait_timeout'
        """
        self.creator = creator
        self.timeout = timeout
        self.recycle = recycle
        self.q = Queue.Queue(pool_size)
        self.cset = set()  # 保证队列成员不重复
        self.overflow = -pool_size
        self._overflow_lock = threading.Lock()

    def inc_overflow(self):
        with self._overflow_lock:
            if self.overflow < 0:
                self.overflow += 1
                return True
            else:
                return False

    def dec_overflow(self):
        with self._overflow_lock:
            self.overflow -= 1
            return True

    def create_connection(self):
        now = time.time()
        c = self.creator()
        c._pool = self
        c._activetime = now
        return c

    def close(self, conn):
        if not conn.open:
            return
        del conn._pool
        try:
            conn._close()
        finally:
            self.dec_overflow()

    def connect(self):
        block = False
        try:
            while 1:
                block = self.overflow >= 0
                c = self.q.get(block, self.timeout)
                if c in self.cset:
                    self.cset.remove(c)
                now = time.time()
                if self.recycle is not None and now - c._activetime >= self.recycle:
                    self.close(c)
                else:
                    #c._activetime = now
                    #XXX: 此时连接是否还活着? 如果在排队期间断线了, 取出来查询的时候就会报
                    #(2006, MySQL server has gone away), 报错说明数据库确实出问题了.
                    return c
        except Queue.Empty:
            if self.overflow >= 0:
                if not block:
                    return self.connect()
                else:
                    raise TimeoutError(
                        "QueuePool limit of size %d, "
                        "connection timed out, timeout %d" %
                        (self.size(), self.timeout))
            
            if self.inc_overflow():
                try:
                    return self.create_connection()
                except:
                    self.dec_overflow()
                    raise

    def return_conn(self, conn):
        if not conn.open:
            return
        if conn in self.cset:
            return
        if time.time() - conn._activetime >= self.recycle:
            self.close(conn)
            return
        try:
            self.cset.add(conn)
            self.q.put(conn, False)
        except Queue.Full:
            logging.warning('QueuePool Full: %s' % self.q.qsize())
            self.close(conn)

    def size(self):
        return self.q.maxsize

    def len(self):
        return self.q.qsize()

    def clear(self):
        while 1:
            try:
                c = self.q.get(False)
                self.close(c)
            except Queue.Empty:
                break


raw_connect = MySQLdb.connect

def im_close(conn):
    if hasattr(conn, '_pool'):
        conn._pool.return_conn(conn)

def im_query(conn, sql):
    try:
        conn._activetime = time.time()
        return conn._query(sql)
    except Error as e:
        # destroy the connection when connection break
        if e[0] in (2006, 2013):
            conn._pool.close(conn)
        raise


class PoolManager:

    def __init__(self):
        self.pools = {}

    def connect(self, **kw):
        pool_size = kw.pop('pool_size', 8)
        recycle = kw.pop('wait_timeout', 30)

        def creator():
            c = raw_connect(**kw)
            # monkey patch
            if not hasattr(c, '_query'):
                c._query = c.query
                c.query = types.MethodType(im_query, c)
            if not hasattr(c, '_close'):
                c._close = c.close
                c.close = types.MethodType(im_close, c)
            return c

        key = (kw['host'], kw['port'], kw['user'], kw['db'])
        pool = self.pools.setdefault(key, QueuePool(creator, pool_size=pool_size, recycle=recycle))
        return pool.connect()


def monkey_patch(pool_size):
    """Inception"""
    manager = PoolManager(pool_size)

    def im_connect(**kw):
        return manager.connect(**kw)

    MySQLdb.connect = im_connect
    Connection._close = Connection.close
    Connection.close = im_close  # 此时close不再关闭连接, 而是归还连接池, 查询完应该主动调用归还连接
    Connection._query = Connection.query
    Connection.query = im_query
