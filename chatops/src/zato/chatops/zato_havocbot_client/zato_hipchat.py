# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import logging
from traceback import format_exc

# havocbot
from havocbot.clients.hipchat import HipChat as _HipChat, HipMUCBot as _HipMUCBot
from havocbot.message import Message

# ################################################################################################################################

logger = logging.getLogger(__name__)

# ################################################################################################################################

class ZatoHipChat(_HipChat):

    @property
    def integration_name(self):
        return 'zato_hipchat'

    def handle_message(self, req):
        self.havocbot.on_request_cb(req)

    def connect(self):
        if not self.username:
            logger.error('An XMPP username must be configured')

        if not self.password:
            logger.error('An XMPP password must be configured')

        self.client = HipMUCBot(
            self, self.havocbot, self.username, self.password, self.room_name + '@' + self.server, self.nickname)

        self.client.register_plugin('xep_0030')  # Service Discovery
        self.client.register_plugin('xep_0045')  # Multi-User Chat

        # XMPP Ping set for a keepalive ping every 60 seconds
        self.client.register_plugin('xep_0199', {'keepalive': True, 'interval': 60})

        if self.client.connect():
            logger.info('Connected as {} ({})'.format(self.nickname, self.username))
            return True
        else:
            return False

# ################################################################################################################################

class HipMUCBot(_HipMUCBot):

    def muc_message(self, msg):
        logger.info('Got message %s', msg)
        if msg['mucnick'] != self.nick:
            try:
                self.parent.handle_message(Message(msg['body'], msg['mucnick'], self.room, 'message'))
            except Exception as e:
                logger.error(format_exc(e))

# ################################################################################################################################
