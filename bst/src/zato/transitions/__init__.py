# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from copy import deepcopy
from cStringIO import StringIO
from datetime import datetime
from json import dumps, loads
from logging import getLogger
from string import Template
from uuid import uuid4
import os

# Arrow
from arrow import get as arrow_get

# Blockdiag
from blockdiag.parser import parse_string
from blockdiag.builder import ScreenNodeBuilder
from blockdiag.drawer import DiagramDraw
from blockdiag.imagedraw import png
from blockdiag.imagedraw.png import setup as png_setup
from blockdiag.noderenderer import beginpoint, box, endpoint, roundedbox
from blockdiag.noderenderer.beginpoint import setup as beginpoint_setup
from blockdiag.noderenderer.box import setup as box_setup
from blockdiag.noderenderer.endpoint import setup as endpoint_setup
from blockdiag.noderenderer.roundedbox import setup as roundedbox_setup

# Bunch
from bunch import Bunch

# ConfigObj
from configobj import ConfigObj

# PyTZ
import pytz

# ################################################################################################################################

logger = getLogger(__name__)

# ################################################################################################################################

png_setup(png)

beginpoint_setup(beginpoint)
box_setup(box)
endpoint_setup(endpoint)
roundedbox_setup(roundedbox)

# ################################################################################################################################

class CONST:
    NO_SUCH_NODE = 'NO_SUCH_NODE'
    DEFAULT_DIAG_HIGHLIGHT_COLOR = 'bccc73'
    DEFAULT_DIAG_NODE_WIDTH = 200
    DEFAULT_DIAG_ORIENTATION = 'portrait'
    DEFAULT_DIAG_DT_FORMAT = '%a %d/%m/%y %H:%M:%S'
    DEFAULT_DIAG_TZ = 'UTC'
    DEFAULT_GRAPH_VERSION = 1
    DIAG_ORIENTATION = ['portrait', 'landscape']
    PRETTY_PRINT_REPLACE = {
        'Force stop:': 'force_stop=',
        'Objects:': 'objects=',
        'Version:': 'version=',
    }
    DIAG_DEF_TEMPLATE = """
blockdiag {
   orientation = $orientation;
   default_shape = box;
   node_width = $node_width;
   class emphasis [color="#$highlight_color", style = dashed];

group {
  orientation = portrait;
  color = "#ccccdd";
$forced_stop
}

   begin [shape = beginpoint];
   end [shape = endpoint];

$labels

$edges
}
""".lstrip()

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
                return AddEdgeResult(False, CONST.NO_SUCH_NODE, node)
        return func(self, from_, to)
    return _inner

# ################################################################################################################################

def parse_pretty_print(value):

    value = value.splitlines()
    out = StringIO()
    sep_idx = None

    for idx, line in enumerate(value):
        if line.strip().startswith('-'):
            sep_idx = idx
            break
    else:
        raise ValueError('Could not find header separator in `{}`'.format(value))

    header = '[{}]'.format(value[sep_idx-1].strip())
    items = [item.strip() for item in value[sep_idx+1:] if item]

    out.write('{}\n'.format(header))

    for item in items:
        for source, target in CONST.PRETTY_PRINT_REPLACE.items():
            if item.startswith(source):
                item = item.replace(source, target)
        item = item.replace(': ', '=', 1).replace(':', '=', 1).replace('= ', '=', 1)
        out.write('{}\n'.format(item))

    value = out.getvalue()
    out.close()

    return value.strip()

# ################################################################################################################################

def yield_definitions(service):

    bst_dir = os.path.join(service.server.base_dir, 'config', 'repo', 'bst')
    for name in os.listdir(bst_dir):
        full_name = os.path.join(bst_dir, name)
        value = ConfigObj(parse_pretty_print(open(full_name).read()).splitlines())

        for key, value in value.items():
            yield key, value

# ################################################################################################################################

