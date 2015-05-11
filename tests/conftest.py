# coding=utf-8

# Copyright (C) 2013-2015 David R. MacIver (david@drmaciver.com)

# This file is part of Hypothesis (https://github.com/DRMacIver/hypothesis)

# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

# END HEADER

from __future__ import division, print_function, absolute_import, \
    unicode_literals

import gc
import warnings
from tempfile import mkdtemp

import pytest
from hypothesis import Settings
from hypothesis.settings import set_hypothesis_home_dir

warnings.filterwarnings('error', category=UnicodeWarning)

set_hypothesis_home_dir(mkdtemp())

Settings.default.max_examples = 1000
Settings.default.max_iterations = 1500
Settings.default.timeout = -1
Settings.default.strict = True

try:
    import resource
    MAX_MEMORY = 10
    resource.setrlimit(resource.RLIMIT_DATA, (MAX_MEMORY, MAX_MEMORY))
except ImportError:
    pass


@pytest.fixture(scope='function', autouse=True)
def some_fixture():
    gc.collect()
