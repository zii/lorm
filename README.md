# lorm
A light weight python ORM without models.

# Examples:
```python
import lorm

c = orm.Connection()
c.connect('localhost', 3306, 'dba_user', '123456', 'tbkt')
print c.is_connected

c.goods.filter(id=3).delete()
print c.goods.join('search_keywords', "s.keyword=g.keyword").select('g.title', 's.max_price')[2:4]
print c.goods.rjoin('goods', "g2.keyword=g1.keyword").select('g1.id', 'g2.id')[:2]
print c.goods.rows(0,2)
print c.goods.get(id=1)
print c.auth_user.get(id=1)
print c.auth_user[0]
print c.auth_user[1:3]
print c.auth_user.filter(username="1'356'5422119js").first()
print c.auth_user.order_by('-id').select('id', 'username').last()
print c.auth_user.count()
print c.auth_user.select('count(*) n', 'id')[0]
print c.tmp_id[:]
print c.tmp_id.order_by('?').first()
print c.auth_user.order_by('-id').get(is_active=1)
print c.auth_user[-727011]
print c.auth_user.filter(is_active=1).order_by('-id').query
print c.word2.filter(id=3).delete()
sql = "insert into word2 set text=%s" % literal("c'a't")
print c.execute(sql)
print c.word2.create(text="x'x'yy", phoneticy='a', phoneticm='b')
print list(c.tmp_id.order_by('-id'))
print len(c.tmp_id)
print c.auth_user.filter(id=1).rows()
print c.execute_many("insert into word2 (text, phoneticy) values (%s, %s)", (('cat2', 'xxx'), ('cat3', 'xxx'),))
word = {"text":"cat4", "phoneticy":"dd"}
c.word2.bulk_create([word]*2)
print c.u_task.group_by('type').select('type', 'count(*) n').rows()
print c.auth_user.filter(id__gt=1).first()
print c.auth_user.filter(id__in=(1,378364))[:]
print c.auth_user.filter(date_joined__in=('2009-08-24 17:26:26', '2012-06-13 11:48:39'))[:]
print c.auth_user.filter("id=-1 or id>3", is_active=1)[:2]
print c.auth_user.filter(username__icontains='000js')[0]
start = datetime(2016,1,1)
end = datetime(2016,5,5)
print c.auth_user.filter(last_login__range=[start, end])[:2]
print c.auth_user.filter(id__ne=None)[0] # is not null
```