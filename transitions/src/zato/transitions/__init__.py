# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from datetime import datetime
from json import dumps, loads
from logging import basicConfig, getLogger
from uuid import uuid4

from bunch import Bunch

# ConfigObj
from configobj import ConfigObj

# ################################################################################################################################

logger = getLogger(__name__)

basicConfig()

# ################################################################################################################################

class CONSTANTS:
    NO_SUCH_NODE = 'NO_SUCH_NODE'
    DEFAULT_GRAPH_VERSION = 1

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
                return AddEdgeResult(False, CONSTANTS.NO_SUCH_NODE, node)
        return func(self, from_, to)
    return _inner

# ################################################################################################################################

def setup_server_config(service):
    config = {}
    prefix = 'biz_states_'
    for name, data in service.server.user_config.user.items():

        # Pick up only our definitions ..
        if name.startswith(prefix):

            # .. parse the definition and append to the state machine's config dict
            item = ConfigItem()
            item.parse_config_dict({name.replace(prefix, ''):data})
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
    def __init__(self, name=None, version=CONSTANTS.DEFAULT_GRAPH_VERSION):
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

    def parse_config_dict(self, config):

        # There will be exactly one key
        orig_key = config.keys()[0]
        def_name = Definition.get_name(orig_key)
        config[def_name] = config[orig_key]
        self.def_.name = def_name

        # Version is optional
        self.def_.version = config[self.def_.name].pop('version', CONSTANTS.DEFAULT_GRAPH_VERSION)

        # Extend attributes that may either strings or lists in config
        self._extend_list(config, 'objects')
        self._extend_list(config, 'force_stop')

        # Collect nodes and edges
        self._add_nodes_edges(config)
        self._add_nodes_edges(config, False)

        # Set correct tag
        self.def_.tag = Definition.get_tag(self.def_.name, self.def_.version)

    def parse_config_string(self, data):

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
    PATTERN_STATE_CURRENT = 'zato:trans:state:current:{}'
    PATTERN_STATE_HISTORY = 'zato:trans:state:history:{}'

    def __init__(self, conn):
        self.conn = conn

    def get_current_state_info(self, object_tag, def_tag):
        data = self.conn.hget(self.PATTERN_STATE_CURRENT.format(def_tag), object_tag)
        if data:
            return loads(data)

    def get_history(self, object_tag, def_tag):
        history = self.conn.hget(self.PATTERN_STATE_HISTORY.format(def_tag), object_tag)
        return loads(history) if history else []

    def set_current_state_info(self, object_tag, def_tag, state_info):

        # Set the new state object is in ..
        self.conn.hset(self.PATTERN_STATE_CURRENT.format(def_tag), object_tag, state_info)

        # .. and append it to the object's history of transitions.
        history = self.get_history(object_tag, def_tag)
        history.append(state_info)
        history = dumps(history)

        self.conn.hset(self.PATTERN_STATE_HISTORY.format(def_tag), object_tag, history)

# ################################################################################################################################

class StateMachine(object):
    def __init__(self, config=None, backend=None, run_set_up=True):
        self.config = config
        self.backend = backend
        self.object_to_def = {}

        # Prepares database and run-time structures
        if run_set_up:
            self.set_up()

    def set_up(self):
        # Map object types to definitions they are contained in.
        for def_tag, config_item in self.config.items():
            for object_type in config_item.objects:
                defs = self.object_to_def.setdefault(object_type, [])
                defs.append(def_tag)

    @staticmethod
    def get_object_tag(object_type, object_id):
        return '{}.{}'.format(object_type, object_id)

# ################################################################################################################################

    def get_transition_info(self, state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, is_forced):
        return {
            'state_previous': state_current,
            'state_current': state_new,
            'object_tag': object_tag,
            'def_tag': def_tag,
            'transition_ts_utc': datetime.utcnow().isoformat(),
            'server_ctx': server_ctx,
            'user_ctx': user_ctx,
            'is_forced': is_forced
        }

# ################################################################################################################################

    def can_transit(self, object_tag, state_new, def_tag, force=False):

        # Obtain graph object's config
        config = self.config[def_tag]

        # Find the current state of this object in backend
        state_current_info = self.backend.get_current_state_info(object_tag, config.def_.tag)
        state_current = state_current_info['state_current'] if state_current_info else None

        # Could be a a forced transition so if state_new exists at all in the definition, this is all good.
        if force and state_new in config.def_.nodes:
            return True, '', state_current

        # Perhaps it's a forced stop interrupting the process immediately
        if state_new in config.force_stop:
            return True, '', state_current

        # If not found and it's not a root node, just return False and reason - we cannot work with unknown objects
        if not state_current_info and state_new not in config.def_.roots:
            msg = 'Object `{}` of `{}` not found and target state `{}` is not one of roots `{}`'.format(
                object_tag, config.def_.tag, state_new, ', '.join(config.def_.roots))
            logger.warn(msg)
            return False, msg, None

        # If there is no current state it means we want to transit to one of roots so the check below is skipped.
        if state_current:

            if not config.def_.has_edge(state_current, state_new):
                msg = 'No transition found from `{}` to `{}` for `{}` in `{}`'.format(
                    state_current, state_new, object_tag, def_tag)
                logger.warn(msg)
                return False, msg, state_current

        return True, '', state_current

