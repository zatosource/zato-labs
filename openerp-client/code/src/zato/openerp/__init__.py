# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# stdlib
from logging import getLogger
from traceback import format_exc

# Zato
from zato.common import ZatoException
from zato.server.service import Service

OE_CONN_INFO_PREFIX = 'zato:openerp:conn-info'
OE_PARAMS = {}

for name in('hostname', 'database', 'port', 'login', 'password'):
    OE_PARAMS[name] = '{}:{}'.format(OE_CONN_INFO_PREFIX, name)

class Client(object):
    def __init__(self, name=None, hostname=None, database=None, login=None, password=None, port=8069, protocol='xmlrpc', user_id=None):
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
        
        # stdlib
        from time import time
        self.time = time
        
        # OpenERP
        import openerplib
        self.openerplib = openerplib
        
    def connect(self):
        self.conn = self.openerplib.get_connection(self.hostname, self.protocol, self.port, self.database,
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

class OpenERPService(Service):
    """ Subclassing this service gives you access to the self.openerp object
    which is a thin wrapper around openerplib's connection.
    """
    def before_handle(self):
        self.openerp = self
        
    def get(self, name):
        params = {
            'hostname': None,
            'database': None,
            'port': None,
            'login': None,
            'password': None
        }
        missing = []
        for param in params:
            key_prefix = OE_PARAMS[param]
            key = ':'.join((key_prefix, name))
            value = self.kvdb.conn.get(key)
            
            if not value:
                missing.append(key)
            else:
                value = int(value) if param == 'port' else value
                params[param] = value
                
        if missing:
            msg = 'One or more config key is missing or has no value: {}'.format(missing)
            self.logger.error(msg)
            raise ZatoException(self.cid, msg)

        client = Client(**params)
        client.connect()
        
        return client
    
    # It's the same thing right now but will be a different method when the client
    # is added to the core.
    ping = get
