# -*- coding: utf-8 -*-

"""
Copyright (C) 2015 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import sys
from logging import getLogger

# click
import click

# cryptography
from cryptography.fernet import Fernet

# Zato
try:
    from zato.server.service import Service
except ImportError:
    class Service(object):
        pass # Dummy so that CLI works outside of Zato

# ################################################################################################################################

log_prefix = 'enclogdata:'
log_prefix_len = len(log_prefix)

cli_key_option = '--fernet-key'
cli_key_prompt='Fernet key'
cli_key_confirm_prompt=False
cli_key_help='Fernet key to decrypt data with.'

# ################################################################################################################################

class _EncryptedLogger(object):
    def __init__(self, service):
        self.service = service
        self.fernet = Fernet(self.service.user_config.user.enclog.fernet_key)
        self._enclog = getLogger('enclog')

    def _encrypt(self, msg):
        return '{}{}'.format(log_prefix, self.fernet.encrypt(msg.encode('utf-8')))

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

def _open(ctx, path, fernet_key):
    fernet = Fernet(fernet_key)
    for line in open(path):
        prefix, encrypted = line.split(log_prefix)
        sys.stdout.write('{}{}'.format(prefix, fernet.decrypt(encrypted)))

# ################################################################################################################################

@click.group()
def cli_main():
    pass

@click.command()
@click.argument('path', type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True))
@click.password_option(cli_key_option, prompt=cli_key_prompt, confirmation_prompt=cli_key_confirm_prompt, help=cli_key_help)
@click.pass_context
def _cli_open(ctx, path, fernet_key):
    _open(ctx, path, fernet_key.encode('utf-8'))

@click.command()
@click.argument('path', type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True))
@click.password_option(cli_key_option, prompt=cli_key_prompt, confirmation_prompt=cli_key_confirm_prompt, help=cli_key_help)
@click.pass_context
def _cli_tailf(ctx, path, fernet_key):
    _open(ctx, path, fernet_key.encode('utf-8'))

cli_main.add_command(_cli_open, 'open')
cli_main.add_command(_cli_tailf, 'tailf')

if __name__ == '__main__':
    main()
