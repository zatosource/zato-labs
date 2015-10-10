# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from json import dumps, loads

# Bunch
from bunch import bunchify

# zato-labs
from zato_transitions import CONST, Definition, setup_server_config, StateMachine, transition_to, yield_definitions

# Zato
from zato.server.connection.http_soap import BadRequest
from zato.server.service import AsIs, Bool, Service

# ################################################################################################################################

class FORMAT:
    DEFINITION = ['diagram-def', 'diagram-png', 'json', 'text']
    STATE = ['diagram-def', 'diagram-png', 'json']

# ################################################################################################################################

class Testing(Service):
    name = 'zato.labs.transitions.definition.testing'

    def handle(self):

        for x in range(50):
            with transition_to(self, 'order', x, 'canceled'):
                pass

# ################################################################################################################################

class Base(Service):
    name = 'zato.labs.transitions.definition.base'

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
    name = 'zato.labs.transitions.definition.json-producer'

    def after_handle(self):
        self.response.content_type = 'application/json'

# ################################################################################################################################

class StartupSetup(Base):
    """ A start-up service to imports all definitions of transitions in state machines
    and creates runtime structures out of what is found.
    """
    name = 'zato.labs.transitions.definition.startup-setup'

    def handle(self):
        # Base before_handle does everything we need
        pass

# ################################################################################################################################

class SingleTransitionBase(Base):
    name = 'zato.labs.transitions.single-transit-base'

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

class CanTransition(SingleTransitionBase):
    """ Returns information if a given object can transit to a new state.
    """
    name = 'zato.labs.transitions.can-transition'

    def handle(self):
        self._set_response(*self.environ.sm.can_transit(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, self.request.input.force))

# ################################################################################################################################

class Transition(SingleTransitionBase):
    """ Performs a transition on an object.
    """
    name = 'zato.labs.transitions.transition'

    class SimpleIO(SingleTransitionBase.SimpleIO):
        input_optional = SingleTransitionBase.SimpleIO.input_optional + ('user_ctx',)

    def handle(self):
        self._set_response(*self.environ.sm.transit(
            self.environ.object_tag, self.request.input.state_new, self.environ.def_tag, 'zzz',
            self.request.input.get('user_ctx', None), self.request.input.force, False))

# ################################################################################################################################

class MassTransition(Base, JSONProducer):
    """ Performs transitions on a list of object.
    """
    name = 'zato.labs.transitions.mass-transition'

    def handle(self):
        out = []
        for item in loads(self.request.raw_request):
            out.append(self.invoke(Transition.name, item))

        self.response.payload = dumps(out)

# ################################################################################################################################

class GetHistory(SingleTransitionBase, JSONProducer):
    """ Returns a history of transitions for a given object
    """
    name = 'zato.labs.transitions.get-history'

    class SimpleIO:
        input_required = ('object_type', AsIs('object_id'))

    def handle(self):
        self.response.payload = dumps(self.environ.sm.get_history(self.environ.object_tag, self.environ.def_tag))

# ################################################################################################################################

class GetDefinitionList(Base, JSONProducer):
    """ Returns all definition as JSON.
    """
    name = 'zato.labs.transitions.get-definition-list'

    def handle(self):
        self.response.payload = dumps([{name:data} for name, data in yield_definitions(self)])

# ################################################################################################################################

class FormatBase(Base):

    def_format = None

    def validate_input(self):
        format = self.request.input.get('format')
        if format and format not in self.def_format:
            raise BadRequest(self.cid, 'Format is not one of `{}`\n'.format(', '.join(self.def_format)))

# ################################################################################################################################

class GetDefinition(FormatBase):
    """ Returns a selected definition, as text, JSON or a diagram.
    """
    name = 'zato.labs.transitions.get-definition'
    def_format = FORMAT.DEFINITION

    class SimpleIO:
        input_optional = ('format', 'def_version', 'node_width', 'node_width', 'orientation')

    def handle(self):
        def_name = Definition.get_name(self.request.input.def_name)
        def_tag = Definition.get_tag(def_name, self.request.input.get('def_version') or CONST.DEFAULT_GRAPH_VERSION)

        if def_tag not in self.environ.sm.config:
            raise BadRequest(self.cid, 'No such definition `{}`\n'.format(def_tag))

        format = self.request.input.get('format') or 'diagram-png'
        format = format.replace('-', '_')

        getattr(self, '_handle_{}'.format(format))(def_tag)

    def _handle_text(self, def_tag):
        """ Returns a string representation of a definition.
        """
        return str(self.environ.sm.config[def_tag].def_)

    def _handle_json(self, def_tag):
        """ Returns a JSON representation of a definition.
        """
        return dumps(self.environ.sm.config[def_tag].orig_config)

    def _get_diagram(self, def_tag, needs_png=True, mime_type='image/png'):
        """ Returns either a diagram of a definition, or blockdiag's configuration of the diagram.
        """
        png, diag_def = self.environ.sm.get_def_diagram(
            def_tag, self.request.input.get('node_width'), self.request.input.get('orientation'))

        self.response.payload = png if needs_png else diag_def
        self.response.content_type = mime_type

    def _handle_diagram_png(self, def_tag):
        """ Returns a definition as a block diagram.
        """
        self._get_diagram(def_tag)

    def _handle_diagram_def(self, def_tag):
        """ Returns a definition as a blockdiag's configuration.
        """
        self._get_diagram(def_tag, False, 'text/plain')

# ################################################################################################################################

class GetCurrentStateInfo(GetDefinition):
    """ Returns information on an object's state in a given process as JSON or a diagram.
    """
    name = 'zato.labs.transitions.get-current-state-info'
    def_format = FORMAT.STATE

    class SimpleIO:
        input_required = ('format', 'object_type', AsIs('object_id'))
        input_optional = ('def_name', 'def_version')

    def _handle_json(self):
        return dumps(self.environ.sm.get_current_state_info(self.environ.object_tag, self.environ.def_tag))

    def _handle_diagram(self):
        raise NotImplementedError('TODO')

# ################################################################################################################################