def setup_server_config(service):
    config = {}
    for name, data in yield_definitions(service):
        # .. parse the definition and append to the state machine's config dict
        item = ConfigItem()
        item.parse_config_dict({name:data})
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
    def __init__(self, name=None, version=CONST.DEFAULT_GRAPH_VERSION):
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
        self.def_config = {}
        self.orig_config = {}

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

    def parse_config_dict(self, orig_config):

        # So that the original, possibly still kept in a service's self.user_config, is not modified
        self.def_config = deepcopy(orig_config)

        # Handy to keep it around because higher level layers may wish to consult it
        self.orig_config.update(deepcopy(orig_config))

        # There will be exactly one key
        orig_key = self.def_config.keys()[0]
        def_name = Definition.get_name(orig_key)
        self.def_config[def_name] = self.def_config[orig_key]
        self.def_.name = def_name

        # Version is optional
        self.def_.version = self.def_config[self.def_.name].pop('version', CONST.DEFAULT_GRAPH_VERSION)

        # Extend attributes that may either strings or lists in config
        self._extend_list(self.def_config, 'objects')
        self._extend_list(self.def_config, 'force_stop')

        # Collect nodes and edges
        self._add_nodes_edges(self.def_config)
        self._add_nodes_edges(self.def_config, False)

        # Set correct tag
        self.def_.tag = Definition.get_tag(self.def_.name, self.def_.version)

    def parse_config_ini(self, data):

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
        self.object_type_to_def = {}

        # Prepares database and run-time structures
        if run_set_up:
            self.set_up()

    def set_up(self):
        # Map object types to definitions they are contained in.
        for def_tag, config_item in self.config.items():
            for object_type in config_item.objects:
                defs = self.object_type_to_def.setdefault(object_type, [])
                defs.append(def_tag)

    @staticmethod
    def get_object_tag(object_type, object_id):
        return '{}.{}'.format(object_type, object_id)

    def get_def_tag(self, object_type, object_id, state_new, def_name, def_version):
        def_tag = self.object_type_to_def[object_type]

        if len(def_tag) > 1:
            msg = 'Ambiguous input. Object `{}` maps to more than one definition `{}` '\
                '(id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                object_type, ', '.join(def_tag), object_id, state_new, def_name, def_version)
            logger.warn(msg)
            raise TransitionError(msg)

        # Ok, we've got it now after ensuring there is only one definition for that object type
        return def_tag[0]

# ################################################################################################################################

    def get_transition_info(self, state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, is_forced):
        return {
            'state_old': state_current,
            'state_current': state_new,
            'object_tag': object_tag,
            'def_tag': def_tag,
            'transition_ts_utc': datetime.utcnow().isoformat(),
            'server_ctx': server_ctx,
            'user_ctx': user_ctx,
            'is_forced': is_forced or False
        }

# ################################################################################################################################

    def can_transition(self, object_tag, state_new, def_tag, force=False):

        # Obtain graph object's config
        config = self.config[def_tag]

        # Find the current state of this object in backend
        state_current_info = self.backend.get_current_state_info(object_tag, config.def_.tag)
        state_current = state_current_info['state_current'] if state_current_info else None

        # Could be a a forced transition so if state_new exists at all in the definition, this is all good.
        if force and state_new in config.def_.nodes:
            return True, '', state_current

        # Perhaps it's a forced stop interrupting the process immediately.
        # However, unless forced to, we don't want to transition the same stop state.
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

    def transition(self, object_tag, state_new, def_tag, server_ctx, user_ctx=None, force=False, raise_on_error=True):

        # Make sure this is a valid transition
        can_transition, reason, state_current = self.can_transition(object_tag, state_new, def_tag, force)

        if not can_transition:
            if raise_on_error:
                raise TransitionError(reason)
            else:
                return can_transition, reason, state_current, state_new

        self.backend.set_current_state_info(
            object_tag, def_tag, dumps(self.get_transition_info(
                state_current, state_new, object_tag, def_tag, server_ctx, user_ctx, force)))

        return can_transition, reason, state_current, state_new

# ################################################################################################################################

    def mass_transition(self, items):
        for item in items:
            self.transition(*item)

# ################################################################################################################################

    def get_current_state_info(self, object_tag, def_tag):
        state_info = self.backend.get_current_state_info(object_tag, def_tag)
        state_info['object_tag'] = object_tag
        state_info['def_tag'] = def_tag
        return state_info

# ################################################################################################################################

    def get_history(self, object_tag, def_tag):
        return [loads(elem) for elem in self.backend.get_history(object_tag, def_tag)]

# ################################################################################################################################

    def get_diagram_safe_name(self, name):
        return name.strip().lower().replace(' ', '_')

    def reformat_date(self, value, time_zone, date_time_format):
        value = arrow_get(value).replace(tzinfo=pytz.UTC)
        local_tz = pytz.timezone(time_zone)
        return local_tz.normalize(value.astimezone(local_tz)).strftime(date_time_format)

    def get_name_state(self, name, state_info, time_zone, date_time_format, is_stop):
        if not state_info:
            return name

        history = self.get_history(state_info.object_tag, state_info.def_tag)

        is_stop=' (s)' if is_stop else ''
        tz_sep = '\n' if len(time_zone) > 5 else '' # So that for instance America/New_York fits in a single line

        if name == state_info.state_current:
            return '{name}{is_stop}{is_forced}\n{date} {tz_sep}{time_zone}'.format(
                name=name,
                is_stop=is_stop,
                is_forced=' (f)' if state_info.is_forced else '',
                date=self.reformat_date(state_info.transition_ts_utc, time_zone, date_time_format),
                tz_sep=tz_sep,
                time_zone=time_zone)

        elif name == state_info.state_old:

            # We know there is some previous state so we can get history
            # for this object and look up the penultimate element which points to the previous state.
            previous = history[-2]

            return '{name}{is_stop}{is_forced}\n{date} {tz_sep}{time_zone}'.format(
                name=name,
                is_stop=is_stop,
                is_forced=' (f)' if previous['is_forced'] else '',
                date=self.reformat_date(previous['transition_ts_utc'], time_zone, date_time_format),
                tz_sep=tz_sep,
                time_zone=time_zone)

        return name

    def get_diagram_label(self, name, state_info, time_zone, date_time_format, is_stop=False):
        item = '{name_safe} [label="{name_state}" {options}]'

        if state_info and name in (state_info.state_current, state_info.state_old):
            options = ', class="emphasis"'
        else:
            options = ''

        return item.format(
            name_safe=self.get_diagram_safe_name(name),
            name_state=self.get_name_state(name, state_info, time_zone, date_time_format, is_stop),
            options=options)