# ################################################################################################################################

    def transit(self, object_tag, state_new, def_tag, server_ctx, user_ctx=None, force=False):

        # Make sure this is a valid transition
        can_transit, reason, state_current = self.can_transit(object_tag, state_new, def_tag, force)
        if not can_transit:
            raise TransitionError(reason)

        self.backend.set_current_state_info(
            object_tag, def_tag, dumps(self.get_transition_info(
                state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, force)))

# ################################################################################################################################

    def mass_transit(self, items):
        for item in items:
            self.transit(*item)

# ################################################################################################################################

    def get_current_state_info(self, object_tag, def_tag):
        return self.backend.get_current_state_info(object_tag, def_tag)

# ################################################################################################################################

    def get_history(self, object_tag, def_tag):
        return [loads(elem) for elem in self.backend.get_history(object_tag, def_tag)]

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

        if not 'zato_state_machine' in service.server.user_ctx:
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

            if self.object_type not in self.state_machine.object_to_def:
                msg = 'Unknown object type `{}` (id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                    self.object_type, self.object_id, self.state_new, self.def_name, self.def_version)
                logger.warn(msg)
                raise TransitionError(msg)

            def_tag = self.state_machine.object_to_def[self.object_type]

            if len(def_tag) > 1:
                msg = 'Ambiguous input. Object `{}` maps to more than one definition `{}` '\
                    '(id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                    self.object_type, ', '.join(def_tag), self.object_id, self.state_new, self.def_name, self.def_version)
                logger.warn(msg)
                raise TransitionError(msg)

            # Ok, we've got it now after ensuring there is only one definition for that object type
            self.def_tag = def_tag[0]

        can_transit, reason, _ = self.state_machine.can_transit(self.object_tag, self.state_new, self.def_tag, self.force)
        if not can_transit:
            raise TransitionError(reason)

        return self.ctx

    def __exit__(self, exc_type, exc_value, traceback):

        if not exc_type:
            # TODO: Use server_ctx in .transit
            self.state_machine.transit(
                self.object_tag, self.state_new, self.def_tag, None, self.ctx, self.force)
            return True

# ################################################################################################################################

if __name__ == '__main__':
    d = Definition('Orders')
    d.add_node('new')
    d.add_node('returned')
    d.add_node('submitted')
    d.add_node('ready')
    d.add_node('sent_to_client')
    d.add_node('client_confirmed')
    d.add_node('client_rejected')
    d.add_node('updated')

    d.add_edge('new', 'submitted')
    d.add_edge('returned', 'submitted')
    d.add_edge('submitted', 'ready')
    d.add_edge('ready', 'sent_to_client')
    d.add_edge('sent_to_client', 'client_confirmed')
    d.add_edge('sent_to_client', 'client_rejected')
    d.add_edge('client_rejected', 'updated')
    d.add_edge('updated', 'ready')

    # print(g)

    config1 = """
    [Orders]
    objects=order, priority.order
    force_stop=canceled
    new=submitted
    returned=submitted
    submitted=ready
    ready=sent_to_client
    sent_to_client=client_confirmed, client_rejected
    client_rejected=updated
    updated=ready
    """.strip()

    config2 = """
    [Orders Old]
    objects=order.old, priority.order
    force_stop=archived
    new=submitted
    returned=submitted
    submitted=ready
    ready=sent_to_client
    sent_to_client=client_confirmed, client_rejected
    client_rejected=rejected
    updated=ready
    """.strip()

    ci1 = ConfigItem()
    ci1.parse_config_string(config1)

    ci2 = ConfigItem()
    ci2.parse_config_string(config2)

    # print(ci1.graph)

    # Imported here because in runtime we expect it to be provided
    # as an input parameter to state machines, i.e. backends won't
    # establish connections themselves.
    from redis import StrictRedis

    conn = StrictRedis()

    config = {
        ci1.def_.tag: ci1,
        ci2.def_.tag: ci2
    }

    order_id = uuid4().hex

    object_tag = StateMachine.get_object_tag('order', order_id)
    def_tag = Definition.get_tag('Orders', '1')

    server_ctx = 'server-{}:{}'.format(uuid4().hex, datetime.utcnow().isoformat())

    sm = StateMachine(config, RedisBackend(conn))

    with transition_to(sm, 'order', order_id, 'new') as t:
        t.ctx = '123'
        # z

    print(t.ctx)

    '''
    sm = StateMachine(config, RedisBackend(conn))
    sm.can_transit(object_tag, 'new', def_tag)
    sm.transit(object_tag, 'new', def_tag, server_ctx)
    sm.transit(object_tag, 'submitted', def_tag, server_ctx)
    sm.transit(object_tag, 'submitted', def_tag, server_ctx, force=True)

    print()
    print('Current:', sm.get_current_state_info(object_tag, def_tag))
    print()
    print('History:')
    for item in sm.get_history(object_tag, def_tag):
        print(' * ', item)
        print()
    print()
    '''

# ################################################################################################################################
