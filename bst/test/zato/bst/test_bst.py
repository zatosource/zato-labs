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
from zato.bst import AddEdgeResult, ConfigItem, CONST, Definition, Node, parse_pretty_print, RedisBackend, \
     StateBackendBase, StateMachine

EXPECTED_DIAGRAM_PNG = """
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
""".strip()

EXPECTED_DIAGRAM_DEF = """blockdiag {
   orientation = portrait;
   default_shape = box;
   node_width = 200;
   class emphasis [color="#bccc73", style = dashed];

group {
  orientation = portrait;
  color = "#ccccdd";
   canceled [label="canceled" ]
   interrupted [label="interrupted" ]
   needs_supervision [label="needs_supervision" ]
   quit [label="quit" ]
}

   begin [shape = beginpoint];
   end [shape = endpoint];

   client_confirmed [label="client_confirmed" ]
   client_rejected [label="client_rejected
Fri 09/10/15 19:51:03 EST" , class="emphasis"]
   new [label="new" ]
   qa [label="QA" ]
   ready [label="ready" ]
   rejected_in_qa [label="Rejected in QA" ]
   returned [label="returned" ]
   sent_to_client [label="sent_to_client
Sat 10/10/15 13:20:30 EST" , class="emphasis"]
   submitted [label="submitted" ]
   updated [label="updated" ]

   begin -> returned;
   client_confirmed -> end;
   client_rejected -> updated;
   new -> submitted;
   qa -> new;
   qa -> qa;
   qa -> ready;
   qa -> rejected_in_qa;
   qa -> submitted;
   ready -> sent_to_client;
   rejected_in_qa -> end;
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

    def test_parse_config_ini1(self):

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
        ci.parse_config_ini(config)

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

    def test_parse_config_ini2(self):

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
        ci.parse_config_ini(config)

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
        self.assertEquals(RedisBackend.PATTERN_STATE_CURRENT, 'zato:bst:state:current:{}')
        self.assertEquals(RedisBackend.PATTERN_STATE_HISTORY, 'zato:bst:state:history:{}')

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
            force_stop=canceled,quit,needs_supervision,interrupted
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
        self.ci.parse_config_ini(config)

        self.sm = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn))
        self.sm = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn))
        self.sm_no_set_up = StateMachine({self.ci.def_.tag:self.ci}, RedisBackend(self.conn), False)

    def test_get_def_diagram(self):

        state_info = bunchify({
            'state_old':'sent_to_client',
            'state_current':'client_rejected',
            'transition_ts_utc': '2015-10-10T00:51:03.461721',
            'is_forced': False,
            'object_tag':'order.1',
            'def_tag':'Order.1'
        })

        def get_history(*ignored):
            return [
                {'state_old': 'updated', 'state_current': 'client_rejected', 'def_tag': 'Orders.v1',
                 'transition_ts_utc': '2015-10-10T18:20:30.327425', 'object_tag': 'order.1',
                 'user_ctx': {}, 'server_ctx': None, 'is_forced': False},
                {'state_old': 'updated', 'state_current': 'ready', 'def_tag': 'Orders.v1',
                 'transition_ts_utc': '2015-10-10T18:20:30.327425', 'object_tag': 'order.1',
                 'user_ctx': {}, 'server_ctx': None, 'is_forced': False},
            ]

        self.sm.get_history = get_history

        diag, diag_def = self.sm.get_diagram(
            Definition.get_tag('Orders', '1'), state_info=state_info, time_zone='EST')

        self.assertEquals(EXPECTED_DIAGRAM_PNG, diag.encode('base64').strip())
        self.assertEquals(EXPECTED_DIAGRAM_DEF, diag_def)

# ################################################################################################################################

class ParsePrettyPrintTestCase(TestCase):
    def test_parse_pretty_print(self):

        orig_value = """
Orders
------

New: Submitted
Submitted: Ready
Ready: Sent
Sent: Confirmed, Rejected
Rejected: Updated
Updated: Ready
Objects: Order, Priority order
Force stop: Canceled, Interrupted
""".strip()

        expected_after_value = """
[Orders]
New=Submitted
Submitted=Ready
Ready=Sent
Sent=Confirmed, Rejected
Rejected=Updated
Updated=Ready
objects=Order, Priority order
force_stop=Canceled, Interrupted
""".strip()

        self.assertEquals(expected_after_value, parse_pretty_print(orig_value))

# ################################################################################################################################
