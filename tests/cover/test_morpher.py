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
from hypothesis.searchstrategy.morpher import MorpherStrategy, Morpher

morphers = MorpherStrategy()
intlists = s.lists(s.integers())


def test_can_simplify_through_a_morpher():
    m = find(morphers, lambda x: bool(x.become(intlists)))
    assert m.become(intlists) == [0]


def test_can_simplify_text_through_a_morpher():
    m = find(morphers, lambda x: bool(x.become(s.text())))
    assert m.become(s.text()) == '0'


def test_can_simplify_lists_of_morphers():
    ms = find(
        s.lists(morphers),
        lambda x: sum(t.become(s.integers()) for t in x) >= 100
    )

    ls = [t.become(s.integers()) for t in ms]
    assert sum(ls) == 100


def test_can_simplify_through_two_morphers():
    m = find(morphers, lambda x: bool(x.become(morphers).become(intlists)))
    print(m)
    assert m.become(morphers).become(intlists) == [0]


def test_a_morpher_retains_its_data_on_reserializing():
    m = find(morphers, lambda x: sum(x.become(intlists)) > 1)
    m2 = morphers.from_basic(morphers.to_basic(m))
    assert m.become(intlists) == m2.become(intlists)


def test_can_clone_morphers_into_inactive_morphers():
    m = find(
        s.lists(morphers),
        lambda x: len(x) >= 2 and x[0].become(s.integers()) >= 0)
    m_as_ints = [x.become(s.integers()) for x in m]
    assert m_as_ints == [0, 0]


def test_can_simplify_a_morpher_for_two_types_simultaneously():
    m = find(
        morphers, lambda x: x.become(s.integers()) and x.become(s.text())
    )
    assert m.become(s.text()) == "0"
    assert m.become(s.integers()) == 1


def test_can_simplify_lists_of_morphers_with_mixed_types():
    m = find(
        s.lists(morphers),
        lambda xs: any(x.become(s.text()) for x in xs) and any(
            x.become(s.integers()) for x in xs))
    assert 1 <= len(m) <= 2
    m_as_ints = [x.become(s.integers()) for x in m]
    m_as_text = [x.become(s.text()) for x in m]
    assert "0" in m_as_text
    assert 1 in m_as_ints


def test_a_morpher_accumulates_strategies():
    m = Morpher(1, 1)
    m.become(s.integers())
    m.become(s.text())
    assert len(m.data) == 2
    assert m.data[0].strategy is not m.data[1].strategy
