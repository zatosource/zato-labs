# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

"""
Copyright (C) 2016 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-Source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import logging

# havocbot
from havocbot.clients.hipchat import HipChat as _HipChat

# ################################################################################################################################

logger = logging.getLogger(__name__)

# ################################################################################################################################

class HipChat(_HipChat):

    @property
    def integration_name(self):
        return 'zato_hipchat'

    def handle_message(self, **kwargs):
        logger.info(kwargs)

# ################################################################################################################################
