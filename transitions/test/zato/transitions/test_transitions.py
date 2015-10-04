# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from unittest import TestCase
from uuid import uuid4

# Zato
from zato.transitions import AddEdgeResult, ERROR, Graph, Node

def rand_string(count=1):
    if count == 1:
        return 'a' + uuid4().hex
    else:
        return ['a' + uuid4().hex for x in range(count)]

class AddEdgeResultTestCase(TestCase):
    def test_attrs(self):

        bools = [True, False]
        error_codes = rand_string(2)
        details = [rand_string(), rand_string()]

        for is_ok in bools:
            for code in error_codes:
                for detail in details:
                    aer = AddEdgeResult(is_ok, code, detail)
                    self.assertEquals(aer.is_ok, is_ok)
                    self.assertEquals(aer.error_code, code)
                    self.assertEquals(aer.details, detail)
                    self.assertEquals(bool(aer), is_ok)

class NodeTestCase(TestCase):
    def test_attrs(self):
        name, data = rand_string(2)
        n1 = Node(name, data)
        self.assertEquals(n1.name, name)
        self.assertEquals(n1.data, data)
        self.assertEquals(len(n1.edges), 0)

        name = rand_string()
        n2 = Node(name)
        self.assertEquals(n2.name, name)
        self.assertIsNone(n2.data)
        self.assertEquals(len(n2.edges), 0)

    def test__cmp__(self):
        n1 = Node('name1')
        n2 = Node('name2')

        # Compared by names, lexicographically
        self.assertLess(n1, n2)

    def test__str__(self):
        n1 = Node('name1')
        self.assertEquals(str(n1), 'Node: name1')

    def test_add_edge(self):
        n1 = Node(rand_string())
        n2, n3 = rand_string(2)

        n1.add_edge(n2)
        n1.add_edge(n3)

        self.assertEquals(len(n1.edges), 2)
        self.assertTrue(n2 in n1.edges)
        self.assertTrue(n3 in n1.edges)

    def test_has_edge(self):
        n1 = Node(rand_string())
        n2, n3 = rand_string(2)

        n1.add_edge(n2)
        n1.add_edge(n3)

        self.assertTrue(n1.has_edge(n2))
        self.assertTrue(n1.has_edge(n3))

class GraphTestCase(TestCase):

    def setUp(self):

        self.g = Graph('Orders')
        self.g.add_node('new')
        self.g.add_node('returned')
        self.g.add_node('submitted')
        self.g.add_node('ready')
        self.g.add_node('sent_to_client')
        self.g.add_node('client_confirmed')
        self.g.add_node('client_rejected')
        self.g.add_node('updated')

        self.g.add_edge('new', 'submitted')
        self.g.add_edge('returned', 'submitted')
        self.g.add_edge('submitted', 'ready')
        self.g.add_edge('ready', 'sent_to_client')
        self.g.add_edge('sent_to_client', 'client_confirmed')
        self.g.add_edge('sent_to_client', 'client_rejected')
        self.g.add_edge('client_rejected', 'updated')
        self.g.add_edge('updated', 'ready')

    def test__str__(self):
        expected = """Graph Orders: ~new, ~returned, client_confirmed, client_rejected, ready, sent_to_client, submitted, updated
 * ~new             -> submitted
 * ~returned        -> submitted
 * client_confirmed -> (None)
 * client_rejected  -> updated
 * ready            -> sent_to_client
 * sent_to_client   -> client_confirmed, client_rejected
 * submitted        -> ready
 * updated          -> ready"""
        self.assertEquals(str(self.g), expected)

    def test_get_roots(self):
        self.assertListEqual(self.g.roots, ['new', 'returned'])

    def test_add_node(self):
        default = ['new', 'returned', 'submitted', 'ready', 'sent_to_client', 'client_confirmed', 'client_rejected', 'updated']

        self.assertEquals(len(self.g.nodes), len(default))
        for name in default:
            self.assertTrue(name in self.g.nodes)

        new = rand_string()
        self.g.add_node(new)

        self.assertEquals(len(self.g.nodes), len(default)+1)
        self.assertTrue(new in self.g.nodes)
        self.assertTrue(new in self.g.roots) # Because no edge leads to it

    def test_add_edge_ok(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        self.g.add_node(name1)
        self.g.add_node(name2)
        self.g.add_node(name3)
        self.g.add_node(name4)

        self.g.add_edge(name1, name2)
        self.g.add_edge(name2, name3)
        self.g.add_edge(name2, name4)
        self.g.add_edge(name3, name5)
        self.g.add_edge(name4, name5)

        self.assertTrue(name2 in self.g.nodes[name1].edges)
        self.assertTrue(name3 in self.g.nodes[name2].edges)
        self.assertTrue(name4 in self.g.nodes[name2].edges)
        self.assertTrue(name5 in self.g.nodes[name3].edges)
        self.assertTrue(name5 in self.g.nodes[name4].edges)

        self.assertTrue(name1 in self.g.roots) # Because no edge leads to it

    def test_has_edge_ok(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        self.g.add_node(name1)
        self.g.add_node(name2)
        self.g.add_node(name3)
        self.g.add_node(name4)
        self.g.add_node(name5)

        self.g.add_edge(name1, name2)
        self.g.add_edge(name2, name3)
        self.g.add_edge(name2, name4)
        self.g.add_edge(name3, name5)
        self.g.add_edge(name4, name5)

        self.assertTrue(self.g.has_edge(name1, name2))
        self.assertTrue(self.g.has_edge(name2, name3))
        self.assertTrue(self.g.has_edge(name2, name4))
        self.assertTrue(self.g.has_edge(name3, name5))
        self.assertTrue(self.g.has_edge(name4, name5))

        # Edges should not get established the other way around
        self.assertFalse(self.g.has_edge(name2, name1))
        self.assertFalse(self.g.has_edge(name3, name2))
        self.assertFalse(self.g.has_edge(name4, name2))
        self.assertFalse(self.g.has_edge(name5, name3))
        self.assertFalse(self.g.has_edge(name5, name4))

    def test_has_edge_missing_nodes(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        # We're adding only three nodes
        self.g.add_node(name1)
        self.g.add_node(name2)
        self.g.add_node(name3)

        self.g.add_edge(name1, name2)
        self.g.add_edge(name2, name3)
        self.g.add_edge(name2, name4)
        self.g.add_edge(name3, name5)
        self.g.add_edge(name4, name5)
