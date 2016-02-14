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
import os
import sys
from logging.handlers import RotatingFileHandler
from httplib import OK, responses

# gevent
#from gevent.pywsgi import WSGIServer

# havocbot
from havocbot.bot import HavocBot

# Munch
from munch import Munch, munchify

# rapidjson
from rapidjson import loads

# setproctitle
from setproctitle import setproctitle

# ################################################################################################################################

class const:
    exit_invalid_log_conf = 1

# ################################################################################################################################

class Server(object):
    def __init__(self, conf, conf_path):
        self.conf = conf
        self.conf_path = conf_path
        self.name = '{} ({})'.format(self.conf.core.name, self.conf.core.chat_provider)
        self.setup_logging()
        self.bot = None

# ################################################################################################################################

    def setup_logging(self):

        log_conf = self.conf.logging

        log_path = log_conf.log_file
        if not os.path.isabs(log_path):
            log_path = os.path.abspath(os.path.join(os.path.dirname(self.conf_path), log_path))

        log_dir = os.path.dirname(log_path)
        if not os.path.exists(log_dir):
            sys.stderr.write('Could not find log directory `%s`\n' % log_dir)
            sys.exit(const.exit_invalid_log_conf)

        formatter = logging.Formatter(log_conf.format)

        file_handler = RotatingFileHandler(log_path, maxBytes=log_conf.max_log_size, backupCount=log_conf.max_backups)
        file_handler.setFormatter(formatter)

        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)

        self.logger = logging.getLogger('zato.chatops')
        self.logger.setLevel(getattr(logging, log_conf.level))

        self.logger.addHandler(file_handler)
        self.logger.addHandler(stdout_handler)

        logging.basicConfig(level=logging.INFO, format=self.conf.logging.format)

# ################################################################################################################################

    def on_request(self, req):
        self.logger.info(req)

# ################################################################################################################################

    def run_forever(self):

        class _Bot(HavocBot):
            def __init__(self, on_request_cb, *args, **kwargs):
                self.on_request_cb = on_request_cb
                HavocBot.__init__(self, *args, **kwargs)

        # So it's easier to find us
        setproctitle(self.name)

        # Ok, only logging left ..
        self.logger.info('Starting %s' % self.name)

        bot_conf = Munch()
        bot_conf.clients_enabled = 'zato_hipchat'
        bot_conf.plugin_dirs = 'plugins'

        client_conf = Munch()
        client_conf.zato_hipchat = []
        client_conf.zato_hipchat.extend(getattr(self.conf, self.conf.core.chat_provider).items())

        self.bot = _Bot(self.on_request)
        self.bot.add_client_package('zato.chatops.zato_havocbot_client.%s')
        self.bot.set_settings(havocbot_settings=bot_conf, clients_settings=client_conf)

        try:
            self.bot.start()
        except (KeyboardInterrupt, SystemExit):
            self.logger.info('Shutting down %s', self.name)
            if self.bot.clients is not None and len(self.bot.clients):
                self.bot.shutdown()
            sys.exit(0)

# ################################################################################################################################
