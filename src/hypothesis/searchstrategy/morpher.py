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

from copy import copy
from random import Random
from collections import namedtuple
from hypothesis.internal.tracker import Tracker


from hypothesis.internal.compat import hrange, integer_types
from hypothesis.searchstrategy.strategies import BadData, SearchStrategy, \
    check_basic, check_length, check_data_type

StoredAsBasic = namedtuple('StoredAsBasic', ('basic',))
StoredAsDeferred = namedtuple('StoredAsDeferred', ('strategy', 'template'))


def record_to_basic(record):
    if isinstance(record, StoredAsBasic):
        return record.basic
    else:
        return record.strategy.to_basic(record.template)


def tupleize(x):
    if isinstance(x, list):
        return tuple(map(tupleize, x))
    else:
        return x


class Morpher(object):

    def __init__(
        self,
        parameter_seed, template_seed,
        data=None
    ):
        if data is None:
            data = []
        self.parameter_seed = parameter_seed
        self.template_seed = template_seed
        self.data = data
        self.seen_reprs = set()

    def collapse_data(self):
        new_data = []
        t = Tracker()
        for record in self.data:
            as_basic = record_to_basic(record)
            if t.track(as_basic) == 1:
                new_data.append(StoredAsBasic(as_basic))
        self.data = new_data

    def prune_unused(self):
        self.data = [r for r in self.data if isinstance(r, StoredAsDeferred)]

    def __hash__(self):
        return hash(self.sig_tuple())

    def __eq__(self, other):
        return isinstance(other, Morpher) and (
            self.sig_tuple() == other.sig_tuple()
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def sig_tuple(self):
        return (
            self.parameter_seed, self.template_seed,
            tupleize(list(map(record_to_basic, self.data)))
        )

    def become(self, strategy):
        return strategy.reify(self.template_for(strategy))

    def __copy__(self):
        result = Morpher(
            self.parameter_seed, self.template_seed,
            list(self.data),
        )
        return result

    def __trackas__(self):
        return (
            'Morpher', self.parameter_seed, self.template_seed,
            list(map(record_to_basic, self.data)),
        )

    def __repr__(self):
        return 'Morpher(%d, %d, %r)' % (
            self.parameter_seed, self.template_seed, self.data
        )

    def strategies(self):
        for record in self.data:
            if isinstance(record, StoredAsDeferred):
                yield record.strategy

    def template_for(self, strategy):
        for i in hrange(len(self.data)):
            record = self.data[i]
            if (
                isinstance(record, StoredAsDeferred) and
                record.strategy is strategy
            ):
                del self.data[i]
                self.data.append(record)
                return record.template
            elif isinstance(record, StoredAsBasic):
                try:
                    active_template = strategy.from_basic(record.basic)
                    self.data.append(
                        StoredAsDeferred(strategy, active_template))
                    return active_template
                except BadData:
                    pass
        param = strategy.draw_parameter(Random(self.parameter_seed))
        active_template = strategy.draw_template(
            Random(self.template_seed), param)
        self.data.append(StoredAsDeferred(strategy, active_template))
        return active_template


class MorpherStrategy(SearchStrategy):

    def __repr__(self):
        return 'MorpherStrategy()'

    def draw_parameter(self, random):
        return random.getrandbits(64)

    def draw_template(self, random, parameter):
        return Morpher(parameter, random.getrandbits(64))

    def reify(self, template):
        return template

    def to_basic(self, template):
        template.collapse_data()
        return [
            template.parameter_seed, template.template_seed,
            list(map(record_to_basic, template.data))
        ]

    def from_basic(self, data):
        check_length(3, data)
        check_data_type(integer_types, data[0])
        check_data_type(integer_types, data[1])
        check_data_type(list, data[2])
        check_basic(data[2])
        return Morpher(data[0], data[1], list(map(StoredAsBasic, data[2])))

    def simplifiers(self, random, template):
        for strategy in template.strategies():
            for simplifier in strategy.simplifiers(
                random, template.template_for(strategy)
            ):
                yield self.convert_simplifier(strategy, simplifier)

    def strictly_simpler(self, x, y):
        strategies = list(x.strategies()) + list(y.strategies())
        if not strategies:
            return x.template_seed < y.template_seed

        for strategy in strategies:
            if not strategy.strictly_simpler(
                x.template_for(strategy), y.template_for(strategy)
            ):
                return False
        return True

    def convert_simplifier(self, strategy, simplifier):
        def accept(random, template):
            converted = template.template_for(strategy)
            for simpler in simplifier(random, converted):
                new_template = copy(template)
                new_template.data.pop()
                new_template.prune_unused()
                new_template.data.append(StoredAsBasic(
                    strategy.to_basic(simpler)
                ))
                new_template.data.append(StoredAsDeferred(
                    strategy, simpler
                ))
                yield new_template
        accept.__name__ = str(
            'convert_simplifier(%r, %s)' % (strategy, simplifier.__name__))
        return accept
