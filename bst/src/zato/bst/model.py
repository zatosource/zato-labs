# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
from datetime import datetime
from operator import itemgetter

# SQLAlchemy
from sqlalchemy import create_engine

builtins = (str, int, dict, list, bool, tuple, datetime)

class CONST:
    ARG_SIMPLE = 'simple'
    ARG_ENUM = 'enum'
    ARG_USER_DEFINED = 'userdef'
    NO_DEFAULT = 'zato.nodef'

# ################################################################################################################################

class Model(object):

    def __repr__(self):
        all_attrs = []
        attrs = []
        max_len = 0
        max_value = 0

        for name in sorted(dir(self)):
            attr = getattr(self, name)
            if isinstance(attr, Attr):
                value = attr.get_value_as_str()
                value = value if value != CONST.NO_DEFAULT else '(none)'
                max_len = max(max_len, len(name))
                max_value = max(max_value, len(value))
                all_attrs.append((name, attr, attr.is_required, value))

        all_attrs.sort(key=itemgetter(2), reverse=True) # Sort by is_required, reversed order

        print(max_len)

        for name, attr, is_required, value in all_attrs:
            is_required_marker = '*' if isinstance(attr, required) else ' '
            name = name.ljust(max_len+2, b'.')
            attrs.append(' %s %s%s%s' % (is_required_marker, name, value, attr._arg_type))

        return '<%s at %s\n%s\n>' % (self.__class__.__name__, hex(id(self)), '\n'.join(attrs))

    def by_id(self, id):
        pass

# ################################################################################################################################

class Attr(object):

    def __repr__(self):
        return '<%s %s:%s (%s)>' % (self.__class__.__name__, self._type, self.args, hex(id(self)))

    def __init__(self, *args, **kwargs):
        self.is_required = isinstance(self, required)
        self.args = args
        self._type = None
        self._arg_type = None
        self._value = CONST.NO_DEFAULT

        if len(self.args) == 1:
            self._arg_type = args[0].__name__
            if self.args[0] in builtins:
                self._type = CONST.ARG_SIMPLE
            else:
                self._type = CONST.ARG_USER_DEFINED
        else:
            self._arg_type = 'enum: [%s]' % ', '.join(self.args)
            self._type = CONST.ARG_ENUM

    def get_value_as_str(self):
        return self._value if isinstance(self._value, basestring) else str(self._value)

# ################################################################################################################################

class required(Attr):
    pass

class optional(Attr):
    pass

class many(Attr):
    pass
'''
# ################################################################################################################################

class Upload(Model):
    created = required(datetime)
    gift_codes = many('gift.code')

    _name = 'gift.import'

# ################################################################################################################################

class GiftCode(Model):
    code = required(str)
    created = required(datetime)
    state = required('new', 'viewed')
    last_updated = optional(datetime)
    user = required('user')
    import_ = required(Upload)

    _name = 'gift.code'
    _index = code, last_updated
    _encrypted = True

# ################################################################################################################################

class User(Model):
    id = required(str)
    gift_codes = many(GiftCode)

    _name = 'user'
'''
# ################################################################################################################################

class Foo(Model):

    a1 = required(str)
    b1 = required(int)
    c1 = required(dict)
    e1 = required(tuple)
    ffff1 = required(bool)
    g1 = required(datetime)
    h1 = required('a', 'b', 'c')

    a2 = optional(str)
    aa2 = optional(str)
    b2 = optional(int)
    c2 = optional(dict)
    e2 = optional(tuple)
    f2 = optional(bool)
    ggggggggg2 = optional(datetime)

# ################################################################################################################################

if __name__ == '__main__':
    from sql import Base, Cluster, Group, GroupTag, Item, get_session, SubGroup, SubGroupTag, Tag

    engine = create_engine('sqlite:///model.db')
    Base.metadata.create_all(engine)
    session = get_session(engine)

    f = Foo()
    print(f)
