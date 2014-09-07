# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

# flake8: noqa

# stdlib
import os

# Cython
from Cython.Build import cythonize

# setuptools
from setuptools import setup, find_packages

import sys
if 'setuptools.extension' in sys.modules:
    m = sys.modules['setuptools.extension']
    m.Extension.__dict__ = m._Extension.__dict__

curdir = os.path.dirname(os.path.abspath(__file__))
version = '2.1'

setup(
    name = 'zato-cli',
    version = version,

    author = 'Zato Developers',
    author_email = 'info@zato.io',
    url = 'https://zato.io',

    package_dir = {'zato':''},
    packages = ['zato'],

    setup_requires=['setuptools_cython'],


    ext_modules = cythonize(['src/zato/cli/*.pyx']),

    zip_safe = False,
    entry_points = """
    [console_scripts]
    zato = zato.cli.zato_command:main
      """
)
