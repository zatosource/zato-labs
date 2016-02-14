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
from httplib import OK
from threading import RLock

# havocbot
from havocbot.bot import HavocBot

# Munch
from munch import Munch, munchify

# rapidjson
from rapidjson import loads

# requests
import requests

# setproctitle
from setproctitle import setproctitle

# zato-elem
from zato.elem import json

# ################################################################################################################################

class const:
    exit_invalid_log_conf = 1

# ################################################################################################################################

class Server(object):
    def __init__(self, conf, conf_path):
        self.conf = conf
        self.conf_path = conf_path
        self.name = '{} ({})'.format(self.conf.core.name, self.conf.core.chat_provider)
        self.self_mention = self.conf.hipchat.mention
        self.mentions = {}
        self.api_url = self.conf.hipchat.api_url
        self.api_token = self.conf.hipchat.api_token
        self.setup_logging()
        self.bot = None
        self.update_lock = RLock()

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

# ################################################################################################################################

    def _call_api(self, path, **params):
        _params = {'auth_token': self.api_token}
        _params.update(params)
        response = requests.get('{}{}'.format(self.api_url, path), _params)

        if response.status_code != OK:
            raise Exception(response.text)

        return munchify(loads(response.text))

# ################################################################################################################################

    def _set_mentions(self):
        for item in self._call_api('/user')['items']:
            self.mentions[item.name] = '@{}'.format(item['mention_name'])

# ################################################################################################################################

    def get_sender_mention(self, from_):
        with self.update_lock:
            if from_ not in self.mentions:
                self._set_mentions()
            return self.mentions[from_]

# ################################################################################################################################

    def get_response(self, msg):
        return msg

# ################################################################################################################################

    def handle(self, client, req):
        self.logger.info(req)
        req.reply('{} {}'.format(
            self.get_sender_mention(req.get_mucnick()), self.get_response(req['body'].replace(self.self_mention, '', 1).strip())))
        req.send()

# ################################################################################################################################

    def on_request(self, client, req):
        if req['body'].startswith(self.self_mention):
            self.handle(client, req)

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

        from_ = 'Dariusz Suchojad'
        self.get_sender_mention(from_)

        try:
            self.bot.start()
        except (KeyboardInterrupt, SystemExit):
            self.logger.info('Shutting down %s', self.name)
            if self.bot.clients is not None and len(self.bot.clients):
                self.bot.shutdown()
            sys.exit(0)

# ################################################################################################################################
