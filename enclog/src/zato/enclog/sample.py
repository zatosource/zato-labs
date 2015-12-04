# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function, unicode_literals

"""
Copyright (C) 2015 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# Part of Zato - Open-source ESB, SOA, REST, APIs and Cloud Integrations in Python
# https://zato.io

# stdlib
import logging

# cryptography
from cryptography.fernet import Fernet

# Zato
from enclog import EncryptedLogFormatter

level = logging.INFO
format = '%(levelname)s - %(message)s'

fernet_key = Fernet.generate_key()
formatter = EncryptedLogFormatter(fernet_key, format)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger('')
logger.addHandler(handler)
logger.setLevel(level)

logger.info(b'{"user":"Jane Xi"}')