# ################################################################################################################################

    def get_diagram(self, def_tag, node_width=None, orientation=None, highlight_color=None, state_info=None, time_zone=None,
            date_time_format=None, include_force_stop=True):

        node_width = node_width or CONST.DEFAULT_DIAG_NODE_WIDTH
        orientation = orientation or CONST.DEFAULT_DIAG_ORIENTATION
        highlight_color = highlight_color.replace('#', '') if highlight_color else CONST.DEFAULT_DIAG_HIGHLIGHT_COLOR
        time_zone = time_zone or CONST.DEFAULT_DIAG_TZ
        date_time_format = date_time_format or CONST.DEFAULT_DIAG_DT_FORMAT

        config_item = self.config[def_tag]
        name = config_item.def_config.keys()[0] # There will be one key only
        config = config_item.def_config[name]

        forced_stop = []
        labels = []
        edges = []

        for from_, to in config.items():
            from_safe = self.get_diagram_safe_name(from_)
            if isinstance(to, basestring):
                to = [to]

            # Regular edges
            for to in to:
                to_safe = self.get_diagram_safe_name(to)

                edges.append('{} -> {};'.format(from_safe, to_safe))

                # Labels separately so nodes can contain whitespace

                from_label = self.get_diagram_label(from_, state_info, time_zone, date_time_format)
                if from_label not in labels:
                    labels.append(from_label)

                to_label = self.get_diagram_label(to, state_info, time_zone, date_time_format)
                if to_label not in labels:
                    labels.append(to_label)

                # Leaves
                if to not in config:
                    edges.append('{} -> end;'.format(to_safe))

            # Roots
            if from_ in config_item.def_.roots:
                edges.append('begin -> {};'.format(from_safe))

        # Forced stops
        if include_force_stop:
            for name in config_item.force_stop:
                forced_stop.append(self.get_diagram_label(name, state_info, time_zone, date_time_format, True))

        forced_stop = '\n'.join(sorted('   {}'.format(elem) for elem in forced_stop))
        labels = '\n'.join(sorted('   {}'.format(elem) for elem in labels))
        edges = '\n'.join(sorted('   {}'.format(elem) for elem in edges))

        diag_def = Template(CONST.DIAG_DEF_TEMPLATE).safe_substitute(
            highlight_color=highlight_color,
            orientation=orientation,
            node_width=node_width,
            forced_stop=forced_stop,
            labels=labels,
            edges=edges)

        try:
            diagram = ScreenNodeBuilder.build(parse_string(diag_def))
            draw = DiagramDraw('png', diagram)
            draw.draw()
        except Exception:
            msg = 'Could not obtain diagram from definition:\n{}'.format(diag_def)
            logger.warn(msg)
            raise

        return draw.save(), diag_def

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

        if 'zato_state_machine' not in service.server.user_ctx:
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

            if self.object_type not in self.state_machine.object_type_to_def:
                msg = 'Unknown object type `{}` (id:`{}`, state_new:`{}`, def_name:`{}`, def_version:`{}`)'.format(
                    self.object_type, self.object_id, self.state_new, self.def_name, self.def_version)
                logger.warn(msg)
                raise TransitionError(msg)

            self.def_tag = self.state_machine.get_def_tag(
                self.object_type, self.object_id, self.state_new, self.def_name, self.def_version)

        can_transition, reason, _ = self.state_machine.can_transition(self.object_tag, self.state_new, self.def_tag, self.force)
        if not can_transition:
            raise TransitionError(reason)

        return self.ctx

    def __exit__(self, exc_type, exc_value, traceback):

        if not exc_type:
            # TODO: Use server_ctx in .transit
            self.state_machine.transition(
                self.object_tag, self.state_new, self.def_tag, None, self.ctx, self.force)
            return True

# ################################################################################################################################