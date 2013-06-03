# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import argparse, os, sys
from os.path import abspath, exists, join

# anyjson
from anyjson import loads

# Bunch
from bunch import bunchify

# Texttable
from texttable import Texttable

# Zato
from zato.cli import ManageCommand, ZATO_INFO_FILE
from zato.cli.check_config import CheckConfig
from zato.cli.zato_command import add_opts, get_parser

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
    class SYS_ERROR(ManageCommand.SYS_ERROR):
        NO_INPUT = 11
        
    def _on_server(self, args):
        
        # Sanity check
        cc= CheckConfig(args)
        cc.show_output = False
        cc.execute(args)
        
        # TODO: Check if JSON doesn't define anything twice
        # TODO: Ping outgoing connections (at least check ports)
        
        # TODO: --delete-all-first must never delete Zato stuff
        
        # TODO: Warn on duplicate includes
        
        if args.input:
            input_path = abspath(join(args.curdir, args.input))
            if not exists(input_path):
                self.logger.error('No such path: [{}]'.format(input_path))

                # TODO: ManageCommand should not ignore returned exit codes
                sys.exit(self.SYS_ERROR.NO_INPUT)
                
            json = bunchify(loads(open(input_path).read()))
            results = self.json_sanity_check(json)
            if results.ok:
                print(results)
                
            else:
                
                out = {}
                
                for idx, warning in enumerate(results.warnings, 1):
                    out['warn{}'.format(idx)] = warning.value
                    
                for idx, error in enumerate(results.errors, 1):
                    out['error{}'.format(idx)] = warning.value

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
                
                self.logger.info(table.draw())
                
    def json_find_include_dups(self, json):
        
        # Find duplicate includes first
        seen_includes = []
        duplicate_includes = []
        
        for key in sorted(json):
            for value in json[key]:
                if isinstance(value, basestring):
                    if value in seen_includes:
                        duplicate_includes.append((key, value))
                    seen_includes.append(value)
                    
        dups = {}
        for key, value in duplicate_includes:
            dup_keys = dups.setdefault(value, [])
            dup_keys.append(key)
            
        return dups
            
    def json_sanity_check(self, json):
        warnings = []
        errors = []
        
        for dup, keys in self.json_find_include_dups(json).items():
            len_keys = len(keys)
            keys = sorted(set(keys))
            value = '{} included multiple times ({}) \n{}'.format(dup, len_keys, '\n'.join(' - {}'.format(name) for name in keys))
            warnings.append(Warning(dup, value))
            
        return Results(warnings, errors)

def main():
    parser = argparse.ArgumentParser(add_help=True, description=EnMasse.__doc__)
    parser.add_argument('--store-log', help='Whether to store an execution log', action='store_true')
    parser.add_argument('--verbose', help='Show verbose output', action='store_true')
    parser.add_argument('--store-config', 
        help='Whether to store config options in a file for a later use', action='store_true')
    parser.add_argument('-i', help='Run in interactive mode. Can be used with --dry-run. Excludes -f.', action='store_true')
    parser.add_argument('--collect-only', help='Only create a single JSON document containing all objects', action='store_true')
    parser.add_argument('--delete-all-first', help='Deletes all existing objects before new ones are created', action='store_true')
    parser.add_argument('-f', help='Force replacing already existing objects. Excludes -i.', action='store_true')
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