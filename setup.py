#!/usr/bin/env python

# Copyright (c) Harri Rautila, 2011

# This file is part of sxsuite library. It is free software, distributed
# under the terms of the GNU Lesser General Public License Version 3,
# or any later version.
# See the COPYING file included in this archive

"""
setup.py file for sxsuite package.
"""
from distutils.core import setup, Extension

setup(name = 'sxsuite',
      version = '0.1',
      author = 'Harri Rautila',
      author_email = 'harri.rautila@gmail.com',
      description = """Xchange protocol suite""",
      packages = [ "sxsuite", "sxsuite.fix"]
      )
