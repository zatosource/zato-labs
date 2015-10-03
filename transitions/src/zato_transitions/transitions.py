# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from uuid import uuid4

class ERROR:
    NO_SUCH_NODE = 'NO_SUCH_NODE'

def validate_from_to(func):
    """ Makes sure that both from_ and to are valid node names.
    """
    def _inner(self, from_, to):
        for node in (from_, to):
            if node not in self.nodes:
                return AddEdgeResult(False, ERROR.NO_SUCH_NODE, node)
        return True
    return func

class AddEdgeResult(object):
    """ A boolean result of adding an edge between nodes. Includes error code if the operation failed.
    """
    def __init__(self, is_ok=True, error_code=None, details=None):
        self.is_ok = is_ok
        self.error_code = error_code
        self.details = details

    def __bool__(self):
        return self.is_ok

class Node(object):
    """ An individual node in a graph.
    """
    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.edges = set()

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __str__(self):
        return 'Node: {}'.format(self.name)

    def add_edge(self, to):
        self.edges.add(to)

    def has_edge(self, to):
        return to in self.edges

class Graph(object):
    """ A graph of nodes and edges connecting them. Edges can be cyclic and graphs can have more than one root.
    """
    def __init__(self, name=None):
        self.name = name or 'auto-{}'.format(uuid4().hex)
        self.nodes = {}

    def __str__(self):
        nodes = ', '.join(node.name for node in sorted(self.nodes.values()))
        edges = []

        max_name = 0
        for node in self.nodes.values():
            max_name = max(max_name, len(node.name))

        node_format = ' * {:<'+ str(max_name) +'} -> {}'

        for node in sorted(self.nodes.values()):
            edges.append(node_format.format(node.name, ', '.join(sorted(node.edges)) or '(None)'))

        return '{} {}: {}\n{}'.format(self.__class__.__name__, self.name, nodes, '\n'.join(edges))

    def add_node(self, name, data=''):
        self.nodes[name] = Node(name, data)

    @validate_from_to
    def add_edge(self, from_, to):
        """ Adds a connection between from_ and to nodes.
        """
        self.nodes[from_].add_edge(to)

        # Result OK
        return True

    @validate_from_to
    def has_edge(self, from_, to):
        """ Does a direct connection between from_ and to nodes exist?
        """
        return self.nodes[from_].has_edge(to)

if __name__ == '__main__':
    g = Graph()
    g.add_node('new')
    g.add_node('submitted')
    g.add_node('ready')
    g.add_node('sent_to_client')
    g.add_node('client_confirmed')
    g.add_node('client_rejected')
    g.add_node('updated')

    g.add_edge('new', 'submitted')
    g.add_edge('submitted', 'ready')
    g.add_edge('ready', 'sent_to_client')
    g.add_edge('sent_to_client', 'client_confirmed')
    g.add_edge('sent_to_client', 'client_rejected')
    g.add_edge('client_rejected', 'updated')
    g.add_edge('updated', 'ready')

    print(g)
