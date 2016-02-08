# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from copy import deepcopy
from cStringIO import StringIO
from datetime import datetime
from logging import getLogger
from uuid import uuid4
import os

# Arrow
from arrow import get as arrow_get

# Bunch
from bunch import Bunch

# ConfigObj
from configobj import ConfigObj

# pyrapidjson
from rapidjson import dumps, loads

# PyTZ
import pytz

# zato-labs
try:
    from zato.bst.sql import Group, Item, label, SubGroup
except ImportError:
    from zato_bst_sql import Group, Item, label, SubGroup

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

class CONST:
    NO_SUCH_NODE = 'NO_SUCH_NODE'
    DEFAULT_DIAG_DT_FORMAT = '%a %d/%m/%y %H:%M:%S'
    DEFAULT_DIAG_TZ = 'UTC'
    DEFAULT_GRAPH_VERSION = 1
    PRETTY_PRINT_REPLACE = {
        'Force stop:': 'force_stop=',
        'Objects:': 'objects=',
        'Version:': 'version=',
    }

# ################################################################################################################################

class TransitionError(Exception):
    pass

# ################################################################################################################################

def validate_from_to(func):
    """ Makes sure that both from_ and to are valid node names.
    """
    def _inner(self, from_, to):
        for node in (from_, to):
            if node not in self.nodes:
                return AddEdgeResult(False, CONST.NO_SUCH_NODE, node)
        return func(self, from_, to)
    return _inner

# ################################################################################################################################

def parse_pretty_print(value):

    value = value.splitlines()
    out = StringIO()
    sep_idx = None

    for idx, line in enumerate(value):
        if line.strip().startswith('-'):
            sep_idx = idx
            break
    else:
        raise ValueError('Could not find header separator in `{}`'.format(value))

    header = '[{}]'.format(value[sep_idx-1].strip())
    items = [item.strip() for item in value[sep_idx+1:] if item]

    out.write('{}\n'.format(header))

    for item in items:

        # Ignore comments
        if item.startswith('#'):
            continue

        for source, target in CONST.PRETTY_PRINT_REPLACE.items():
            if item.startswith(source):
                item = item.replace(source, target)
        item = item.replace(': ', '=', 1).replace(':', '=', 1).replace('= ', '=', 1)
        out.write('{}\n'.format(item))

    value = out.getvalue()
    out.close()

    return value.strip()

# ################################################################################################################################

def yield_definitions(service):

    bst_dir = os.path.join(service.server.base_dir, 'config', 'repo', 'proc', 'bst')
    for name in os.listdir(bst_dir):
        full_name = os.path.join(bst_dir, name)
        value = ConfigObj(parse_pretty_print(open(full_name).read()).splitlines())

        for key, value in value.items():
            yield key, value

# ################################################################################################################################

def setup_server_config(service):
    config = {}
    for name, data in yield_definitions(service):
        # .. parse the definition and append to the state machine's config dict
        item = ConfigItem()
        item.parse_config_dict({name:data})
        config[item.def_.tag] = item

    service.server.user_ctx.zato_state_machine = StateMachine(config, RedisBackend(service.kvdb.conn))

# ################################################################################################################################

class AddEdgeResult(object):
    """ A boolean result of adding an edge between nodes. Includes error code if the operation failed.
    """
    def __init__(self, is_ok=True, error_code=None, details=None):
        self.is_ok = is_ok
        self.error_code = error_code
        self.details = details

    def __nonzero__(self):
        return self.is_ok

# ################################################################################################################################

class Node(object):
    """ An individual node in a graph.
    """
    def __init__(self, name, data=None):
        self.name = name
        self.data = data
        self.edges = set()

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __str__(self):
        return '{}: {}'.format(self.__class__.__name__, self.name)

    def add_edge(self, to):
        self.edges.add(to)

    def has_edge(self, to):
        return to in self.edges

# ################################################################################################################################

