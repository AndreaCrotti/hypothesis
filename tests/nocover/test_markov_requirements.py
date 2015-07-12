# coding=utf-8

# This file is part of Hypothesis (https://github.com/DRMacIver/hypothesis)

# Most of this work is copyright (C) 2013-2015 David R. MacIver
# (david@drmaciver.com), but it contains contributions by other. See
# https://github.com/DRMacIver/hypothesis/blob/master/CONTRIBUTING.rst for a
# full list of people who may hold copyright, and consult the git log if you
# need to determine who owns an individual contribution.

# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

# END HEADER

from __future__ import division, print_function, absolute_import, \
    unicode_literals

import hypothesis.strategies as st
from hypothesis import find


def test_random_1d_walk():
    def is_divergent(xs):
        c = 0
        lower = 0
        upper = 0
        for x in xs:
            if x:
                c += 1
            else:
                c -= 1
            lower = min(lower, c)
            upper = max(upper, c)
        return lower <= -20 and upper >= 20

    print(find(
        st.lists(st.booleans(), min_size=100, max_size=100), is_divergent
    ))
