# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import argparse, logging, os, sys
from contextlib import closing
from copy import deepcopy
from datetime import datetime
from itertools import chain
from json import dumps
from os.path import abspath, exists, join
from traceback import format_exc

# anyjson
from anyjson import loads

# Bunch
from bunch import Bunch, bunchify

# Pip
from pip import download

# Texttable
from texttable import Texttable

# Zato
from zato.cli import ManageCommand, ZATO_INFO_FILE
from zato.cli.check_config import CheckConfig
from zato.cli.zato_command import add_opts, get_parser
from zato.client import AnyServiceInvoker
from zato.common.crypto import CryptoManager
from zato.common.odb.model import ConnDefAMQP, ConnDefWMQ, HTTPBasicAuth, \
     HTTPSOAP, SecurityBase, Server, Service, TechnicalAccount, to_json, WSSDefinition
from zato.common.util import get_config

"""
channel-amqp
channel-jms-wmq
channel-plain-http
channel-soap
channel-zmq
def-amqp
def-jms-wmq
def-sec
outconn-amqp
outconn-ftp
outconn-jms-wmq
outconn-plain-http
outconn-soap
outconn-sql
outconn-zmq
"""

DEFAULT_COLS_WIDTH = '15,100'

class _DummyLink(object):
    """ Pip requires URLs to have a .url attribute.
    """
    def __init__(self, url):
        self.url = url

class Warning(object):
    def __init__(self, value_raw, value):
        self.value_raw = value_raw
        self.value = value
        
class Error(object):
    def __init__(self, value_raw, value):
        self.value_raw = value_raw
        self.value = value

class Results(object):
    def __init__(self, warnings, errors):
        self.warnings = warnings
        self.errors = errors

    def _get_ok(self):
        return not(self.warnings or self.errors)
    
    ok = property(_get_ok)
    
class ZatoClient(AnyServiceInvoker):
    def __init__(self, *args, **kwargs):
        super(ZatoClient, self).__init__(*args, **kwargs)
        self.cluster_id = None
        self.odb_session = None
    
class EnMasse(ManageCommand):
    """ Creates server objects en masse.
    """
    # TODO: Ping outgoing connections (at least check ports)
    # TODO: --delete-all-first must never delete Zato stuff
    # TODO: Make sure any new connector-based connections are not active by default

    class SYS_ERROR(ManageCommand.SYS_ERROR):
        NO_INPUT = 11
        CONFLICTING_OPTIONS = 12
        NO_OPTIONS = 13
        INVALID_INPUT = 14
        
    def _on_server(self, args):
        
        self.args = args
        self.curdir = self.args.curdir
        self.force_override = self.args.f
        self.has_import = getattr(args, 'import')
        self.json = None
        
        self.odb_objects = Bunch()
        self.objects = Bunch()
        
        # 
        # Tasks and scenarios
        #
        # 1) Export all local JSON files into one (--export-local)
        # 2) Export all definitions from ODB (--export-odb)
        # -> 3) Export all local JSON files with ODB definitions merged into one (--export-local --export-odb):
        #    3a) bail out if local JSON overrides any from ODB (no -f)
        #    3b) override whatever is found in ODB with values from JSON (-f)
        # -> 4) Import definitions from a local JSON file (--import)
        #    4a) delete all ODB definitions before importing a local JSON (--delete-all-odb-first)
        #    4b) bail out if local JSON overrides any from ODB (no -f)
        #    4c) override whatever is found in ODB with values from JSON (-f)
        #
        
        # Imports and export are mutually excluding
        if self.has_import and (args.export_local or args.export_odb):
            self.logger.error('Cannot specify import and export options at the same time, stopping now')
            sys.exit(self.SYS_ERROR.CONFLICTING_OPTIONS)

        if args.export_local:
            input_path = self.ensure_input_exists()
            self.json = bunchify(loads(open(input_path).read()))
            
            # Local JSON sanity check first
            json_sanity_results = self.json_sanity_check()
            if not json_sanity_results.ok:
                self.logger.error('JSON sanity check failed')        
                self.report_warnings_errors([json_sanity_results])
                sys.exit(self.SYS_ERROR.INVALID_INPUT)
            
        # 3) a/b
        if args.export_local and args.export_odb:
            self.export_local_odb()
            
        # 1)
        elif args.export_local:
            if self.report_warnings_errors(self.export_local()):
                self.save_json()
            
        # 2)
        elif args.export_odb:
            self.export_odb()
           
        # 4) a/b/c
        elif self.has_import:
            self.import_()
            
        else:
            self.logger.error('At least one of --export-local, --export-odb or --import is required, stopping now')
            sys.exit(self.SYS_ERROR.NO_OPTIONS)
        
        '''
        # Checks if connections to ODB/Redis are configured properly
        cc = CheckConfig(self.args)
        cc.show_output = False
        cc.execute(self.args)

        # Get client and issue a sanity check as quickly as possible
        self.set_client()
        self.client.invoke('zato.ping')
        
        if self.args.input:
            input_path = self.ensure_input_exists()
            self.json = bunchify(loads(open(input_path).read()))
            
            self.grab_odb_objects()
            
            warn_err, warn_no, error_no = self.run_local_json()
            if warn_err:
                self.report_warnings_errors(warn_err, warn_no, error_no)
                
        self.client.session.close()
        self.logger.info('All checks OK')
        '''