class Definition(object):
    """ A graph of nodes and edges connecting them. Edges can be cyclic and graphs can have more than one root.
    """
    def __init__(self, name=None, version=CONST.DEFAULT_GRAPH_VERSION):
        self.name = Definition.get_name(name)
        self.version = version
        self.tag = self.get_tag(self.name, self.version)
        self.nodes = {}
        self._non_root = set()
        self._roots = None

    def __str__(self):
        roots = self.roots
        edges = []
        nodes = []
        _roots = []

        for node in sorted(self.nodes.values()):
            name = node.name
            if name in roots:
                _roots.append('~{}'.format(name))
            else:
                nodes.append(name)

        _roots.sort()
        _roots.reverse()

        for root in _roots:
            nodes.insert(0, root)

        _nodes = ', '.join(nodes)

        max_name = 0
        for name in nodes:
            max_name = max(max_name, len(name))

        node_format = ' * {:<'+ str(max_name) +'} -> {}'

        for name in nodes:
            edges.append(node_format.format(name, ', '.join(sorted(self.nodes[name.replace('~', '')].edges)) or '(None)'))

        return '{} {} v{}: {}\n{}'.format(self.__class__.__name__, self.name, self.version, _nodes, '\n'.join(edges))

    @staticmethod
    def get_tag(name, version):
        return '{}.v{}'.format(name, version)

    @staticmethod
    def format_name(name):
        return name.replace(' ', '.').strip() if name else ''

    @staticmethod
    def get_name(name):
        return Definition.format_name(name) or 'auto-{}'.format(uuid4().hex)

    @property
    def roots(self):
        """ All nodes that have no parents.
        """
        if not self._roots:
            self._roots = sorted(set(self.nodes) - self._non_root)
        return self._roots

    def add_node(self, name, data=''):
        """ Adds a new node by name and opaque data it contains.
        """
        self.nodes[name] = Node(name, data)

    @validate_from_to
    def add_edge(self, from_, to):
        """ Adds a connection between from_ and to nodes.
        """
        # Add an edge
        self.nodes[from_].add_edge(to)

        # So that we know 'to' is not one of roots seeing as at least one node leads to it
        self._non_root.add(to)

        # Result OK
        return True

    @validate_from_to
    def has_edge(self, from_, to):
        """ Does a direct connection between from_ and to nodes exist?
        """
        return self.nodes[from_].has_edge(to)

# ################################################################################################################################

class ConfigItem(object):
    """ An individual definition of transitions.
    """
    def __init__(self):
        self.def_ = Definition()
        self.objects = []
        self.force_stop = []
        self.def_config = {}
        self.orig_config = {}

    def _add_nodes_edges(self, config, add_nodes=True):
        for from_, to in config[self.def_.name].items():
            if not isinstance(to, list):
                to = [to]

            if add_nodes:
                self.def_.add_node(from_)
                for to_item in to:
                    self.def_.add_node(to_item)
            else:
                for to_item in to:
                    self.def_.add_edge(from_, to_item)

    def _extend_list(self, config, attr):
        item = config[self.def_.name].pop(attr, [])
        if not isinstance(item, list):
            item = [item]
        getattr(self, attr).extend(item)

    def parse_config_dict(self, orig_config):

        # So that the original, possibly still kept in a service's self.user_config, is not modified
        self.def_config = deepcopy(orig_config)

        # Handy to keep it around because higher level layers may wish to consult it
        self.orig_config.update(deepcopy(orig_config))

        # There will be exactly one key
        orig_key = self.def_config.keys()[0]
        def_name = Definition.get_name(orig_key)
        self.def_config[def_name] = self.def_config[orig_key]
        self.def_.name = def_name

        # Version is optional
        self.def_.version = self.def_config[self.def_.name].pop('version', CONST.DEFAULT_GRAPH_VERSION)

        # Extend attributes that may either strings or lists in config
        self._extend_list(self.def_config, 'objects')
        self._extend_list(self.def_config, 'force_stop')

        # Collect nodes and edges
        self._add_nodes_edges(self.def_config)
        self._add_nodes_edges(self.def_config, False)

        # Set correct tag
        self.def_.tag = Definition.get_tag(self.def_.name, self.def_.version)

    def parse_config_ini(self, data):

        # Parse string as a list of lines and turn it into config
        self.parse_config_dict(ConfigObj(data.splitlines()))

