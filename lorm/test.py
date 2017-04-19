#coding: utf-8
from db import Hub
import datetime

if __name__ == '__main__':
    "test"
    db = Hub()
    # master db connection
    db.add_pool('default', host='192.168.0.130', port=3306, user='dba_user', 
                passwd='tbkt123456', db='test', charset='utf8', autocommit=True,
                pool_size=8, wait_timeout=30)
    # slave db connection
    db.add_pool('slave', host='192.168.0.130', port=3306, user='dba_user', 
                passwd='tbkt123456', db='test', charset='utf8', autocommit=True,
                pool_size=8, wait_timeout=30)

    #user = db.default.auth_user.get(id=1)
    #print user
    # >>> {u'username': u'super', u'real_name': u'\u73ed\u5185\u7f51', u'last_login': datetime.datetime(2013, 4, 10, 11, 22, 6), 
    # >>> u'portrait': u'portrait/2009/08/24/small_super.png', u'password': u'sha1$e7852$9145986c1df5da5ef390e6d95bcf9c4e6a828608'
    # >>> , u'type': 3, u'id': 1, u'date_joined': datetime.datetime(2009, 8, 24, 17, 26, 26)}
    #print user.id, user.last_login
    # >>> 1 2013-04-10 11:22:06

    #print db.slave.auth_user[0]

    # greater than
    #print db.slave.auth_user.filter(id__gt=10).first()

    # less than
    #print db.slave.auth_user.filter(id__lt=10).last()

    # not equal
    #print db.slave.auth_user.filter(id__ne=1).first()

    # in
    #print db.slave.auth_user.filter(id__in=(1,2,3))[:]

    # not in
    #q = db.slave.auth_user.filter(id__in=(1,2,3), id__ni=(1,3)).flat('id')
    #print q[:]
    # >>> [2]
    #print q.sql
    # >>> select id from auth_user where id not in (1,3) and id in (1,2,3)

    #print db.default.auth_user.filter(id__lt=10).select('id')[:]
    # >>> [{u'id': 1}, {u'id': 2}, {u'id': 3}]

    #print db.default.auth_user.filter(id__lt=10).values('id')[:]
    # >>> ((1,), (2,), (3,))
    
    #print db.default.auth_user.filter(id__lt=10).flat('id')[:]
    # >>> [1, 2, 3]

    #print db.slave.auth_user.count()
    # >>> 979

    #print db.slave.auth_user.filter(real_name__startswith='熊猫').select('id').first()
    # >>> {u'id': 1}

    #print db.slave.auth_user.filter(real_name__endswith='熊猫').select('id').first()
    # >>> {u'id': 1}

    #print db.slave.auth_user.filter(real_name__contains='熊猫').select('id').first()
    # >>> {u'id': 1}

    #q = db.slave.auth_user.filter(id__range=(1,3)).flat('id')
    #print q.sql
    # >>> select id from auth_user where id between 1 and 3
    #print q[:]
    # >>> [1, 2, 3]

    # reverse order
    #print db.slave.auth_user.filter(id__lt=10).order_by('-id').flat('id')[:]
    # >>> [3, 2, 1]

    # random sort
    #print db.slave.auth_user.filter(id__lt=10).order_by('?').flat('id')[:]
    # >>> [2, 3, 1]

    # group by
    #print db.slave.school.group_by('county').select('county', 'count(*) n').order_by('-n')[:3]
    # SQL: select county,count(*) n from school  group by county order by n desc limit 3
    # >>> [{u'county': u'410928', u'n': 823}, {u'county': u'410482', u'n': 793}, {u'county': u'410423', u'n': 730}]

    # insert
    #print db.default.auth_user.create(id=10, username='13500000000xs', real_name='斑马')
    # >>> 10

    # bulk insert
    #users = [{'username':'13500000011xs', 'real_name':'仙人掌'}, 
    #         {'username':'13500000012xs', 'real_name':'仙人球'}]
    #print db.default.auth_user.bulk_create(users)
    # >>> 2

    # check if exists
    #if db.slave.auth_user.filter(id=10):
    #    print 'exists!'

    # update
    #print db.default.auth_user.filter(id=1).update(real_name='熊猫')
    # >>> 1
    #print db.default.auth_user.filter(id=1).update(real_name='熊猫')
    # >>> 0

    # delete
    #print db.default.auth_user.filter(id=10).delete()
    # >>> 1
    #print db.default.auth_user.filter(id=10).delete()
    # >>> 0
