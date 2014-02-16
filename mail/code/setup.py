# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Axel Mendoza <aekroft at gmail.com>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from setuptools import setup, find_packages

version = '0.1'

setup(
      name = 'zato-mail',
      version = version,
      
      keyword = ' soa eai esb middleware messaging queueing asynchronous integration performance http zeromq framework events agile broker messaging server jms enterprise python middleware clustering amqp nosql websphere mq wmq mqseries ibm amqp zmq openerp mail',

      author = 'Msc. Axel Mendoza Pupo',
      author_email = 'aekroft@gmail.com',
      url = 'http://eloquentia.com.mx',

      package_dir = {'':'src'},
      packages = find_packages('src'),

      namespace_packages = ['zato'],
      
      install_requires=[
          'html2text',
      ],

      zip_safe = False,
)