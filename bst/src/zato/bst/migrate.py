# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
import logging

# Redis
import redis

# SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Zato
from zato.common.odb.model import Cluster

# zato-labs
try:
    from zato_bst_core import RedisBackend
    from zato_bst_sql import Item, label, SubGroup
except ImportError:
    from zato.bst.core import RedisBackend
    from zato.bst.sql import Item, label, SubGroup

# ################################################################################################################################

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ################################################################################################################################

def get_session(engine):
    session = sessionmaker() # noqa
    session.configure(bind=engine)
    return session()

# ################################################################################################################################

def migrate(args):

    logger.info('Migrating BST data using: `%s`', args.__dict__)

    connect_args = {'application_name':util.get_component_name('bst.migrate')} if args.odb_type == 'postgresql' else {}
    engine = create_engine(odb_util.get_engine_url(args), connect_args=connect_args)
    session = get_session(engine)

    c = session.query(Cluster).\
        filter(Cluster.id==args.cluster_id).\
        one()

    redis_conn = redis.StrictRedis(args.redis_host, args.redis_port, password=args.redis_password)
    redis_conn.ping()

    for current_key in redis_conn.keys(RedisBackend.PATTERN_STATE_CURRENT.format('*')):
        for object_tag, value in redis_conn.hgetall(current_key).items():

            def_tag = current_key.replace(RedisBackend.PATTERN_STATE_CURRENT.replace('{}', ''), '')

            sub_group_id, group_id = session.query(SubGroup.id, SubGroup.group_id).\
                filter(SubGroup.name==label.sub_group.conf.process_bst).\
                filter(SubGroup.cluster_id==c.id).\
                one()

            item = Item()
            item.name = label.item.process_bst_inst_current % (def_tag, object_tag)
            item.is_internal = False
            item.cluster_id = c.id
            item.group_id = group_id
            item.sub_group_id = sub_group_id
            item.value = value

            logger.info('Adding `current`, name:`%s`, value:`%s`', item.name, item.value)

            session.add(item)
            session.commit()

    for history_key in redis_conn.keys(RedisBackend.PATTERN_STATE_HISTORY.format('*')):
        for object_tag, value in redis_conn.hgetall(history_key).items():

            def_tag = history_key.replace(RedisBackend.PATTERN_STATE_HISTORY.replace('{}', ''), '')

            sub_group_id, group_id = session.query(SubGroup.id, SubGroup.group_id).\
                filter(SubGroup.name==label.sub_group.conf.process_bst).\
                filter(SubGroup.cluster_id==c.id).\
                one()

            item = Item()
            item.name = label.item.process_bst_inst_history % (def_tag, object_tag)
            item.is_internal = False
            item.cluster_id = c.id
            item.group_id = group_id
            item.sub_group_id = sub_group_id
            item.value = value

            logger.info('Adding `history`, name:`%s`, value:`%s`', item.name, item.value)

            session.add(item)
            session.commit()

    logger.info('BST data migrated')

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
    parser.add_argument('--odb_host', type=str, help='SQL host to connect to')
    parser.add_argument('--odb_port', type=str, help='SQL port to connect to')
    parser.add_argument('--odb_user', type=str, help='ODB username to connect with')
    parser.add_argument('--odb_password', type=str, help='Password for ODB user')
    parser.add_argument('--odb_db_name', type=str, help='Name of database to connect to')
    parser.add_argument('--cluster_id', type=str, help='ID of cluster to install BST in', required=True)
    parser.add_argument('--dev_mode', type=str, help='(Reserved for internal use)', default=False)

    parser.add_argument('--redis_host', type=str, help='Redis host to connect to', required=True)
    parser.add_argument('--redis_port', type=str, help='Redis port to connect to', required=True)
    parser.add_argument('--redis_password', type=str, help='Password for Redis user')
    parser.add_argument('--proc_names', type=str, help='Names of processes to migrate')

    migrate(parser.parse_args())
