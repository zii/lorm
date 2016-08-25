#coding: utf-8
from gevent import monkey;monkey.patch_all()
import gevent
import lorm
import time

pool = lorm.mysql_pool('localhost', 3306, 'root', 'root', 'test', max_connections=5)
def foo():
    pool.c.execute("select sleep(2)")
    print len(pool)

g_list = []
for i in xrange(5):
    g = gevent.spawn(foo)
    g_list.append(g)

st = time.time()
gevent.joinall(g_list)
print 'took', time.time() - st
