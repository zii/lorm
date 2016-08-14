# lorm
A light weight python ORM without models.

# Examples:
```
c = Connection()
c.connect('localhost', 3306, 'dba_user', '123456', 'tbkt')

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
print c.word2.delete(id=3)
sql = "insert into word2 set text=%s" % literal("c'a't")
print c.execute(sql)
print c.word2.create(text="x'x'yy", phoneticy='a', phoneticm='b')
print list(c.tmp_id.order_by('-id'))
print len(c.tmp_id)
print c.auth_user.filter(id=1).rows
print c.execute_many("insert into word2 (text, phoneticy) values (%s, %s)", (('cat2', 'xxx'), ('cat3', 'xxx'),))
word = {"text":"cat4", "phoneticy":"dd"}
c.word2.bulk_create([word]*2)
```