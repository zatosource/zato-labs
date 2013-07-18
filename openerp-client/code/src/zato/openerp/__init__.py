# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
from logging import getLogger
from traceback import format_exc

# OpenERP
import openerplib

class Client(object):
    def __init__(self, name, hostname, database, login, password, port=8069, protocol='xmlrpc', user_id=None):
        self.name = name
        self.hostname = hostname
        self.database = database
        self.login = login
        self.password = password
        self.port = port
        self.protocol = protocol
        self.user_id = user_id
        self.conn = None
        
        self.logger = getLogger(self.__class__.__name__)
        
        # Imported here so it doesn't interfere with gevent's monkey-patching
        from time import time
        self.time = time
        
    def connect(self):
        self.conn = openerplib.get_connection(self.hostname, self.protocol, self.port, self.database,
            self.login, self.password, self.user_id)
        
    def ping(self):
        """ Pings an OE connection by logging a user in.
        """ 
        self.logger.debug('About to ping an OpenERP connection:[{}]'.format(self.name))

        start_time = self.time()
        self.conn.check_login()
        response_time = self.time() - start_time

        self.logger.debug('Ping OK, connection:[{0}], response_time:[{1:03.4f} s]'.format(self.name, response_time))

        return response_time


hostname = 'localhost'
database = 'behave'
login = 'admin'
password = 'admin'

client = Client('My OE conn', hostname, database, login, password)
client.connect()
print(client.ping())

'''

conn = openerplib.get_connection(hostname=hostname, database=database, login=login, password=password)
conn.user_id = 1111

user_model = conn.get_model('res.users')
ids = user_model.search([('login', '=', 'admin')])
user_info = user_model.read(ids[0], ['name'])
print user_info['name']
'''

"""
self.openerp['mydb'].conn.search_read(login='admin')
"""