# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from json import dumps, loads

# Bunch
from bunch import bunchify

# zato-labs
from zato_transitions import ConfigItem, CONSTANTS, setup_server_config, StateMachine, transition_to

# Zato
from zato.common.broker_message import MESSAGE_TYPE, SERVICE
from zato.common.util import new_cid
from zato.server.service import AsIs, Bool, Service

# ################################################################################################################################

class Testing(Service):
    name = 'xzato.labs.bizstates.definition.testing'

    def handle(self):
        with transition_to(self, 'order', 1, 'canceled'):
            pass

# ################################################################################################################################

class Base(Service):
    name = 'xzato.labs.bizstates.definition.base'

    def before_handle(self):
        if not 'zato_state_machine' in self.server.user_ctx:
            setup_server_config(self)

        req = self.request.input
        if req:
            self.environ = bunchify(self.environ)

            self.environ.sm = self.server.user_ctx.zato_state_machine
            self.environ.def_version = req.get('def_version', CONSTANTS.DEFAULT_GRAPH_VERSION)
            self.environ.object_tag = StateMachine.get_object_tag(req.object_type, req.object_id)
            self.environ.def_tag = self.environ.sm.get_def_tag(
                req.object_type, req.object_id, req.state_new, req.get('def_name'), self.environ.def_version)

# ################################################################################################################################

class StartupSetup(Base):
    """ A start-up service to imports all definitions of transitions in state machines
    and creates runtime structures out of what is found.
    """
    name = 'xzato.labs.bizstates.definition.startup-setup'

    def handle(self):
        # Base before_handle does everything we need
        pass

# ################################################################################################################################

class SingleTransitBase(Base):
    name = 'xzato.labs.bizstates.transition.single-transit-base'

    class SimpleIO:
        input_required = ('object_type', AsIs('object_id'), 'state_new')
        input_optional = ('def_name', 'def_version', Bool('force'))
        output_required = (Bool('can_transit'), 'state_old', 'state_new')
        output_optional = ('reason',)

    def _set_response(self, can_transit, reason, state_old, state_new):
        self.response.payload.can_transit = can_transit
        self.response.payload.reason = reason
        self.response.payload.state_old = state_old
        self.response.payload.state_new = state_new

class CanTransit(SingleTransitBase):
    """ Returns information if a given object can transit to a new state.
    """
    name = 'xzato.labs.bizstates.transition.can-transit'

    def handle(self):
        self._set_response(*self.environ.sm.can_transit(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, self.request.input.force))

# ################################################################################################################################

class Transit(SingleTransitBase):
    """ Performs a transition on an object.
    """
    name = 'xzato.labs.bizstates.transition.transit'

    class SimpleIO(SingleTransitBase.SimpleIO):
        input_optional = SingleTransitBase.SimpleIO.input_optional + ('user_ctx',)

    def handle(self):
        self._set_response(*self.environ.sm.transit(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, 'zzz',
            self.request.input.get('user_ctx', None), self.request.input.force, False))

# ################################################################################################################################

class MassTransit(Base):
    """ Performs transitions on a list of object.
    """
    name = 'xzato.labs.bizstates.transition.mass-transit'

    def handle(self):
        out = []
        for item in loads(self.request.raw_request):
            out.append(self.invoke(Transit.name, item))

        self.response.payload = dumps(out)

# ################################################################################################################################

class GetHistory(Base):
    """ Returns a history of transitions for a given object
    """
    name = 'xzato.labs.bizstates.transition.get-history'

# ################################################################################################################################

class GetDefinition(Base):
    """ Returns a selected definition, as text, Python dict or a diagram.
    """
    name = 'xzato.labs.bizstates.transition.get-definition'

# ################################################################################################################################

class GetCurrentStateInfo(Base):
    """ Returns information on an object's state in a given process as a Python dict or a diagram.
    """
    name = 'xzato.labs.bizstates.transition.get-current-state-info'

# ################################################################################################################################
