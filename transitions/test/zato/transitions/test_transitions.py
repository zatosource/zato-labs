# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from inspect import getargspec
from json import dumps, loads
from unittest import TestCase
from uuid import uuid4

# Bunch
from bunch import bunchify

# fakeredis
from fakeredis import FakeRedis

# Zato
from zato.transitions import AddEdgeResult, ConfigItem, CONST, Definition, Node, RedisBackend, StateBackendBase, StateMachine

EXPECTED_DIAGRAM_PNG = """
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
yb0KtAIAAAAASUVORK5CYII=
""".strip()

EXPECTED_DIAGRAM_DEF = """blockdiag {
   orientation = portrait;
   default_shape = roundedbox;
   node_width = 200;

   begin [shape = beginpoint];
   end [shape = endpoint];

   client_confirmed [label = "client_confirmed"];
   client_rejected [label = "client_rejected"];
   new [label = "new"];
   poor_quality [label = "Poor quality"];
   qa [label = "QA"];
   ready [label = "ready"];
   returned [label = "returned"];
   sent_to_client [label = "sent_to_client"];
   submitted [label = "submitted"];
   updated [label = "updated"];

   begin -> returned;
   client_confirmed -> end;
   client_rejected -> updated;
   new -> submitted;
   poor_quality -> end;
   qa -> end;
   qa -> end;
   qa -> new;
   qa -> poor_quality;
   qa -> qa;
   qa -> ready;
   qa -> submitted;
   ready -> sent_to_client;
   returned -> submitted;
   sent_to_client -> client_confirmed;
   sent_to_client -> client_rejected;
   submitted -> ready;
   updated -> qa;
   updated -> ready;
}
""".lstrip()

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

# ################################################################################################################################

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

    def test__str__(self):
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

    def test_get_roots(self):
        self.assertListEqual(self.d.roots, ['new', 'returned'])

    def test_add_node(self):
        default = ['new', 'returned', 'submitted', 'ready', 'sent_to_client', 'client_confirmed', 'client_rejected', 'updated']

        self.assertEquals(len(self.d.nodes), len(default))
        for name in default:
            self.assertTrue(name in self.d.nodes)

        new = rand_string()
        self.d.add_node(new)

        self.assertEquals(len(self.d.nodes), len(default)+1)
        self.assertTrue(new in self.d.nodes)
        self.assertTrue(new in self.d.roots) # Because no edge leads to it

    def test_add_edge(self):
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

    def test_has_edge_ok(self):
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

    def test_has_edge_missing_nodes(self):
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

        self.assertEquals(result24.error_code, CONST.NO_SUCH_NODE)
        self.assertEquals(result24.details, name4)

        self.assertEquals(result35.error_code, CONST.NO_SUCH_NODE)
        self.assertEquals(result35.details, name5)

        self.assertEquals(result45.error_code, CONST.NO_SUCH_NODE)
        self.assertEquals(result45.details, name4)

# ################################################################################################################################

class ConfigItemTestCase(TestCase):

    def test_parse_config_string1(self):

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
        ci.parse_config_string(config)

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

    def test_parse_config_string2(self):

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
        ci.parse_config_string(config)

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

    def test_patterns(self):
        self.assertEquals(RedisBackend.PATTERN_STATE_CURRENT, 'zato:trans:state:current:{}')
        self.assertEquals(RedisBackend.PATTERN_STATE_HISTORY, 'zato:trans:state:history:{}')

    def test_set_current_state_info(self):
        object_tag, def_tag, state_info = rand_string(3, True)

        backend = RedisBackend(self.conn)
        backend.set_current_state_info(object_tag, def_tag, state_info)

        state = self.conn.hget(backend.PATTERN_STATE_CURRENT.format(def_tag), object_tag)
        self.assertEquals(state, state_info)

    def test_get_current_state_info(self):
        object_tag, def_tag, state_info = rand_string(3, True)

        backend = RedisBackend(self.conn)
        backend.set_current_state_info(object_tag, def_tag, state_info)

        state = backend.get_current_state_info(object_tag, def_tag)
        self.assertEquals(state, loads(state_info))

    def test_get_history(self):
        object_tag, def_tag = rand_string(2)
        state_info1, state_info2, state_info3 = rand_string(3, True)

        backend = RedisBackend(self.conn)

        backend.set_current_state_info(object_tag, def_tag, state_info1)
        backend.set_current_state_info(object_tag, def_tag, state_info2)
        backend.set_current_state_info(object_tag, def_tag, state_info3)

        history = backend.get_history(object_tag, def_tag)

        self.assertListEqual(history, [state_info1, state_info2, state_info3])

# ################################################################################################################################

class StateMachineTestCase(TestCase):

    def setUp(self):
        self.maxDiff = None
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
            updated=ready,QA
            QA=submitted,ready,new,Rejected in QA,QA
            """.strip()

        self.conn = FakeRedis()
        self.ci = ConfigItem()
        self.ci.parse_config_string(config)

        self.sm = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn))
        self.sm = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn))
        self.sm_no_set_up = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn), False)

    def test_get_def_diagram(self):

        state_info = bunchify({
            'state_old':'sent_to_client',
            'state_current':'client_rejected',
            'transition_ts_utc': '2015-10-10T00:51:03.461721',
            'is_forced': False
        })

        diag, diag_def = self.sm.get_diagram(
            Definition.get_tag('Orders', '1'), state_info=state_info, time_zone='EST')

        #self.assertEquals(EXPECTED_DIAGRAM_PNG, diag.encode('base64').strip())
        #self.assertEquals(EXPECTED_DIAGRAM_DEF, diag_def)
        print(diag)
        #print(diag_def)

# ################################################################################################################################
