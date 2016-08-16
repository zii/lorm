**Example**

::

 import lorm
 
 c = lorm.mysql_connect('localhost', 3306, 'root', '******', 'mysql')
 
 print c.user.get(host='localhost')
