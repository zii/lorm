#coding: utf-8
from lorm import Hub
import datetime
import time
import pymysql

if __name__ == '__main__':
    "test"
    db = Hub(pymysql)
    # master db connection
    db.add_pool('default', host='192.168.0.209', port=3306, user='root', 
                passwd='mysqlzhdzeyadkjcau62', db='test', charset='utf8', autocommit=True,
                pool_size=8, wait_timeout=30)

    #pet = db.default.pet.get(id=1)
    #print pet
    # >>> {u'id': 1, u'name': u'cat'}
    #print pet.id, pet.name
    # >>> 1 cat

    #print db.default.pet[0]

    # >
    #print db.default.pet.filter(id__gt=10).first()

    # <
    #print db.default.pet.filter(id__lt=10).last()

    # !=
    #print db.default.pet.filter(id__ne=1).order_by('id').first()

    # in
    #print db.default.pet.filter(id__in=(1,2,3))[:]

    # not in
    # q = db.default.pet.filter(id__in=(1,2,3), id__ni=(1,3)).flat('id')
    # print q[:]
    # >>> [2]
    # print q.sql
    # >>> select id from pet where `id` not in (1,3) and `id` in (1,2,3)

    # row style: dict
    #print db.default.pet.filter(id__lt=10).select('id')[:]
    # >>> [{u'id': 1}, {u'id': 2}, {u'id': 3}]

    # row style: 2D-array
    #print db.default.pet.filter(id__lt=10).values('id')[:]
    # >>> ((1,), (2,), (3,))
    
    # row style: 1D-array
    #print db.default.pet.filter(id__lt=10).flat('id')[:]
    # >>> [1, 2, 3]

    # count
    #print db.default.pet.count()
    # >>> 979

    # sum
    #print db.default.pet.flat("sum(id)").first()

    # like 'xxx%'
    #print db.default.pet.filter(name__startswith=u'熊').select('id')[:]
    # >>> {u'id': 1}

    # like '%xxx'
    # c = db.default
    # print c.pet.filter(name__endswith=u'%熊').select('id')[:]
    # >>> {u'id': 1}
    # print c.last_executed

    # like '%xxx%'
    #print db.default.pet.filter(name__contains=u'熊').select('id')[:]
    # >>> {u'id': 1}

    # range
    #q = db.default.pet.filter(id__range=(1,3)).flat('id')
    #print q.sql
    # >>> select id from pet where `id` between 1 and 3   
    #print q[:]
    # >>> [1, 2, 3]

    # exclude
    #print db.default.pet.filter(id__lt=10).exclude(id=2).flat('id')[:]

    # reverse order
    #print db.default.pet.filter(id__lt=10).order_by('-id').flat('id')[:]
    # >>> [3, 2, 1]

    # random sort
    #print db.default.pet.filter(id__lt=10).order_by('?').flat('id')[:]
    # >>> [2, 3, 1]

    # group by
    #print db.default.pet.group_by('name').select('name', 'count(*) n').order_by('-n')[:3]
    # SQL: select name,count(*) n from pet  group by name order by n desc 
    # >>> [{u'name': u'\u718a\u732b', u'n': 2}, {u'name': u'cat,dog', u'n': 1}, {u'name': u'\u6d63\u718a', u'n': 1}]

    # insert
    #print db.default.pet.create(name='斑马')
    # >>> 10

    # insert ... on duplicate
    #print db.default.pet.ondup(name=u"苹果").create(id=1, name='bird')
    #print db.default.pet.ondup(name="unknonw").bulk_create([{'id':'1', 'name':'Micky'}, {'id':20, 'name':'Donald'}])

    # bulk insert
    #items = {'name':'Micky'}, {'name':'Donald'}
    #print db.default.pet.bulk_create(items)
    # >>> 2

    # check if exists
    #print db.default.pet.filter(id=1).exists()

    # update
    # c = db.default
    # print c.pet.filter(id=1).update(name=u'龙猫')
    # print c.last_executed
    # >>> 1
    # >>> update pet set `name`='龙猫' where `id`=1

    # delete
    #print db.default.pet.filter(id=1).delete()
    # >>> 1

    # transaction success, commit
    # with db.default as c:
    #     print c.pet.create(name="crocodile")

    # transaction fail, rollback
    # with db.default as c:
    #     c.pet.create(name="new")  # insert new
    #     c.pet.create(id=1)  # Duplicate PRIMARY error and rollback

    # is connection alive?
    # c = db.default
    # c.character_set_name()
    # print c.open

    # two styles to select a table
    # print db.default['pet'][0]
    # print db.default.pet[0]

    # two styles to select a db
    # print db['default']['pet'][0]
    # print db.default['pet'][0]

    # test encoding
    # now = datetime.datetime.now()
    # s = db.default.literal([now, u"a"])
    # print type(s), s
    # print db.default.literal(u'a"a"a')
    # s = db.default.escape_string(u"是'")
    # print type(s), s

    # raw sql
    # print db.default.execute("insert into pet(name) values(%s)", 'dog')
    # >>> (1, 29)
    # print db.default.fetchall("select * from pet where id in %s", [1,2])
    # >>> ((1, u'cat'), (2, u'\u718a\u732b'))
    # print db.default.fetchall_dict("select * from pet where id in %s", [1,2])
    # >>> [{u'id': 1, u'name': u'cat'}, {u'id': 2, u'name': u'\u718a\u732b'}]
    # print db.default.execute_many("insert into pet(name) value(%s)", ['cat', 'dog'])
    # >>> 2
    #print db.default.execute_many("insert into pet(id, name) value(%s, %s)", [(32, 'cat'), (33, 'dog')])
    # >>> 2