# ##############################################################################

    def save_json(self):
        now = datetime.now().isoformat() # Not in UTC, we want to use user's TZ
        name = 'zato-export-{}.json'.format(now.replace(':', '_').replace('.', '_'))
        
        f = open(join(self.curdir, name), 'w')
        f.write(dumps(self.json, indent=1, sort_keys=True))
        f.close()
        
        self.logger.info('Data exported to {}'.format(f.name))
        
# ##############################################################################
        
    def set_client(self):
        #
        # TODO: Much of it is copy/pasted from 'zato invoke', this needs to be refactored
        #       before 'zato enmasse' gets into the core.
        #
        
        repo_dir = os.path.join(os.path.abspath(os.path.join(self.args.path)), 'config', 'repo')
        config = get_config(repo_dir, 'server.conf')
        
        priv_key_location = os.path.abspath(os.path.join(repo_dir, config.crypto.priv_key_location))
        
        cm = CryptoManager(priv_key_location=priv_key_location)
        cm.load_keys()
        
        engine_args = Bunch()
        engine_args.odb_type = config.odb.engine
        engine_args.odb_user = config.odb.username
        engine_args.odb_password = cm.decrypt(config.odb.password)
        engine_args.odb_host = config.odb.host
        engine_args.odb_db_name = config.odb.db_name
        
        engine = self._get_engine(engine_args)
        session = self._get_session(engine)
        
        auth = None
        with closing(session) as session:
            cluster = session.query(Server).\
                filter(Server.token == config.main.token).\
                one().cluster
            
            channel = session.query(HTTPSOAP).\
                filter(HTTPSOAP.cluster_id == cluster.id).\
                filter(HTTPSOAP.url_path == '/zato/admin/invoke').\
                one()
            
            if channel.security_id:
                security = session.query(HTTPBasicAuth).\
                    filter(HTTPBasicAuth.id == channel.security_id).\
                    first()
                
                if security:
                    auth = (security.username, security.password)
                    
        self.client = ZatoClient('http://{}'.format(config.main.gunicorn_bind), 
            '/zato/admin/invoke', auth, max_response_repr=15000)
        
        self.client.cluster_id = session.query(Server).\
            filter(Server.token == config.main.token).\
            one().cluster_id
        
        self.client.odb_session = session
        
# ##############################################################################

    def ensure_input_exists(self):
        input_path = abspath(join(self.curdir, self.args.input))
        if not exists(input_path):
            self.logger.error('No such path: [{}]'.format(input_path))

            # TODO: ManageCommand should not ignore exit codes subclasses return
            sys.exit(self.SYS_ERROR.NO_INPUT)
            
        return input_path

