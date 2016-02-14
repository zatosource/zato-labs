# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# Click
import click

# ConfigObj
from configobj import ConfigObj

# Munch
from munch import munchify

# Zato
from zato.chatops.server import Server

@click.group()
def main():
    pass

@click.command()
@click.option('--path', default='conf/chatops.conf', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.pass_context
def run(ctx, path):
    """ Starts Zato ChatOps server using configuration file from `path`.
    """
    Server(munchify(ConfigObj(path)), path).run_forever()

main.add_command(run)

if __name__ == '__main__':
    main()
