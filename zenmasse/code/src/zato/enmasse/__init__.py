# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import argparse, logging, os, sys
from os.path import abspath, exists, join
from itertools import chain
from traceback import format_exc

# anyjson
from anyjson import loads

# Bunch
from bunch import bunchify

# Pip
from pip import download

# Texttable
from texttable import Texttable

# Zato
from zato.cli import ManageCommand, ZATO_INFO_FILE
from zato.cli.check_config import CheckConfig
from zato.cli.zato_command import add_opts, get_parser
from zato.client import AnyServiceInvoker

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

class ZatoClient(AnyServiceInvoker):
    def __init__(self, server_conf):
        self.server_conf = server_conf

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
    
class EnMasse(ManageCommand):
    """ Creates server objects en masse.
    """
    # TODO: Ping outgoing connections (at least check ports)
    # TODO: --delete-all-first must never delete Zato stuff

    class SYS_ERROR(ManageCommand.SYS_ERROR):
        NO_INPUT = 11
        
    def _on_server(self, args):
        
        # Checks if connections to ODB/Redis are configured properly
        cc= CheckConfig(args)
        cc.show_output = False
        cc.execute(args)
        
        if args.input:
            input_path = self.ensure_input_exists(args)
            json = bunchify(loads(open(input_path).read()))
            
            warn_err, warn_no, error_no = self.find_warnings_errors(args, json)
            if warn_err:
                self.report_warnings_errors(args, warn_err, warn_no, error_no)
                
        self.logger.info('All checks OK')

# ##############################################################################

    def ensure_input_exists(self, args):
        input_path = abspath(join(args.curdir, args.input))
        if not exists(input_path):
            self.logger.error('No such path: [{}]'.format(input_path))

            # TODO: ManageCommand should not ignore exit codes subclasses return
            sys.exit(self.SYS_ERROR.NO_INPUT)
            
        return input_path

# ##############################################################################
    
    def find_warnings_errors(self, args, json):
        
        warn_idx = 1
        error_idx = 1
        warn_err = {}
        
        for item in self.sanity_check(args, json):

            for warning in item.warnings:
                warn_err['warn{:04}'.format(warn_idx)] = warning.value
                warn_idx += 1
                
            for error in item.errors:
                warn_err['error{:04}'.format(error_idx)] = error.value
                error_idx += 1
                
        warn_no = warn_idx-1
        error_no = error_idx-1
                
        return warn_err, warn_no, error_no
            
    def report_warnings_errors(self, args, warn_err, warn_no, error_no):

        table = self.get_table(args, warn_err)        
        
        warn_plural = '' if warn_no == 1 else 's'
        error_plural = '' if error_no == 1 else 's'
        
        if warn_no or error_no:
            if error_no:
                level = logging.ERROR
            else:
                level = logging.WARN
                
            prefix = '{} warning{} and {} error{} found:\n'.format(warn_no, warn_plural, error_no, error_plural)
            self.logger.log(level, prefix + table.draw())

# ##############################################################################

    def get_table(self, args, out):
        
        cols_width = args.cols_width if args.cols_width else DEFAULT_COLS_WIDTH
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

    def _get_json_includes(self, json):
        for key in sorted(json):
            for value in json[key]:
                if isinstance(value, basestring):
                    yield key, value
                
    def json_find_include_dups(self, json):
        seen_includes = []
        duplicate_includes = []
        
        for key, value in self._get_json_includes(json):
            if value in seen_includes:
                duplicate_includes.append((key, value))
            seen_includes.append(value)
                    
        dups = {}
        for key, value in duplicate_includes:
            dup_keys = dups.setdefault(value, [])
            dup_keys.append(key)
            
        return dups
    
    def json_find_missing_includes(self, curdir, json):
        missing = {}
        for key in sorted(json):
            for value in json[key]:
                if isinstance(value, basestring):
                    if download.is_file_url(_DummyLink(value)):
                        abs_path = abspath(join(curdir, value.replace('file://', '')))
                        if not exists(abs_path):
                            item = missing.setdefault((value, abs_path), [])
                            item.append(key)
        return missing
    
    def json_find_unparsable_includes(self, curdir, json, missing):
        unparsable = {}
        
        for key in sorted(json):
            for value in json[key]:
                if isinstance(value, basestring):
                    if download.is_file_url(_DummyLink(value)):
                        abs_path = abspath(join(curdir, value.replace('file://', '')))
                        
                        # No point in parsing what is already known not to exist
                        if abs_path not in missing:
                            try:
                                loads(open(abs_path).read())
                            except Exception, e:
                                exc_pretty = format_exc(e)
                                
                                item = unparsable.setdefault((value, abs_path, exc_pretty), [])
                                item.append(key)

        return unparsable
            
    def json_sanity_check(self, args, json):
        warnings = []
        errors = []
        
        for raw, keys in sorted(self.json_find_include_dups(json).items()):
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} included multiple times ({}) \n{}'.format(raw, len_keys, '\n'.join(' - {}'.format(name) for name in keys))
            errors.append(Error(raw, value))
            
        missing_items = sorted(self.json_find_missing_includes(args.curdir, json).items())
        for raw, keys in missing_items:
            missing, missing_abs = raw
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} ({}) not found but defined ({}) \n{}'.format(missing, missing_abs, len_keys, '\n'.join(' - {}'.format(name) for name in keys))
            errors.append(Error(raw, value))
            
        unparsable = self.json_find_unparsable_includes(args.curdir, json, [elem[0][1] for elem in missing_items])
        for raw, keys in unparsable.items():
            include, abs_path, exc_pretty = raw
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} ({}) could not be parsed as JSON, used in ({})\n{} \n{}'.format(
                include, abs_path, len_keys, '\n'.join(' - {}'.format(name) for name in keys), exc_pretty)
            errors.append(Error(raw, value))
            
        return Results(warnings, errors)
    
# ##############################################################################

    def find_missing_defs(self, json):
        missing = []
        
        return Results([], [])

# ##############################################################################

    def sanity_check(self, args, json):
        
        # Local JSON sanity check first
        json_results = self.json_sanity_check(args, json)
        if json_results:
            self.logger.error('JSON sanity check failed')        
            return [json_results]
        
        # Grab everything from ODB and check if local JSON wants to overrite anything.
        # Fail if it does and -f (force) is not set.
        
        missing_auth = self.find_missing_auth(json)
        
        return [json_results, missing_auth]

# ##############################################################################

def main():
    parser = argparse.ArgumentParser(add_help=True, description=EnMasse.__doc__)
    parser.add_argument('--store-log', help='Whether to store an execution log', action='store_true')
    parser.add_argument('--verbose', help='Show verbose output', action='store_true')
    parser.add_argument('--store-config', 
        help='Whether to store config options in a file for a later use', action='store_true')
    parser.add_argument('--collect-only', help='Only create a single JSON document containing all objects', action='store_true')
    parser.add_argument('--delete-all-first', help='Deletes all existing objects before new ones are created', action='store_true')
    parser.add_argument('-f', help='Force replacing objects already existing in ODB', action='store_true')
    parser.add_argument('--dry-run', help="Don't really do anything, only show what will be done. Can be used with -i.", action='store_true')
    parser.add_argument('--input', help="Path to an input JSON document")
    parser.add_argument('--cols_width', help='A list of columns width to use for the table output, default: {}'.format(DEFAULT_COLS_WIDTH))
    
    parser.add_argument('path', help='Path to a running Zato server')
    add_opts(parser, EnMasse.opts)

    args = parser.parse_args()
    args.curdir = abspath(os.getcwd())
    
    EnMasse(args).run(args)

if __name__ == '__main__':
    main()