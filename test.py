#coding: utf-8
from gevent import monkey;monkey.patch_all()
import gevent
import lorm
import time

db = lorm.MysqlPool('121.40.85.144', 3306, 'root', 'aa131415', 'crawler')
#db = lorm.mysql_connect('121.40.85.144', 3306, 'root', 'aa131415', 'crawler')
def foo():
    db.execute("select sleep(2)")

g_list = []
for i in xrange(5):
    g = gevent.spawn(foo)
    g_list.append(g)

st = time.time()
gevent.joinall(g_list)
print 'took', time.time() - st
