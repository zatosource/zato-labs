# -*- coding: utf-8 -*-

"""
Copyright (C) 2015 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from logging import getLogger

# cryptography
from cryptography.fernet import Fernet

# Zato
try:
    from zato.server.service import Service
except ImportError:
    class Service(object):
        # Dummy so that CLI works
        pass

# ################################################################################################################################

class _EncryptedLogger(object):
    def __init__(self, service):
        self.service = service
        self.fernet = Fernet(self.service.user_config.user.enclog.fernet_key)
        self._enclog = getLogger('enclog')

    def _encrypt(self, msg):
        return 'enclogdata:{}'.format(self.fernet.encrypt(msg.encode('utf-8')))

    def debug(self, msg):
        return self._enclog.debug(self._encrypt(msg))

    def info(self, msg):
        return self._enclog.info(self._encrypt(msg))

    def warn(self, msg):
        return self._enclog.warn(self._encrypt(msg))

    def error(self, msg):
        return self._enclog.error(self._encrypt(msg))

# ################################################################################################################################

class EncryptedLoggingAware(Service):
    name = 'enc.logging.aware'

    def before_handle(self):
        self.enclog = _EncryptedLogger(self)

    def handle(self):
        self.enclog.warn(data)

# ################################################################################################################################
