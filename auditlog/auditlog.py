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

# Bunch
from bunch import bunchify

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

class exit_code:
    invoke_error = 1
    no_channel_match = 2
    no_search_match = 3

# ################################################################################################################################

class ZatoClient(AnyServiceInvoker):
    def __init__(self, *args, **kwargs):
        super(ZatoClient, self).__init__(*args, **kwargs)
        self.cluster_id = None
        self.odb_session = None

    def invoke(self, *args, **kwargs):
        response = self._invoke(async=False, *args, **kwargs)
        if response.ok:
            response.data = bunchify(response.data)
        return response

# ################################################################################################################################

class AuditLogTool(object):

    def __init__(self, path, channel_pattern, search_pattern, cid):
        self.path = path
        self.channel_pattern = channel_pattern if channel_pattern != 'all' else ''
        self.search_pattern = search_pattern
        self.cid = cid

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
        channels = self.client.invoke(
            'zato.http-soap.get-list', {'cluster_id':self.client.cluster_id, 'connection':'channel', 'transport':'plain_http'})
        seen_any = False

        for item in sorted(channels.data, key=itemgetter('name')):
            if self.channel_pattern not in item.name:
                continue

            config = self.client.invoke('zato.http-soap.get-audit-config', {'id':item.id}).data
            config.service_id = item.id
            config.name = item.name
            seen_any = True
            yield config

        if not seen_any:
            logging.warn('No channels matching pattern `%s`', self.channel_pattern)
            sys.exit(exit_code.no_match)

    def status(self):
        table = Texttable()
        table.set_cols_dtype(['t', 't'])

        rows = [['service_name', 'audit_enabled']]
        for item in self.get_items():
            rows.append((item.name, item.audit_enabled))

        table.add_rows(rows)
        print(table.draw())

    def _set_state(self, enable=True):
        verb = 'Enabled' if enable else 'Disabled'

        for item in self.get_items():
            seen_any = True
            response = self.client.invoke('zato.http-soap.set-audit-state', {'id':item['service_id'], 'audit_enabled':enable})
            if not response.ok:
                logging.error(response.details)
                sys.exit(exit_code.invoke_error)
            logging.info('%s audit log for `%s`' % (verb, item['name']))

    def enable(self):
        self._set_state()

    def disable(self):
        self._set_state(False)

    def search(self):
        result = []
        for item in self.get_items():
            if item.audit_enabled:
                print(item.name, item.audit_enabled)

        if not result:
            logging.info('No results')

# ################################################################################################################################

@click.group()
def cli_main():
    pass

# ################################################################################################################################

def get_arg(name):

    def _cli_arg(ctx, path, channel_pattern, search_pattern=None, cid=None):
        tool = AuditLogTool(path, channel_pattern, search_pattern, cid)
        tool.set_client()
        getattr(tool, name)()

    _cli_arg = click.pass_context(_cli_arg)

    if name == 'search':
        _cli_arg = click.argument('search_pattern', required=True)(_cli_arg)

    elif name == 'get':
        _cli_arg = click.argument('cid', required=True)(_cli_arg)

    _cli_arg = click.argument('channel_pattern', required=True)(_cli_arg)
    _cli_arg = click.argument('path', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))(_cli_arg)

    _cli_arg = click.command()(_cli_arg)

    return _cli_arg

# ################################################################################################################################

for name in ('enable', 'disable', 'status', 'search'):
    cli_main.add_command(get_arg(name), name)

# ################################################################################################################################

if __name__ == '__main__':
    cli_main()

# ################################################################################################################################
