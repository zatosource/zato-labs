# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from datetime import datetime
from json import dumps, loads
from logging import basicConfig, getLogger
from uuid import uuid4

# ConfigObj
from configobj import ConfigObj

# ################################################################################################################################

logger = getLogger(__name__)

basicConfig()

# ################################################################################################################################

class CONSTANTS:
    NO_SUCH_NODE = 'NO_SUCH_NODE'
    NO_SUCH_OBJECT = 'NO_SUCH_OBJECT'
    DEFAULT_GRAPH_VERSION = 1

# ################################################################################################################################

class StateError(Exception):
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

class Graph(object):
    """ A graph of nodes and edges connecting them. Edges can be cyclic and graphs can have more than one root.
    """
    def __init__(self, name=None, version=CONSTANTS.DEFAULT_GRAPH_VERSION):
        self.name = name.replace(' ', '.').strip() if name else 'auto-{}'.format(uuid4().hex)
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
        self.graph = Graph()
        self.objects = []
        self.force_stop = []

    def _add_nodes_edges(self, config, add_nodes=True):
        for from_, to in config[self.graph.name].items():
            if not isinstance(to, list):
                to = [to]

            if add_nodes:
                self.graph.add_node(from_)
                for to_item in to:
                    self.graph.add_node(to_item)
            else:
                for to_item in to:
                    self.graph.add_edge(from_, to_item)

    def _extend_list(self, config, attr):
        item = config[self.graph.name].pop(attr, [])
        if not isinstance(item, list):
            item = [item]
        getattr(self, attr).extend(item)

    def parse_config(self, data):

        # Parse string as a list of lines
        config = ConfigObj(data.splitlines())

        # There will be exactly one key
        self.graph.name = config.keys()[0]

        # Extend attributes that may either strings or lists in config
        self._extend_list(config, 'objects')
        self._extend_list(config, 'force_stop')

        # Collect nodes and edges
        self._add_nodes_edges(config)
        self._add_nodes_edges(config, False)

        # Version is optional
        self.graph.version = config[self.graph.name].get('version', 1)

        # Set correct tag
        self.graph.tag = Graph.get_tag(self.graph.name, self.graph.version)

# ################################################################################################################################

class StateBackendBase(object):
    """ An abstract object defining the API for state backend implementations to follow.
    """
    def add_graph(self, graph_name, graph_version):
        """ Adds a graph in a given version and returns its ID.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def rename_graph(self, old_graph_name, old_graph_version, new_graph_name, new_graph_version):
        """ Renames a graph in place, possibly including its version.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def get_current_state_info(self, object_tag, graph_tag):
        """ Returns information on the current state of an object in a graph of transitions.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def get_history(self, object_tag, graph_tag):
        """ Returns history of transitions for a given object.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def set_current_state_info(self, object_tag, graph_tag, state_info):
        """ Sets new state of an object.
        """
        raise NotImplementedError('Must be implemented in subclasses')

    def set_ctx(self, object_type, object_id, graph_tag, transition_id, ctx=None):
        """ Attaches arbitrary context data to a transition.
        """
        raise NotImplementedError('Must be implemented in subclasses')

# ################################################################################################################################

class RedisBackend(StateBackendBase):
    KEY_GRAPH_ATTRS_TO_ID = 'zato:trans:graph:tag-to-id'
    PATTERN_STATE_CURRENT = 'zato:trans:state:current:{}'
    PATTERN_STATE_HISTORY = 'zato:trans:state:history:{}'

    def __init__(self, conn):
        self.conn = conn

    def add_graph(self, graph_tag):
        graph_id = self.conn.hget(self.KEY_GRAPH_ATTRS_TO_ID, graph_tag)

        if not graph_id:
            graph_id = uuid4().hex
            self.conn.hset(self.KEY_GRAPH_ATTRS_TO_ID, graph_tag, graph_id)

        return graph_id

    def get_current_state_info(self, object_tag, graph_tag):
        data = self.conn.hget(self.PATTERN_STATE_CURRENT.format(graph_tag), object_tag)
        if data:
            return loads(data)

    def get_history(self, object_tag, graph_tag):
        history = self.conn.hget(self.PATTERN_STATE_HISTORY.format(graph_tag), object_tag)
        return loads(history) if history else []

    def set_current_state_info(self, object_tag, graph_tag, state_info):

        # Set the new state object is in ..
        self.conn.hset(self.PATTERN_STATE_CURRENT.format(graph_tag), object_tag, state_info)

        # .. and append it to the object's history of transitions.
        history = self.get_history(object_tag, graph_tag)
        history.append(state_info)
        history = dumps(history)

        self.conn.hset(self.PATTERN_STATE_HISTORY.format(graph_tag), object_tag, history)

