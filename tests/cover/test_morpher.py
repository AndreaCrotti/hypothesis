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

import hypothesis.strategies as s
from hypothesis import find
from hypothesis.searchstrategy.morpher import MorpherStrategy

morphers = MorpherStrategy()
intlists = s.lists(s.integers())


def test_can_simplify_through_a_morpher():
    m = find(morphers, lambda x: bool(x.become(intlists)))
    assert m.become(intlists) == [0]


def test_can_simplify_lists_of_morphers():
    ms = find(
        s.lists(morphers),
        lambda x: sum(t.become(s.integers()) for t in x) >= 100
    )

    ls = [t.become(s.integers()) for t in ms]
    assert sum(ls) == 100


def test_can_simplify_through_two_morphers():
    m = find(morphers, lambda x: bool(x.become(morphers).become(intlists)))
    assert m.become(morphers).become(intlists) == [0]


def test_a_morpher_retains_its_data_on_reserializing():
    m = find(morphers, lambda x: sum(x.become(intlists)) > 1)
    m2 = morphers.from_basic(morphers.to_basic(m))
    assert m.become(intlists) == m2.become(intlists)