# ################################################################################################################################

class StateBackendBase(object):
    """ An abstract object defining the API for state backend implementations to follow.
    """
    def rename_def(self, old_def_name, old_def_version, new_def_name, new_def_version):
        """ Renames a definition in place, possibly including its version.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def get_current_state_info(self, object_tag, def_tag):
        """ Returns information on the current state of an object in a graph of transitions.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def get_history(self, object_tag, def_tag):
        """ Returns history of transitions for a given object.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def set_current_state_info(self, object_tag, def_tag, state_info):
        """ Sets new state of an object.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def set_ctx(self, object_type, object_id, def_tag, transition_id, ctx=None):
        """ Attaches arbitrary context data to a transition.
        """
        raise NotImplementedError('Must be implemented in subclasses')

# ################################################################################################################################

class RedisBackend(StateBackendBase):

    PATTERN_STATE_CURRENT = 'zato:bst:state:current:{}'
    PATTERN_STATE_HISTORY = 'zato:bst:state:history:{}'

# ################################################################################################################################

    def __init__(self, conn):
        self.conn = conn

# ################################################################################################################################

    def get_current_state_info(self, object_tag, def_tag):
        data = self.conn.hget(self.PATTERN_STATE_CURRENT.format(def_tag), object_tag)
        if data:
            return loads(data)

# ################################################################################################################################

    def get_history(self, object_tag, def_tag):
        history = self.conn.hget(self.PATTERN_STATE_HISTORY.format(def_tag), object_tag)
        return loads(history) if history else []

# ################################################################################################################################

    def set_current_state_info(self, object_tag, def_tag, state_info):

        # Set the new state object is in ..
        self.conn.hset(self.PATTERN_STATE_CURRENT.format(def_tag), object_tag, state_info)

        # .. and append it to the object's history of transitions.
        history = self.get_history(object_tag, def_tag)
        history.append(state_info)
        history = dumps(history)

        self.conn.hset(self.PATTERN_STATE_HISTORY.format(def_tag), object_tag, history)

# ################################################################################################################################

class SQLBackend(StateBackendBase):

    def __init__(self, session, cluster_id):
        self.session = session
        self.cluster_id = cluster_id

# ################################################################################################################################

    def _get_info(self, object_tag, def_tag, name_pattern, needs_item=False, label=label):
        item = self.session.query(Item).\
            filter(Item.name==name_pattern % (def_tag, object_tag)).\
            filter(Item.cluster_id==self.cluster_id).\
            order_by(Item.name).\
            first()

        if item:
            if needs_item:
                return item
            else:
                return loads(item.value) if item.value else None

# ################################################################################################################################

    def _create_item(self, sub_group_name, name_pattern, def_tag, object_tag):

        sub_group_id, group_id = self.session.query(SubGroup.id, SubGroup.group_id).\
            filter(SubGroup.name==sub_group_name).\
            filter(SubGroup.cluster_id==self.cluster_id).\
            one()

        item = Item()
        item.name = name_pattern % (def_tag, object_tag)
        item.is_internal = False
        item.cluster_id = self.cluster_id
        item.group_id = group_id
        item.sub_group_id = sub_group_id

        return item

# ################################################################################################################################

    def get_current_state_info(self, object_tag, def_tag, needs_item=False):
        return self._get_info(object_tag, def_tag, label.item.process_bst_inst_current, needs_item)

# ################################################################################################################################

    def get_history(self, object_tag, def_tag):
        return self._get_info(object_tag, def_tag, label.item.process_bst_inst_history, False) or []