# ################################################################################################################################

class StateMachine(object):
    def __init__(self, config=None, backend=None):
        self.config = config
        self.backend = backend
        self.graph_ids = {}

        # Prepares database and run-time structures
        self.set_up()

    def set_up(self):
        for graph_tag in self.config:
            self.graph_ids[graph_tag] = self.backend.add_graph(graph_tag)

    @staticmethod
    def get_object_tag(object_type, object_id):
        return '{}.{}'.format(object_type, object_id)

    def get_transition_info(self, state_current, state_new, object_tag, graph_tag, server_ctx, user_ctx):
        return {
            'state_previous': state_current,
            'state_current': state_new,
            'object_tag': object_tag,
            'graph_tag': graph_tag,
            'transition_ts_utc': datetime.utcnow().isoformat(),
            'server_ctx': server_ctx,
            'user_ctx': user_ctx
        }

    def can_transit(self, object_tag, state_new, graph_tag):

        # Obtain graph object's config
        config = self.config[graph_tag]

        # Find the current state of this object in backend
        state_current_info = self.backend.get_current_state_info(object_tag, config.graph.tag)

        # If not found and it's not a root node, just return False and reason - we cannot work with unknown objects
        if not state_current_info and state_new not in config.graph.roots:
            msg = 'Object `{}` of `{}` not found and target state `{}` is not one of roots `{}`'.format(
                object_tag, config.graph.tag, state_new, ', '.join(config.graph.roots))
            logger.warn(msg)
            return False, msg, None

        state_current = state_current_info['state_current'] if state_current_info else None

        # If there is no current state it means we want to transit to one of roots so the check below is skipped.
        if state_current:

            if not config.graph.has_edge(state_current, state_new):
                msg = 'No transition found from `{}` to `{}` for `{}` in `{}`'.format(
                    state_current, state_new, object_tag, graph_tag)
                logger.warn(msg)
                return False, msg, None

        return True, '', state_current

    def transit(self, object_tag, state_new, graph_tag, server_ctx, user_ctx=None):

        # Make sure this is a valid transition
        can_transit, reason, state_current = self.can_transit(object_tag, state_new, graph_tag)
        if not can_transit:
            raise StateError(reason)

        self.backend.set_current_state_info(
            object_tag, graph_tag, dumps(self.get_transition_info(
                state_current, state_new, object_tag, graph_tag, server_ctx, user_ctx)))

    def get_current_state_info(self, object_tag, graph_tag):
        return self.backend.get_current_state_info(object_tag, graph_tag)

    def get_history(self, object_tag, graph_tag):
        return [loads(elem) for elem in self.backend.get_history(object_tag, graph_tag)]

# ################################################################################################################################

if __name__ == '__main__':
    g = Graph('Orders')
    g.add_node('new')
    g.add_node('returned')
    g.add_node('submitted')
    g.add_node('ready')
    g.add_node('sent_to_client')
    g.add_node('client_confirmed')
    g.add_node('client_rejected')
    g.add_node('updated')

    g.add_edge('new', 'submitted')
    g.add_edge('returned', 'submitted')
    g.add_edge('submitted', 'ready')
    g.add_edge('ready', 'sent_to_client')
    g.add_edge('sent_to_client', 'client_confirmed')
    g.add_edge('sent_to_client', 'client_rejected')
    g.add_edge('client_rejected', 'updated')
    g.add_edge('updated', 'ready')

    # print(g)

    config = """
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

    ci = ConfigItem()
    ci.parse_config(config)

    # print(ci.graph)

    # Imported here because in runtime we expect it to be provided
    # as an input parameter to state machines, i.e. backends won't
    # establish connections themselves.
    from redis import StrictRedis

    conn = StrictRedis()

    config = {
        ci.graph.tag: ci
    }

    order_id = uuid4().hex

    object_tag = StateMachine.get_object_tag('order', order_id)
    graph_tag = Graph.get_tag('Orders', '1')

    server_ctx = 'server-{}:{}'.format(uuid4().hex, datetime.utcnow().isoformat())

    sm = StateMachine(config, RedisBackend(conn))
    sm.can_transit(object_tag, 'new', graph_tag)
    sm.transit(object_tag, 'new', graph_tag, server_ctx)
    sm.transit(object_tag, 'submitted', graph_tag, server_ctx)

    print()
    print('Current:', sm.get_current_state_info(object_tag, graph_tag))
    print()
    print('History:')
    for item in sm.get_history(object_tag, graph_tag):
        print(' * ', item)
        print()
    print()

# ################################################################################################################################