# ##############################################################################
    
    def get_warnings_errors(self, items):
        
        warn_idx = 1
        error_idx = 1
        warn_err = {}
        
        for item in items:

            for warning in item.warnings:
                warn_err['warn{:04}'.format(warn_idx)] = warning.value
                warn_idx += 1
                
            for error in item.errors:
                warn_err['error{:04}'.format(error_idx)] = error.value
                error_idx += 1
                
        warn_no = warn_idx-1
        error_no = error_idx-1
                
        return warn_err, warn_no, error_no
            
    def report_warnings_errors(self, items):

        warn_err, warn_no, error_no = self.get_warnings_errors(items)
        table = self.get_table(warn_err)        
        
        warn_plural = '' if warn_no == 1 else 's'
        error_plural = '' if error_no == 1 else 's'
        
        if warn_no or error_no:
            if error_no:
                level = logging.ERROR
            else:
                level = logging.WARN
                
            prefix = '{} warning{} and {} error{} found:\n'.format(warn_no, warn_plural, error_no, error_plural)
            self.logger.log(level, prefix + table.draw())
        
        else:
            # A signal that we found no warnings nor errors
            return True

# ##############################################################################

    def get_table(self, out):
        
        cols_width = self.args.cols_width if self.args.cols_width else DEFAULT_COLS_WIDTH
        cols_width = (elem.strip() for elem in cols_width.split(','))
        cols_width = [int(elem) for elem in cols_width]
        
        table = Texttable()
        table.set_cols_width(cols_width)
        
        # Use text ('t') instead of auto so that boolean values don't get converted into ints
        table.set_cols_dtype(['t', 't']) 
        
        rows = [['Key', 'Value']]
        rows.extend(sorted(out.items()))
        
        table.add_rows(rows)
        
        return table
                
# ##############################################################################

    def get_include_abspath(self, curdir, value):
        return abspath(join(curdir, value.replace('file://', '')))
    
    def is_include(self, value):
        return isinstance(value, basestring)

    def get_json_includes(self):
        for key in sorted(self.json):
            for value in self.json[key]:
                if self.is_include(value):
                    yield key, value
                
    def json_find_include_dups(self):
        seen_includes = {}
        
        for key, value in self.get_json_includes():
            keys = seen_includes.setdefault(value, [])
            keys.append(key)
            
        dups = dict((k,v) for (k,v) in seen_includes.items() if len(v) > 1)
            
        return dups
    
    def json_find_missing_includes(self):
        missing = {}
        for key in sorted(self.json):
            for value in self.json[key]:
                if self.is_include(value):
                    if download.is_file_url(_DummyLink(value)):
                        abs_path = self.get_include_abspath(self.curdir, value)
                        if not exists(abs_path):
                            item = missing.setdefault((value, abs_path), [])
                            item.append(key)
        return missing
    
    def json_find_unparsable_includes(self, missing):
        unparsable = {}
        
        for key in sorted(self.json):
            for value in self.json[key]:
                if self.is_include(value):
                    if download.is_file_url(_DummyLink(value)):
                        abs_path = self.get_include_abspath(self.curdir, value)
                        
                        # No point in parsing what is already known not to exist
                        if abs_path not in missing:
                            try:
                                loads(open(abs_path).read())
                            except Exception, e:
                                exc_pretty = format_exc(e)
                                
                                item = unparsable.setdefault((value, abs_path, exc_pretty), [])
                                item.append(key)

        return unparsable
            
    def json_sanity_check(self):
        warnings = []
        errors = []
        
        for raw, keys in sorted(self.json_find_include_dups().items()):
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} included multiple times ({}) \n{}'.format(
                raw, len_keys, '\n'.join(' - {}'.format(name) for name in keys))
            errors.append(Error(raw, value))
            
        missing_items = sorted(self.json_find_missing_includes().items())
        for raw, keys in missing_items:
            missing, missing_abs = raw
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} ({}) missing but needed in multiple definitions ({}) \n{}'.format(
                missing, missing_abs, len_keys, '\n'.join(' - {}'.format(name) for name in keys))
            errors.append(Error(raw, value))
            
        unparsable = self.json_find_unparsable_includes([elem[0][1] for elem in missing_items])
        for raw, keys in unparsable.items():
            include, abs_path, exc_pretty = raw
            len_keys = len(keys)
            suffix = '' if len_keys == 1 else 's'
            keys = sorted(set(keys))
            value = '{} ({}) could not be parsed as JSON, used in ({}) definition{}\n{} \n{}'.format(
                include, abs_path, len_keys, suffix, '\n'.join(' - {}'.format(name) for name in keys), exc_pretty)
            errors.append(Error(raw, value))
            
        return Results(warnings, errors)
    
    def merge_includes(self):
        json_with_includes = Bunch()
        for key, values in self.json.items():
            values_with_includes = json_with_includes.setdefault(key, [])
            for value in values:
                if self.is_include(value):
                    abs_path = self.get_include_abspath(self.curdir, value)
                    include = Bunch(loads(open(abs_path).read()))
                    values_with_includes.append(include)
                else:
                    values_with_includes.append(value)
                    
        self.json = json_with_includes
        
    def merge_odb_json(self):
        merged = deepcopy(self.odb_objects)
        
        for json_key, json_elems in self.json.items():
            if 'http' in json_key or 'soap' in json_key:
                odb_key = 'http_soap'
            else:
                odb_key = json_key.replace('-', '_')
            for json_elem in json_elems:
                if 'http' in json_key or 'soap' in json_key:
                    connection, transport = json_key.split('-', 1)
                    connection = 'outgoing' if connection == 'outconn' else connection
                    transport = transport.replace('-', '_')
                    
                    for odb_elem in merged.http_soap:
                        if odb_elem.get('transport') == transport and odb_elem.get('connection') == connection:
                            if odb_elem.name == json_elem.name:
                                merged.http_soap.remove(odb_elem)
                else:
                    for odb_elem in merged[odb_key]:
                        if odb_elem.name == json_elem.name:
                            merged[odb_key].remove(odb_elem)
                merged[odb_key].append(json_elem)
                    
        self.json = merged
    