# ################################################################################################################################

    def set_current_state_info(self, object_tag, def_tag, state_info, label=label):
        current = self.get_current_state_info(
            object_tag, def_tag, True) or self._create_item(
                label.sub_group.conf.process_bst, label.item.process_bst_inst_current, def_tag, object_tag)
        current.value = state_info

        history = self._get_info(
            object_tag, def_tag, label.item.process_bst_inst_history, True) or self._create_item(
                label.sub_group.conf.process_bst, label.item.process_bst_inst_history, def_tag, object_tag)

        history_value = loads(history.value) if history.value else []
        history_value.append(state_info)
        history.value = dumps(history_value)

        self.session.add(current)
        self.session.add(history)

        self.session.commit()

# ################################################################################################################################

class StateMachine(object):
    def __init__(self, config=None, backend=None, run_set_up=True):
        self.config = config
        self.backend = backend
        self.object_type_to_def = {}

        # Prepares database and run-time structures
        if run_set_up:
            self.set_up()

    def set_up(self):
        # Map object types to definitions they are contained in.
        for def_tag, config_item in self.config.items():
            for object_type in config_item.objects:
                defs = self.object_type_to_def.setdefault(object_type, [])
                defs.append(def_tag)

    @staticmethod
    def get_object_tag(object_type, object_id):
        return '{}.{}'.format(object_type, object_id)

    def get_def_tag(self, object_type, object_id=None, state_new=None, def_name=None, def_version=None):
        def_tag = self.object_type_to_def[object_type]

        if len(def_tag) > 1:
            msg = 'Ambiguous input. Object `{}` maps to more than one definition `{}` '\
                '(id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                object_type, ', '.join(def_tag), object_id, state_new, def_name, def_version)
            logger.warn(msg)
            raise TransitionError(msg)

        # Ok, we've got it now after ensuring there is only one definition for that object type
        return def_tag[0]

# ################################################################################################################################

    def get_transition_info(self, state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, is_forced):
        return {
            'state_old': state_current,
            'state_current': state_new,
            'object_tag': object_tag,
            'def_tag': def_tag,
            'transition_ts_utc': datetime.utcnow().isoformat(),
            'server_ctx': server_ctx,
            'user_ctx': user_ctx,
            'is_forced': is_forced or False
        }

# ################################################################################################################################

    def can_transition(self, object_tag, state_new, def_tag, force=False):

        # Obtain graph object's config
        config = self.config[def_tag]

        # Find the current state of this object in backend
        state_current_info = self.backend.get_current_state_info(object_tag, config.def_.tag)
        state_current = state_current_info['state_current'] if state_current_info else None

        # Could be a a forced transition so if state_new exists at all in the definition, this is all good.
        if force and state_new in config.def_.nodes:
            return True, '', state_current, state_new

        # Perhaps it's a forced stop interrupting the process immediately.
        # However, unless forced to, we don't want to transition the same stop state.
        if state_new in config.force_stop:
            return True, '', state_current, state_new

        # If not found and it's not a root node, just return False and reason - we cannot work with unknown objects
        if not state_current_info and state_new not in config.def_.roots:
            msg = 'Object `{}` of `{}` not found and target state `{}` is not one of roots `{}`'.format(
                object_tag, config.def_.tag, state_new, ', '.join(config.def_.roots))
            logger.warn(msg)
            return False, msg, None, state_new

        # If there is no current state it means we want to transit to one of roots so the check below is skipped.
        if state_current:

            if not config.def_.has_edge(state_current, state_new):
                msg = 'No transition found from `{}` to `{}` for `{}` in `{}`'.format(
                    state_current, state_new, object_tag, def_tag)
                logger.warn(msg)
                return False, msg, state_current, state_new

        return True, '', state_current, state_new

# ################################################################################################################################

    def transition(self, object_tag, state_new, def_tag, server_ctx, user_ctx=None, force=False, raise_on_error=True):

        # Make sure this is a valid transition
        can_transition, reason, state_current, _ = self.can_transition(object_tag, state_new, def_tag, force)

        if not can_transition:
            if raise_on_error:
                raise TransitionError(reason)
            else:
                return can_transition, reason, state_current, state_new

        self.backend.set_current_state_info(
            object_tag, def_tag, dumps(self.get_transition_info(
                state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, force)))

        return can_transition, reason, state_current, state_new

