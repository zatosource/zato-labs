# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import logging, os, sys
from operator import itemgetter

# Click
import click

# Texttable
from texttable import Texttable

# Zato
from zato.cli import cli_util
from zato.client import AnyServiceInvoker
from zato.common.odb.model import Server
from zato.common.util import get_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ################################################################################################################################

class ZatoClient(AnyServiceInvoker):
    def __init__(self, *args, **kwargs):
        super(ZatoClient, self).__init__(*args, **kwargs)
        self.cluster_id = None
        self.odb_session = None

# ################################################################################################################################

class AuditLogTool(object):

    def __init__(self, path, prefix):
        self.path = path
        self.prefix = prefix if prefix != 'all' else '*'

    def set_client(self):

        repo_dir = os.path.join(os.path.abspath(os.path.join(self.path)), 'config', 'repo')
        config = get_config(repo_dir, 'server.conf')

        self.client = ZatoClient('http://{}'.format(config.main.gunicorn_bind),
            '/zato/admin/invoke', cli_util.get_server_client_auth(config, repo_dir), max_response_repr=150000)

        session = cli_util.get_odb_session_from_server_config(
            config, cli_util.get_crypto_manager_from_server_config(config, repo_dir))

        self.client.cluster_id = session.query(Server).\
            filter(Server.token == config.main.token).\
            one().cluster_id

        self.client.odb_session = session

    def get_items(self):
        services = self.client.invoke(
            'zato.http-soap.get-list', {'cluster_id':self.client.cluster_id, 'connection':'channel', 'transport':'plain_http'})

        for item in sorted(services.data, key=itemgetter('name')):
            if self.prefix != '*':
                if item['name'].startswith(self.prefix):
                    config = self.client.invoke('zato.http-soap.get-audit-config', {'id':item['id']}).data
                    config['service_id'] = item['id']
                    config['name'] = item['name']
                    yield config

    def status(self):
        table = Texttable()
        table.set_cols_dtype(['t', 't'])

        rows = [['service_name', 'audit_enabled']]
        for item in self.get_items():
            rows.append((item['name'], item['audit_enabled']))

        table.add_rows(rows)
        print(table.draw())

    def _set_state(self, enable=True):
        verb = 'Enabled' if enable else 'Disabled'

        for item in self.get_items():
            response = self.client.invoke('zato.http-soap.set-audit-state', {'id':item['service_id'], 'audit_enabled':enable})
            if not response.ok:
                logging.error(response.details)
                sys.exit(1)
            logging.info('%s audit log for `%s`' % (verb, item['name']))

    def enable(self):
        self._set_state()

    def disable(self):
        self._set_state(False)

# ################################################################################################################################

@click.group()
def cli_main():
    pass

# ################################################################################################################################

def get_arg(name):

    @click.command()
    @click.argument('path', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
    @click.argument('prefix', default='all')
    @click.pass_context
    def _cli_arg(ctx, path, prefix):
        tool = AuditLogTool(path, prefix)
        tool.set_client()
        getattr(tool, name)()

    return _cli_arg

# ################################################################################################################################

for name in ('enable', 'disable', 'status'):
    cli_main.add_command(get_arg(name), name)

# ################################################################################################################################

if __name__ == '__main__':
    cli_main()

# ################################################################################################################################
