# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from json import dumps, loads

# Bunch
from bunch import bunchify

# zato-labs
from zato_bst import CONST, Definition, setup_server_config, StateMachine, yield_definitions

# Zato
from zato.server.connection.http_soap import BadRequest
from zato.server.service import AsIs, Bool, Service

# ################################################################################################################################

class FORMAT:
    DEFINITION = ['json', 'text']
    STATE = ['json']

# ################################################################################################################################

class Base(Service):
    name = 'labs.proc.bst.definition.base'

    def before_handle(self):

        if 'zato_state_machine' not in self.server.user_ctx:
            setup_server_config(self)

        self.environ = bunchify(self.environ)
        self.environ.sm = self.server.user_ctx.zato_state_machine

        req = self.request.input
        if req and 'object_type' in req:
            self.environ.def_version = req.get('def_version', CONST.DEFAULT_GRAPH_VERSION)
            self.environ.object_tag = StateMachine.get_object_tag(req.object_type, req.object_id)
            self.environ.def_tag = self.environ.sm.get_def_tag(
                req.object_type, req.object_id, req.get('state_new'), req.get('def_name'), self.environ.def_version)

# ################################################################################################################################

class JSONProducer(Service):
    name = 'labs.proc.bst.definition.json-producer'

    def after_handle(self):
        self.response.content_type = 'application/json'

# ################################################################################################################################

class StartupSetup(Base):
    """ A start-up service to imports all definitions of transitions in state machines
    and creates runtime structures out of what is found.
    """
    name = 'labs.proc.bst.definition.startup-setup'

    def handle(self):
        # Base before_handle does everything we need
        pass

# ################################################################################################################################

class SingleTransitionBase(Base):
    name = 'labs.proc.bst.single-transition-base'

    class SimpleIO:
        input_required = ('object_type', AsIs('object_id'), 'state_new')
        input_optional = ('def_name', 'def_version', Bool('force'))
        output_required = (Bool('can_transition'), 'state_old', 'state_new')
        output_optional = ('reason',)

    def _set_response(self, can_transition, reason, state_old, state_new):
        self.response.payload.can_transition = can_transition
        self.response.payload.reason = reason
        self.response.payload.state_old = state_old
        self.response.payload.state_new = state_new

class CanTransition(SingleTransitionBase):
    """ Returns information if a given object can transit to a new state.
    """
    name = 'labs.proc.bst.can-transition'

    def handle(self):
        self._set_response(*self.environ.sm.can_transition(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, self.request.input.force))

# ################################################################################################################################

class Transition(SingleTransitionBase):
    """ Performs a transition on an object.
    """
    name = 'labs.proc.bst.transition'

    class SimpleIO(SingleTransitionBase.SimpleIO):
        input_optional = SingleTransitionBase.SimpleIO.input_optional + ('user_ctx',)

    def handle(self):
        self._set_response(*self.environ.sm.transition(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, None,
            self.request.input.get('user_ctx', None), self.request.input.force, False))

# ################################################################################################################################

class MassTransition(Base, JSONProducer):
    """ Performs transitions on a list of object.
    """
    name = 'labs.proc.bst.mass-transition'

    def handle(self):
        out = []
        for item in loads(self.request.raw_request):
            out.append(self.invoke(Transition.name, item))

        self.response.payload = dumps(out)

# ################################################################################################################################

class GetHistory(SingleTransitionBase, JSONProducer):
    """ Returns a history of transitions for a given object
    """
    name = 'labs.proc.bst.get-history'

    class SimpleIO:
        input_required = ('object_type', AsIs('object_id'))

    def handle(self):
        self.response.payload = dumps(self.environ.sm.get_history(self.environ.object_tag, self.environ.def_tag), indent=2)

# ################################################################################################################################

class GetDefinitionList(Base, JSONProducer):
    """ Returns all definition as JSON.
    """
    name = 'labs.proc.bst.get-definition-list'

    def handle(self):
        self.response.payload = dumps([{name:data} for name, data in yield_definitions(self)], indent=2)

# ################################################################################################################################

class FormatBase(Base):

    def_format = None
    needs_state_info = False

    def validate_input(self):
        format = self.request.input.get('format')
        if format and format not in self.def_format:
            raise BadRequest(self.cid, 'Format is not one of `{}`\n'.format(', '.join(self.def_format)))

# ################################################################################################################################

class GetDefinition(FormatBase):
    """ Returns a selected definition, as text or JSON.
    """
    name = 'labs.proc.bst.get-definition'
    def_format = FORMAT.DEFINITION

    class SimpleIO:
        input_required = ('def_name',)
        input_optional = ('format', 'def_version')

    def handle(self):
        def_name = Definition.get_name(self.request.input.def_name)
        def_tag = Definition.get_tag(def_name, self.request.input.get('def_version') or CONST.DEFAULT_GRAPH_VERSION)

        if def_tag not in self.environ.sm.config:
            raise BadRequest(self.cid, 'No such definition `{}`\n'.format(def_tag))

        self._get_handle()(def_tag)

    def _get_handle(self):

        format = self.request.input.get('format') or 'text'
        format = format.replace('-', '_')
        return getattr(self, '_handle_def_{}'.format(format))

    def _handle_def_text(self, def_tag):
        self.response.payload = str(self.environ.sm.config[def_tag].def_)

    def _handle_def_json(self, def_tag):
        self.response.payload = dumps(self.environ.sm.config[def_tag].orig_config, indent=2)

# ################################################################################################################################

class GetCurrentStateInfo(GetDefinition):
    """ Returns information on an object's state in a given process as JSON.
    """
    name = 'labs.proc.bst.get-current-state-info'
    def_format = FORMAT.STATE
    needs_state_info = True

    class SimpleIO:
        input_required = ('object_type', AsIs('object_id'))
        input_optional = ('format', 'def_name', 'def_version', 'date_time_format', 'time_zone')

    def handle(self):
        self._get_handle()(self.environ.def_tag)

    def _handle_def_json(self, _ignored):
        self.response.payload = dumps(self.environ.sm.get_current_state_info(self.environ.object_tag, self.environ.def_tag))

# ################################################################################################################################
