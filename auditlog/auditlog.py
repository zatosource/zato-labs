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

# Arrow
from arrow import get as arrow_get

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

    def __init__(self, server, channel, query, order_by, batch_size, date_format, cid):
        self.server = server
        self.channel = channel if channel != 'all' else ''
        self.query = query
        self.order_by = order_by
        self.batch_size = batch_size
        self.date_format = date_format
        self.cid = cid

        self.logger = logging.getLogger(__name__)

        self.logger.info('Config server: `%s`', self.server)
        self.logger.info('Config channel: `%s`', channel)
        self.logger.info('Config query: `%s`', self.query)
        self.logger.info('Config order_by: `%s`', self.order_by)
        self.logger.info('Config batch_size: `%s`', self.batch_size)
        self.logger.info('Config date_format: `%s`', self.date_format)
        self.logger.info('Config cid: `%r`', self.cid)

    def set_client(self):

        repo_dir = os.path.join(os.path.abspath(os.path.join(self.server)), 'config', 'repo')
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
            if self.channel.lower() not in item.name.lower():
                continue

            config = self.client.invoke('zato.http-soap.get-audit-config', {'id':item.id}).data
            config.service_id = item.id
            config.service_name = item.service_name
            config.channel = item.name
            seen_any = True
            yield config

        if not seen_any:
            self.logger.warn('No channels matching pattern `%s`', self.channel)
            sys.exit(exit_code.no_channel_match)

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
            response = self.client.invoke('zato.http-soap.set-audit-state', {'id':item.service_id, 'audit_enabled':enable})
            if not response.ok:
                self.logger.error(response.details)
                sys.exit(exit_code.invoke_error)
            self.logger.info('%s audit log for `%s`' % (verb, item.name))

    def enable(self):
        self._set_state()

    def disable(self):
        self._set_state(False)

    def search(self):
        result = []
        for item in self.get_items():
            if item.audit_enabled:
                response = self.client.invoke(
                    'zato.http-soap.get-audit-item-list',
                    {'conn_id':item.service_id, 'query':self.query, 'batch_size':self.batch_size})
                if response.ok:

                    len_data = len(response.data)
                    noun = 'item' if len_data == 1 else 'items'
                    self.logger.info('%s %s found in `%s`', len_data, noun, item.service_name)

                    for audit_item in response.data:
                        audit_item.channel = item.channel
                        audit_item.aid = audit_item.id

                    result.extend(response.data)

                else:
                    self.logger.error(response.details)
                    sys.exit(exit_code.invoke_error)

        if not result:
            self.logger.info('No results')
            sys.exit(exit_code.no_search_match)

        len_result = len(result)
        noun = 'item' if len_result == 1 else 'items'
        self.logger.info('%s %s found in total', len_result, noun)

        table = Texttable(150)
        table.set_cols_dtype(['t', 't', 't', 't', 't', 't',])

        rows = [['#', 'req_time_utc', 'resp_time_utc', 'channel', 'cid', 'aid']]
        for idx, item in enumerate(sorted(result, key=itemgetter(self.order_by)), 1):
            req_time_utc = arrow_get(item.req_time_utc).strftime(self.date_format)
            resp_time_utc = arrow_get(item.resp_time_utc).strftime(self.date_format)
            rows.append((idx, req_time_utc, resp_time_utc, item.channel, item.cid, item.aid))

        table.add_rows(rows)
        print(table.draw())

# ################################################################################################################################

@click.group()
def cli_main():
    pass

# ################################################################################################################################

def get_arg(name):

    def _cli_arg(ctx, server, channel, query=None, order_by=None, batch_size=None, date_format=None, cid=None):
        tool = AuditLogTool(server, channel, query, order_by, batch_size, date_format, cid)
        tool.set_client()
        getattr(tool, name)()

    _cli_arg = click.pass_context(_cli_arg)

    if name == 'search':
        _cli_arg = click.option('--date-format', default='%Y-%m-%d %H:%M:%S')(_cli_arg)
        _cli_arg = click.option('--order-by', default='req_time_utc')(_cli_arg)
        _cli_arg = click.option('--batch-size', default=100)(_cli_arg)
        _cli_arg = click.argument('query', default='')(_cli_arg)

    elif name == 'get':
        _cli_arg = click.argument('cid', required=True)(_cli_arg)

    _cli_arg = click.argument('channel', required=True)(_cli_arg)
    _cli_arg = click.argument('server', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))(_cli_arg)

    _cli_arg = click.command()(_cli_arg)

    return _cli_arg

# ################################################################################################################################

for name in ('enable', 'disable', 'status', 'search'):
    cli_main.add_command(get_arg(name), name)

# ################################################################################################################################

if __name__ == '__main__':
    cli_main()

# ################################################################################################################################