# ################################################################################################################################

    def mass_transition(self, items):
        for item in items:
            self.transition(*item)

# ################################################################################################################################

    def get_current_state_info(self, object_tag, def_tag):
        state_info = self.backend.get_current_state_info(object_tag, def_tag)
        if state_info:
            state_info['object_tag'] = object_tag
            state_info['def_tag'] = def_tag
            return state_info

# ################################################################################################################################

    def get_history(self, object_tag, def_tag):
        return [loads(elem) for elem in self.backend.get_history(object_tag, def_tag)]

# ################################################################################################################################

    def reformat_date(self, value, time_zone, date_time_format):
        value = arrow_get(value).replace(tzinfo=pytz.UTC)
        local_tz = pytz.timezone(time_zone)
        return local_tz.normalize(value.astimezone(local_tz)).strftime(date_time_format)

    def get_name_state(self, name, state_info, time_zone, date_time_format, is_stop):
        if not state_info:
            return name

        history = self.get_history(state_info.object_tag, state_info.def_tag)

        is_stop=' (s)' if is_stop else ''
        tz_sep = '\n' if len(time_zone) > 5 else '' # So that for instance America/New_York fits in a single line

        if name == state_info.state_current:
            return '{name}{is_stop}{is_forced}\n{date} {tz_sep}{time_zone}'.format(
                name=name,
                is_stop=is_stop,
                is_forced=' (f)' if state_info.is_forced else '',
                date=self.reformat_date(state_info.transition_ts_utc, time_zone, date_time_format),
                tz_sep=tz_sep,
                time_zone=time_zone)

        elif name == state_info.state_old:

            # We know there is some previous state so we can get history
            # for this object and look up the penultimate element which points to the previous state.
            previous = history[-2]

            return '{name}{is_stop}{is_forced}\n{date} {tz_sep}{time_zone}'.format(
                name=name,
                is_stop=is_stop,
                is_forced=' (f)' if previous['is_forced'] else '',
                date=self.reformat_date(previous['transition_ts_utc'], time_zone, date_time_format),
                tz_sep=tz_sep,
                time_zone=time_zone)

        return name

# ################################################################################################################################

class TransitionInfo(Bunch):
    def __init__(self, ctx):
        self.update(ctx or {})

# ################################################################################################################################

class transition_to(object):
    """ A context manager to encompass validation and saving of states. Called transition_to instead of TransitionTo
    because eventually it will be available in Zato services as 'self.transitions.to'.
    """
    def __init__(self, service, object_type, object_id, state_new, def_name=None,
            def_version=None, user_ctx=None, force=False):

        if 'zato_state_machine' not in service.server.user_ctx:
            setup_server_config(service)

        self.state_machine = service.server.user_ctx.zato_state_machine
        self.object_type = object_type
        self.object_id = object_id
        self.state_new = state_new
        self.def_name = def_name
        self.def_version = def_version
        self.force = force
        self.ctx = TransitionInfo(user_ctx)
        self.object_tag = StateMachine.get_object_tag(self.object_type, self.object_id)
        self.def_tag = '' # We cannot be certain what it is yet, we may not have definition's name/version yet

    def __enter__(self):

        if not self.def_name:

            if self.object_type not in self.state_machine.object_type_to_def:
                msg = 'Unknown object type `{}` (id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                    self.object_type, self.object_id, self.state_new, self.def_name, self.def_version)
                logger.warn(msg)
                raise TransitionError(msg)

            self.def_tag = self.state_machine.get_def_tag(
                self.object_type, self.object_id, self.state_new, self.def_name, self.def_version)

        can_transition, reason, _, _= self.state_machine.can_transition(self.object_tag, self.state_new, self.def_tag, self.force)
        if not can_transition:
            raise TransitionError(reason)

        return self.ctx

    def __exit__(self, exc_type, exc_value, traceback):

        if not exc_type:
            # TODO: Use server_ctx in .transition
            self.state_machine.transition(self.object_tag, self.state_new, self.def_tag, None, self.ctx, self.force)
            return True

# ################################################################################################################################
