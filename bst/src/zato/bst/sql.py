# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import logging

# dictalchemy
from dictalchemy import make_class_dictable

# SQLAlchemy
from sqlalchemy import Boolean, Column, create_engine, ForeignKey, Integer, Sequence, String, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, relationship, sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

Base = declarative_base()
make_class_dictable(Base)

# ################################################################################################################################

class label:
    """ Each object has its name and all of them are kept here. They are either simple labels
    or patterns with placeholds to fill with actual data in run-time.
    """
    class group:
        """ Names of groups.
        """
        class conf:
            """ Configuration items.
            """
            process = 'zato.conf.process'

    class sub_group:
        """ Names of sub-groups.
        """
        class conf:
            """ Configuration items.
            """
            process_bst = 'zato.conf.process.bst'

    class item:
        """ Actual items such as configuration values or run-time instances.
        """
        process_bst_inst_current = 'zato.inst.process.bst.current.%s.%s'
        process_bst_inst_history = 'zato.inst.process.bst.history.%s.%s'

# ################################################################################################################################

def get_session(engine):
    session = sessionmaker() # noqa
    session.configure(bind=engine)
    return session()

# ################################################################################################################################

class Cluster(Base):
    """ Convenience class used only during development while BST is in zato-labs.
    """
    __tablename__ = 'cluster'

    id = Column(Integer, Sequence('data_cluster_seq'), primary_key=True)

# ################################################################################################################################

class Group(Base):
    """ Groups common items.
    """
    __tablename__ = 'data_group'
    __table_args__ = (UniqueConstraint('cluster_id', 'name'), {})

    id = Column(Integer, Sequence('data_group_seq'), primary_key=True)
    name = Column(String(2048), unique=True, nullable=False)
    is_internal = Column(Boolean(), nullable=False)

    cluster_id = Column(Integer, ForeignKey('cluster.id', ondelete='CASCADE'), nullable=False)

# ################################################################################################################################

class SubGroup(Base):
    """ A sub-group within a larger group of items.
    """
    __tablename__ = 'data_sub_group'
    __table_args__ = (UniqueConstraint('cluster_id', 'group_id', 'name'), {})

    id = Column(Integer, Sequence('data_sub_group_seq'), primary_key=True)
    name = Column(String(2048), unique=True, nullable=False)
    is_internal = Column(Boolean(), nullable=False)

    group_id = Column(Integer, ForeignKey('data_group.id', ondelete='CASCADE'), nullable=False)
    group = relationship(Group, backref=backref('sub_groups', order_by=name, cascade='all, delete, delete-orphan'))

    cluster_id = Column(Integer, ForeignKey('cluster.id', ondelete='CASCADE'), nullable=False)

# ################################################################################################################################

class Item(Base):
    """ The fundamental building block to construct configuration or runtime user-owned objects.
    Belongs to a sub-group, group and is optionally described through one or more tags.
    Column 'value' is in JSON. Some attributes are redundant for convenience - for instance, an item's group could be
    worked out through its sub-group. Likewise, tags may duplicate information that is already in 'value' - this is done
    so as not to require 'value' to be parsed on client side in order to extract data or filter by 'value's contents.
    """
    __tablename__ = 'data_item'
    __table_args__ = (UniqueConstraint('cluster_id', 'group_id', 'sub_group_id', 'name'), {})

    id = Column(Integer, Sequence('data_item_seq'), primary_key=True)
    parent_id = Column(Integer, ForeignKey('data_item.id', ondelete='CASCADE'), nullable=True)
    is_internal = Column(Boolean(), nullable=False)
    is_active = Column(Boolean(), nullable=False, default=True)

    name = Column(String(2048), unique=True, nullable=False)
    value = Column(Text, nullable=True)

    # Foreign keys are for both groups and sub-groups

    group_id = Column(Integer, ForeignKey('data_group.id', ondelete='CASCADE'), nullable=False)
    group = relationship(Group, backref=backref('items', order_by=name, cascade='all, delete, delete-orphan'))

    sub_group_id = Column(Integer, ForeignKey('data_sub_group.id', ondelete='CASCADE'), nullable=False)
    sub_group = relationship(SubGroup, backref=backref('items', order_by=name, cascade='all, delete, delete-orphan'))

    cluster_id = Column(Integer, ForeignKey('cluster.id', ondelete='CASCADE'), nullable=False)

# ################################################################################################################################

class Tag(Base):
    """ A tag that can be attached to any object.
    """
    __tablename__ = 'data_tag'
    __table_args__ = (UniqueConstraint('cluster_id', 'name'), {})

    id = Column(Integer, Sequence('data_tag_seq'), primary_key=True)
    name = Column(String(2048), unique=True, nullable=False)
    is_internal = Column(Boolean(), nullable=False)
    value = Column(Text, nullable=True)

    cluster_id = Column(Integer, ForeignKey('cluster.id', ondelete='CASCADE'), nullable=False)

