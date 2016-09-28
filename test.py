#coding: utf-8
import lorm
import datetime

def test_reconnect():
    c = lorm.mysql_connect('192.168.0.111', 3306, 'root', 'root', 'test', autoreconnect=1)
    print c.fetchall("select sleep(10)")

def test_commit():
    c = lorm.mysql_connect('localhost', 3306, 'root', 'root', 'test', autocommit=0)
    c.pets.filter(id=1).update(name='cat')
    c.commit()
    try:
        c.pets.filter(id=1).update(name='大象')
    finally:
        print c.last_query
    c2 = c.dup()
    c2.autocommit(1)
    print c2.pets.get(id=1)
    c.commit()
    print c2.pets.get(id=1)

def test_rollback():
    c = lorm.mysql_connect('localhost', 3306, 'root', 'root', 'test', autocommit=1)
    c.begin()
    c.pets.create(name='bird')
    c.rollback()
    c.commit()

def test_example():
    c = lorm.mysql_connect('localhost', 3306, 'root', 'root', 'test')
    id = c.pets.create(name='cat')
    print id
    print c.pets.get(id=id)
    print c.last_query
    print c.fetchall("select * from pets")

if __name__ == '__main__':
    "test"
    #test_example()
    #test_commit()
    #test_reconnect()
    #test_rollback()

    #c = lorm.mysql_connect('192.168.0.130', 3306, 'dba_user', 'tbkt123456', 'tbkt')
    #c = lorm.mysql_connect('121.40.85.144', 3306, 'root', 'aa131415', 'crawler')

    #print c.pets.filter(id=11).update(name='xxx')
    #print c.pets.filter(id=15).delete('pets')
    #print c['crawler'].goods.rows()[0]
    #print c.goods.get(id=1)
    #import datetime
    #print c.goods.filter(add_time=datetime.datetime(2016, 8, 12, 10, 48, 29)).first()
    #print c.goods.filter(id__in=[1])[:]
    #print c.goods.count()
    #print c.pets.create(name='dog2')
    #print c.pets.bulk_create([{'name':'dog4'}], ignore=1)
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
    #print c.last_query