# ##############################################################################

    def grab_odb_objects(self):
        
        def get_fields(model):
            return Bunch(loads(to_json(item))[0]['fields'])
        
        self.odb_objects.def_sec = []
        self.odb_objects.def_amqp = []
        self.odb_objects.http_soap = []
        
        basic_auth = self.client.odb_session.query(HTTPBasicAuth).\
            filter(HTTPBasicAuth.cluster_id == self.client.cluster_id)
            
        tech_acc = self.client.odb_session.query(TechnicalAccount).\
            filter(TechnicalAccount.cluster_id == self.client.cluster_id)
        
        wss = self.client.odb_session.query(WSSDefinition).\
            filter(WSSDefinition.cluster_id == self.client.cluster_id)
        
        for query in(basic_auth, tech_acc, wss):
            for item in query.all():
                self.odb_objects.def_sec.append(get_fields(item))
                
        for item in self.client.odb_session.query(ConnDefAMQP).\
            filter(ConnDefAMQP.cluster_id == self.client.cluster_id).all():
            self.odb_objects.def_amqp.append(get_fields(item))
            
        for item in self.client.odb_session.query(HTTPSOAP).\
            filter(HTTPSOAP.cluster_id == self.client.cluster_id).all():
            self.odb_objects.http_soap.append(get_fields(item))

        service_key = {
            'zato.channel.amqp.get-list':'channel_amqp',
            'zato.channel.jms-wmq.get-list':'channel_jms_wmq',
            'zato.channel.zmq.get-list':'channel_zmq',
            'zato.definition.jms-wmq.get-list':'def_jms_wmq',
            'zato.outgoing.amqp.get-list':'outconn_amqp',
            'zato.outgoing.ftp.get-list':'outconn_ftp',
            'zato.outgoing.jms-wmq.get-list':'outconn_jms_wmq',
            'zato.outgoing.sql.get-list':'outconn_sql',
            'zato.outgoing.zmq.get-list':'outconn_zmq',
            'zato.scheduler.job.get-list':'scheduler',
            }
        
        for value in service_key.values():
            self.odb_objects[value] = []
        
        for service, key in service_key.items():
            response = self.client.invoke(service, {'cluster_id':self.client.cluster_id})
            if response.ok:
                for item in response.data:
                    self.odb_objects[key].append(Bunch(item))
    
