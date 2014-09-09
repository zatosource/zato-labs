# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# Click
from click import argument, command, File, group, option, Path

# ######################################################################################################################

@group()
def cli():
    pass

# ######################################################################################################################

@cli.group()
def ca():
    pass

@ca.group('create')
def ca_create():
    pass

@argument('path', type=Path(exists=True, file_okay=False))
@option('--verbose', is_flag=True)
@option('--store-log', is_flag=True)
@option('--store-config', is_flag=True)
@option('--organization', help='Organization name (O)')
@option('--organizational-unit', help='Organizational unit (OU)')
@option('--locality', help='Locality name (L)')
@option('--state-or-province', help='State or province name')
@option('--country', help='Country name (C)')
@option('--common-name', help='Common name (CN)')
@ca_create.command('ca')
def ca_create_ca(**kwargs):
    pass

@argument('path', type=Path(exists=True, file_okay=False))
@option('--verbose', is_flag=True)
@option('--store-log', is_flag=True)
@option('--store-config', is_flag=True)
@option('--organization', help='Organization name (O)')
@option('--organizational-unit', help='Organizational unit (OU)')
@option('--locality', help='Locality name (L)')
@option('--state-or-province', help='State or province name')
@option('--country', help='Country name (C)')
@option('--common-name', help='Common name (CN)')
@ca_create.command('lb_agent')
def ca_create_lb_agent():
    pass

@ca_create.group('server')
def ca_create_server():
    pass

@ca_create.group('server')
def ca_create_server():
    pass

@ca_create.group('web_admin')
def ca_create_web_admin():
    pass

# ######################################################################################################################

def main():
    cli()