# ################################################################################################################################

class GroupTag(Base):
    """ An N:N association between groups and tags.
    """
    __tablename__ = 'data_group_tag'
    __table_args__ = (UniqueConstraint('group_id', 'tag_id'), {})

    id = Column(Integer, Sequence('data_group_tag_seq'), primary_key=True)

    group_id = Column(Integer, ForeignKey('data_group.id', ondelete='CASCADE'), nullable=False)
    group = relationship(Group, backref=backref('tags', order_by=id, cascade='all, delete, delete-orphan'))

    tag_id = Column(Integer, ForeignKey('data_tag.id', ondelete='CASCADE'), nullable=False)
    tag = relationship(Tag, backref=backref('groups', order_by=id, cascade='all, delete, delete-orphan'))

# ################################################################################################################################

class SubGroupTag(Base):
    """ An N:N association between sub-groups and tags.
    """
    __tablename__ = 'data_sub_group_tag'
    __table_args__ = (UniqueConstraint('sub_group_id', 'tag_id'), {})

    id = Column(Integer, Sequence('data_sub_group_tag_seq'), primary_key=True)

    sub_group_id = Column(Integer, ForeignKey('data_sub_group.id', ondelete='CASCADE'), nullable=False)
    sub_group = relationship(SubGroup, backref=backref('tags', order_by=id, cascade='all, delete, delete-orphan'))

    tag_id = Column(Integer, ForeignKey('data_tag.id', ondelete='CASCADE'), nullable=False)
    tag = relationship(Tag, backref=backref('sub_groups', order_by=id, cascade='all, delete, delete-orphan'))

# ################################################################################################################################

class ItemTag(Base):
    """ An N:N association between items and tags.
    """
    __tablename__ = 'data_item_tag'
    __table_args__ = (UniqueConstraint('item_id', 'tag_id'), {})

    id = Column(Integer, Sequence('data_item_tag_seq'), primary_key=True)

    item_id = Column(Integer, ForeignKey('data_item.id', ondelete='CASCADE'), nullable=False)
    item = relationship(Item, backref=backref('tags', order_by=id, cascade='all, delete, delete-orphan'))

    tag_id = Column(Integer, ForeignKey('data_tag.id', ondelete='CASCADE'), nullable=False)
    tag = relationship(Tag, backref=backref('items', order_by=id, cascade='all, delete, delete-orphan'))

# ################################################################################################################################

def setup(args):

    logger.info('Setting up BST in `%s`', args.__dict__)

    connect_args = {'application_name':util.get_component_name('bst')} if args.odb_type == 'postgresql' else {}
    engine = create_engine(odb_util.get_engine_url(args), connect_args=connect_args)

    Base.metadata.create_all(engine)

    session = get_session(engine)

    if args.dev_mode:
        c = Cluster()
    else:
        # Override our development-only Cluster class with the actual one if not in dev mode
        from zato.common.odb.model import Cluster
        c = session.query(Cluster).\
            filter(Cluster.id==args.cluster_id).\
            one()

    g = Group()
    g.name = label.group.conf.process
    g.is_internal = True

    if args.dev_mode:
        g.cluster = c
    else:
        g.cluster_id = c.id

    sg = SubGroup()
    sg.name = label.sub_group.conf.process_bst
    sg.is_internal = True
    sg.group = g

    if args.dev_mode:
        sg.cluster = c
    else:
        sg.cluster_id = c.id

    session.add(c)
    session.add(g)
    session.add(sg)

    session.commit()

    logger.info('BST set up')

# ################################################################################################################################

if __name__ == '__main__':

    # stdlib
    import argparse

    # Zato
    from zato.common import util
    from zato.common.odb import util as odb_util

    db_choices = ('mysql', 'postgresql', 'oracle', 'sqlite')

    parser = argparse.ArgumentParser(description='Set up BST in a Zato 2.0 environment')
    parser.add_argument('--odb_type', type=str, help='Type of database to connect to', choices=db_choices, required=True)
    parser.add_argument('--odb_port', type=str, help='SQL port to connect to')
    parser.add_argument('--odb_host', type=str, help='SQL host to connect to')
    parser.add_argument('--odb_user', type=str, help='Username to connect with')
    parser.add_argument('--odb_password', type=str, help='Password for user')
    parser.add_argument('--odb_db_name', type=str, help='Name of database to connect to')
    parser.add_argument('--cluster_id', type=str, help='ID of cluster to install BST in', required=True)
    parser.add_argument('--dev_mode', type=str, help='(Reserved for internal use)', default=False)

    setup(parser.parse_args())
