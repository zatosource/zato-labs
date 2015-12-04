# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

"""
Copyright (C) 2015 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import logging
import sys
from logging import getLogger, Formatter

# click
import click

# cryptography
from cryptography.fernet import Fernet, InvalidToken

# Tailer
from tailer import follow

# ################################################################################################################################

log_prefix = 'enclogdata:'
log_prefix_len = len(log_prefix)

cli_key_option = '--fernet-key'
cli_key_prompt='Fernet key'
cli_key_confirm_prompt=False
cli_key_help='Fernet key to decrypt data with.'

# ################################################################################################################################

class EncryptedLogFormatter(Formatter):
    def __init__(self, fernet_key, *args, **kwargs):
        self.fernet = Fernet(fernet_key)
        return super(EncryptedLogFormatter, self).__init__(*args, **kwargs)

    def format(self, record):
        record.msg = '{}{}'.format(log_prefix, self.fernet.encrypt(record.getMessage()))
        return super(EncryptedLogFormatter, self).format(record)

# ################################################################################################################################

def _open(ctx, path, fernet_key, needs_tailf=False):
    fernet = Fernet(fernet_key)

    # Plain open
    f = open(path)

    # tail -f
    if needs_tailf:
        f = follow(f, delay=0.1)

    for line in f:
        prefix, encrypted = line.split(log_prefix)
        try:
            sys.stdout.write('{}{}\n'.format(prefix, fernet.decrypt(encrypted)))
            sys.stdout.flush()
        except InvalidToken:
            sys.stderr.write('Invalid Fernet key\n')
            sys.exit(1)

# ################################################################################################################################

@click.group()
def cli_main():
    pass

# ################################################################################################################################

@click.command()
@click.pass_context
def genkey(ctx):
    sys.stdout.write('{}\n'.format(Fernet.generate_key()))

def get_arg(name):

    @click.command()
    @click.argument('path', type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True))
    @click.password_option(cli_key_option, prompt=cli_key_prompt, confirmation_prompt=cli_key_confirm_prompt, help=cli_key_help)
    @click.pass_context
    def _cli_arg(ctx, path, fernet_key):
        _open(ctx, path, fernet_key.encode('utf-8'), True if name == 'tailf' else False)

    return _cli_arg

cli_main.add_command(genkey)

for name in ('open', 'tailf'):
    cli_main.add_command(get_arg(name), name)

# ################################################################################################################################

if __name__ == '__main__':

    level = logging.DEBUG
    format = '%(levelname)s - %(message)s'

    formatter = EncryptedLogFormatter(Fernet.generate_key(), format)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = getLogger('')
    logger.addHandler(handler)
    logger.setLevel(level)

    logger.info('{"user":"Jane Xi"')

# ################################################################################################################################
