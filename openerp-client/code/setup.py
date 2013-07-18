# -*- coding: utf-8 -*-

"""
Copyright (C) 2013 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from setuptools import setup, find_packages

version = '1.1.1'

setup(
      name = 'zato-openerp-client',
      version = version,

      author = 'Zato Developers',
      author_email = 'info@zato.io',
      url = 'https://zato.io',

      package_dir = {'':'src'},
      packages = find_packages('src'),

      namespace_packages = ['zato'],
      
      install_requires=[
          'openerp-client-lib==1.1.2',
          ],

      zip_safe = False,
)