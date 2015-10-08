# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from inspect import getargspec
from json import dumps, loads
from unittest import TestCase
from uuid import uuid4

# fakeredis
from fakeredis import FakeRedis

# Zato
from zato.transitions import AddEdgeResult, ConfigItem, CONSTANTS, Definition, Node, RedisBackend, StateBackendBase

# ################################################################################################################################

def rand_string(count=1, as_json=False):
    if count == 1:
        value = 'a' + uuid4().hex
    else:
        value = ['a' + uuid4().hex for x in range(count)]

    if as_json:
        return [dumps(elem) for elem in value]
    else:
        return value

# ################################################################################################################################

class AddEdgeResultTestCase(TestCase):
    def xtest_attrs(self):

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

# ################################################################################################################################

class NodeTestCase(TestCase):
    def xtest_attrs(self):
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

    def xtest__cmp__(self):
        n1 = Node('name1')
        n2 = Node('name2')

        # Compared by names, lexicographically
        self.assertLess(n1, n2)

    def xtest__str__(self):
        n1 = Node('name1')
        self.assertEquals(str(n1), 'Node: name1')

    def xtest_add_edge(self):
        n1 = Node(rand_string())
        n2, n3 = rand_string(2)

        n1.add_edge(n2)
        n1.add_edge(n3)

        self.assertEquals(len(n1.edges), 2)
        self.assertTrue(n2 in n1.edges)
        self.assertTrue(n3 in n1.edges)

    def xtest_has_edge(self):
        n1 = Node(rand_string())
        n2, n3 = rand_string(2)

        n1.add_edge(n2)
        n1.add_edge(n3)

        self.assertTrue(n1.has_edge(n2))
        self.assertTrue(n1.has_edge(n3))

# ################################################################################################################################