# ##############################################################################
    
    def find_overrides(self):
        warnings = []
        errors = []
        
        def add_warning(key, value_dict, item):
            raw = (key, value_dict)
            msg = '{} already exists in ODB {} ({})'.format(value_dict.toDict(), item.toDict(), key)
            warnings.append(Warning(raw, msg))
        
        for key, values in self.json.items():
            for value_dict in values:
                value_name = value_dict.get('name')
                if not value_name:
                    raw = (key, value_dict)
                    msg = "{} has no 'name' key ({})".format(value_dict.toDict(), key)
                    errors.append(Error(raw, msg))

                if 'http' in key or 'soap' in key:
                    connection, transport = key.split('-', 1)
                    connection = 'outgoing' if connection == 'outconn' else connection
                    transport = transport.replace('-', '_')
                    
                    for item in self.odb_objects.http_soap:
                        if connection == item.connection and transport == item.transport:
                            if value_name == item.name:
                                add_warning(key, value_dict, item)
                                
                else:
                    odb_defs = self.odb_objects[key.replace('-', '_')]
                    for odb_def in odb_defs:
                        if odb_def.name == value_name:
                            add_warning(key, value_dict, odb_def)
                
        return Results(warnings, errors)
    
# ##############################################################################

    def find_missing_defs(self, json):
        
        def get_needed_sec_defs(json):
            for key in json:
                if 'plain-http' in key or 'soap' in key:
                    for item in json[key]:
                        #yield item.get('sec-def', None)
                        #print(item, type(item))
                        pass
                        
            return []
        
        def get_needed_amqp_defs(json):
            pass
        
        def get_needed_jms_wmq_defs(json):
            pass

# ##############################################################################

    def export_local(self):
        
        # Merge all includes into local JSON
        self.merge_includes()
        self.logger.info('Includes merged in successfully')
        
        # Find any definitions that are missing even after merging
        missing_defs = self.find_missing_defs(self.json)
        if missing_defs:
            self.logger.error('Failed to find all definitions needed')        
            return [missing_defs]
        
        # Find channels that require services that don't exist
        
        # Find jobs that require services that don't exist
        
        # As a sanity check, validate again if every required
        # input element has been specified.
        
        return []
    
    def export_local_odb(self):
        # Merge all includes into local JSON
        #self.merge_includes()
        #self.logger.info('Includes merged in successfully')        

        '''        
        # Check if local JSON wants to overrite anything already defined in ODB.
        # Fail if it does and -f (force) is not set.
        

        overrides_results = self.find_overrides()
        if not overrides_results.ok:
            
            if overrides_results.errors:
                return [overrides_results]
            
            elif overrides_results.warnings:
                self.logger.info('Found overrides')
                
                if not self.force_override:
                    self.logger.error('No -f flag set and overrides found, stopping now')
                    overrides_results.errors = overrides_results.errors + overrides_results.warnings
                    overrides_results.warnings[:] = []
                    return [overrides_results]
                else:
                    self.logger.info('-f flag set, will override ODB objects')
        
        # Merge local JSON with what was pulled from ODB
        self.merge_odb_json()
        '''
        
# ##############################################################################

def main():
    parser = argparse.ArgumentParser(add_help=True, description=EnMasse.__doc__)
    parser.add_argument('--store-log', help='Whether to store an execution log', action='store_true')
    parser.add_argument('--verbose', help='Show verbose output', action='store_true')
    parser.add_argument('--store-config', 
        help='Whether to store config options in a file for a later use', action='store_true')
    parser.add_argument('--export-local', help='Export local JSON definitions into one file (can be used with --export-odb)', action='store_true')
    parser.add_argument('--export-odb', help='Export ODB definitions into one file (can be used with --export-local)', action='store_true')
    parser.add_argument('--import', help='Import definitions from a local JSON (excludes --export-*)', action='store_true')
    parser.add_argument('--delete-all-odb-first', help='Deletes all existing objects before new ones are created', action='store_true')
    parser.add_argument('-f', help='Force replacing objects already existing in ODB', action='store_true')
    parser.add_argument('--input', help="Path to an input JSON document")
    parser.add_argument('--cols_width', help='A list of columns width to use for the table output, default: {}'.format(DEFAULT_COLS_WIDTH))
    parser.add_argument('--path', help='Path to a running Zato server')
    
    add_opts(parser, EnMasse.opts)

    args = parser.parse_args()
    args.curdir = abspath(os.getcwd())
    
    EnMasse(args).run(args)

if __name__ == '__main__':
    main()