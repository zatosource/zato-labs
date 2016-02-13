# -*- coding: utf-8 -*-

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

# gevent
from gevent.pywsgi import WSGIServer

# setproctitle
from setproctitle import setproctitle

class const:
    exit_invalid_log_conf = 1

# ################################################################################################################################

class Server(object):
    def __init__(self, conf, conf_path):
        self.conf = conf
        self.conf_path = conf_path
        self.host = self.conf.core.listen_host
        self.port = int(self.conf.core.listen_port)
        self.name = '%s %s:%s%s %s' % (self.conf.core.name, self.host, self.port, self.conf.core.url_path, self.conf_path)
        self.setup_logging()

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

    def _on_request(self, env):
        pass

# ################################################################################################################################

    def on_wsgi_request(self, env, start_response):
        if env['PATH_INFO'] == self.conf.core.url_path:
            status, response = self._on_request(env)
            content_type = 'application/json'
        else:
            status, response = '404 Not Found', b'Not found\n'
            content_type = 'text/json'

        start_response(status, [('Content-Type', content_type)])
        return [response]

# ################################################################################################################################

    def run_forever(self):

        # So it's easier to find us
        setproctitle(self.name)

        # Ok, only logging left ..
        self.logger.info('Starting %s' % self.name)

        # .. and we can start.
        _s = WSGIServer((self.host, self.port), self.on_wsgi_request)
        _s.serve_forever()

# ################################################################################################################################