class DefinitionTestCase(TestCase):

    def setUp(self):

        self.d = Definition('Orders')
        self.d.add_node('new')
        self.d.add_node('returned')
        self.d.add_node('submitted')
        self.d.add_node('ready')
        self.d.add_node('sent_to_client')
        self.d.add_node('client_confirmed')
        self.d.add_node('client_rejected')
        self.d.add_node('updated')

        self.d.add_edge('new', 'submitted')
        self.d.add_edge('returned', 'submitted')
        self.d.add_edge('submitted', 'ready')
        self.d.add_edge('ready', 'sent_to_client')
        self.d.add_edge('sent_to_client', 'client_confirmed')
        self.d.add_edge('sent_to_client', 'client_rejected')
        self.d.add_edge('client_rejected', 'updated')
        self.d.add_edge('updated', 'ready')

    def xtest__str__(self):
        expected = """Definition Orders v1: ~new, ~returned, client_confirmed, client_rejected, ready, sent_to_client, submitted, updated
 * ~new             -> submitted
 * ~returned        -> submitted
 * client_confirmed -> (None)
 * client_rejected  -> updated
 * ready            -> sent_to_client
 * sent_to_client   -> client_confirmed, client_rejected
 * submitted        -> ready
 * updated          -> ready"""
        self.assertEquals(str(self.d), expected)

    def xtest_get_roots(self):
        self.assertListEqual(self.d.roots, ['new', 'returned'])

    def xtest_add_node(self):
        default = ['new', 'returned', 'submitted', 'ready', 'sent_to_client', 'client_confirmed', 'client_rejected', 'updated']

        self.assertEquals(len(self.d.nodes), len(default))
        for name in default:
            self.assertTrue(name in self.d.nodes)

        new = rand_string()
        self.d.add_node(new)

        self.assertEquals(len(self.d.nodes), len(default)+1)
        self.assertTrue(new in self.d.nodes)
        self.assertTrue(new in self.d.roots) # Because no edge leads to it

    def xtest_add_edge(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        self.d.add_node(name1)
        self.d.add_node(name2)
        self.d.add_node(name3)
        self.d.add_node(name4)

        self.assertTrue(self.d.add_edge(name1, name2))
        self.assertTrue(self.d.add_edge(name2, name3))
        self.assertTrue(self.d.add_edge(name2, name4))

        # name5 has not been added above
        self.assertFalse(self.d.add_edge(name3, name5))
        self.assertFalse(self.d.add_edge(name4, name5))

        self.assertTrue(name2 in self.d.nodes[name1].edges)
        self.assertTrue(name3 in self.d.nodes[name2].edges)
        self.assertTrue(name4 in self.d.nodes[name2].edges)

        # name5 has not been added above
        self.assertFalse(name5 in self.d.nodes[name3].edges)
        self.assertFalse(name5 in self.d.nodes[name4].edges)

        self.assertTrue(name1 in self.d.roots) # Because no edge leads to it

    def xtest_has_edge_ok(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        self.d.add_node(name1)
        self.d.add_node(name2)
        self.d.add_node(name3)
        self.d.add_node(name4)
        self.d.add_node(name5)

        self.d.add_edge(name1, name2)
        self.d.add_edge(name2, name3)
        self.d.add_edge(name2, name4)
        self.assertTrue(self.d.add_edge(name3, name5))
        self.assertTrue(self.d.add_edge(name4, name5))

        self.assertTrue(self.d.has_edge(name1, name2))
        self.assertTrue(self.d.has_edge(name2, name3))
        self.assertTrue(self.d.has_edge(name2, name4))
        self.assertTrue(self.d.has_edge(name3, name5))
        self.assertTrue(self.d.has_edge(name4, name5))

        # Edges should not get established the other way around
        self.assertFalse(self.d.has_edge(name2, name1))
        self.assertFalse(self.d.has_edge(name3, name2))
        self.assertFalse(self.d.has_edge(name4, name2))
        self.assertFalse(self.d.has_edge(name5, name3))
        self.assertFalse(self.d.has_edge(name5, name4))

    def xtest_has_edge_missing_nodes(self):
        name1, name2, name3, name4, name5 = rand_string(5)

        # We're adding only three nodes
        self.d.add_node(name1)
        self.d.add_node(name2)
        self.d.add_node(name3)

        self.assertTrue(self.d.add_edge(name1, name2))
        self.assertTrue(self.d.add_edge(name2, name3))

        result24 = self.d.add_edge(name2, name4)
        result35 = self.d.add_edge(name3, name5)
        result45 = self.d.add_edge(name4, name5)

        self.assertFalse(result24)
        self.assertFalse(result35)
        self.assertFalse(result45)

        self.assertFalse(result24.is_ok)
        self.assertFalse(result35.is_ok)
        self.assertFalse(result45.is_ok)

        self.assertEquals(result24.error_code, CONSTANTS.NO_SUCH_NODE)
        self.assertEquals(result24.details, name4)

        self.assertEquals(result35.error_code, CONSTANTS.NO_SUCH_NODE)
        self.assertEquals(result35.details, name5)

        self.assertEquals(result45.error_code, CONSTANTS.NO_SUCH_NODE)
        self.assertEquals(result45.details, name4)

# ################################################################################################################################

class ConfigItemTestCase(TestCase):

    def xtest_parse_config1(self):

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

        self.assertListEqual(ci.objects, ['order', 'priority.order'])
        self.assertListEqual(ci.force_stop, ['canceled'])

        self.assertEquals(ci.def_.name, 'Orders')
        self.assertEquals(ci.def_.version, 1)
        self.assertEquals(ci.def_.tag, 'Orders.v1')
        self.assertEquals(
            sorted(ci.def_.nodes.keys()),
            ['client_confirmed', 'client_rejected', 'new', 'ready', 'returned', 'sent_to_client', 'submitted', 'updated'])

        for key in ci.def_.nodes.keys():
            self.assertEquals(ci.def_.nodes[key].name, key)

        self.assertSetEqual(ci.def_.nodes['client_confirmed'].edges, set())
        self.assertSetEqual(ci.def_.nodes['client_rejected'].edges, set(['updated']))
        self.assertSetEqual(ci.def_.nodes['new'].edges, set(['submitted']))
        self.assertSetEqual(ci.def_.nodes['ready'].edges, set(['sent_to_client']))
        self.assertSetEqual(ci.def_.nodes['returned'].edges, set(['submitted']))
        self.assertSetEqual(ci.def_.nodes['sent_to_client'].edges, set(['client_confirmed', 'client_rejected']))
        self.assertSetEqual(ci.def_.nodes['submitted'].edges, set(['ready']))
        self.assertSetEqual(ci.def_.nodes['updated'].edges, set(['ready']))

    def xtest_parse_config2(self):

        config = """
            [Orders Old]
            objects=order.old, priority.order
            version=99a1
            force_stop=archived,deleted
            new=submitted
            returned=submitted
            submitted=ready
            ready=sent_to_client
            sent_to_client=client_confirmed, client_rejected
            client_rejected=rejected
            updated=ready
            """.strip()

        ci = ConfigItem()
        ci.parse_config(config)

        self.assertListEqual(ci.objects, ['order.old', 'priority.order'])
        self.assertListEqual(ci.force_stop, ['archived', 'deleted'])

        self.assertEquals(ci.def_.name, 'Orders.Old')
        self.assertEquals(ci.def_.version, '99a1')
        self.assertEquals(ci.def_.tag, 'Orders.Old.v99a1')

        self.assertEquals(
            sorted(ci.def_.nodes.keys()),
            ['client_confirmed', 'client_rejected', 'new', 'ready', 'rejected', 'returned',
             'sent_to_client', 'submitted', 'updated'])

        for key in ci.def_.nodes.keys():
            self.assertEquals(ci.def_.nodes[key].name, key)

        self.assertSetEqual(ci.def_.nodes['client_confirmed'].edges, set())
        self.assertSetEqual(ci.def_.nodes['client_rejected'].edges, set(['rejected']))
        self.assertSetEqual(ci.def_.nodes['new'].edges, set(['submitted']))
        self.assertSetEqual(ci.def_.nodes['ready'].edges, set(['sent_to_client']))
        self.assertSetEqual(ci.def_.nodes['returned'].edges, set(['submitted']))
        self.assertSetEqual(ci.def_.nodes['sent_to_client'].edges, set(['client_confirmed', 'client_rejected']))
        self.assertSetEqual(ci.def_.nodes['submitted'].edges, set(['ready']))
        self.assertSetEqual(ci.def_.nodes['updated'].edges, set(['ready']))

# ################################################################################################################################

class StateBackendBaseTestCase(TestCase):
    def test_not_implemented_error(self):

        base = StateBackendBase()

        for name in ['rename_def', 'get_current_state_info', 'get_history', 'set_current_state_info', 'set_ctx']:
            func = getattr(base, name)
            args = rand_string(len(getargspec(func).args)-1)
            try:
                func(*args)
            except NotImplementedError, e:
                self.assertEquals(e.message, 'Must be implemented in subclasses')
            else:
                self.fail('Expected NotImplementedError in `{}`'.format(name))

# ################################################################################################################################

class RedisBackendTestCase(TestCase):

    def setUp(self):
        self.conn = FakeRedis()

    def xtest_patterns(self):
        self.assertEquals(RedisBackend.PATTERN_STATE_CURRENT, 'zato:trans:state:current:{}')
        self.assertEquals(RedisBackend.PATTERN_STATE_HISTORY, 'zato:trans:state:history:{}')

    def xtest_set_current_state_info(self):
        object_tag, def_tag, state_info = rand_string(3, True)

        backend = RedisBackend(self.conn)
        backend.set_current_state_info(object_tag, def_tag, state_info)

        state = self.conn.hget(backend.PATTERN_STATE_CURRENT.format(def_tag), object_tag)
        self.assertEquals(state, state_info)

    def xtest_get_current_state_info(self):
        object_tag, def_tag, state_info = rand_string(3, True)

        backend = RedisBackend(self.conn)
        backend.set_current_state_info(object_tag, def_tag, state_info)

        state = backend.get_current_state_info(object_tag, def_tag)
        self.assertEquals(state, loads(state_info))

    def xtest_get_history(self):
        object_tag, def_tag = rand_string(2)
        state_info1, state_info2, state_info3 = rand_string(3, True)

        backend = RedisBackend(self.conn)

        backend.set_current_state_info(object_tag, def_tag, state_info1)
        backend.set_current_state_info(object_tag, def_tag, state_info2)
        backend.set_current_state_info(object_tag, def_tag, state_info3)

        history = backend.get_history(object_tag, def_tag)

        self.assertListEqual(history, [state_info1, state_info2, state_info3])

# ################################################################################################################################
