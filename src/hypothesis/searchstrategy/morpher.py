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


class Morpher(object):

    def __init__(
        self,
        parameter_seed, template_seed,
        data=None, active_strategy=None
    ):
        if data is None:
            data = []
        self.parameter_seed = parameter_seed
        self.template_seed = template_seed
        self.data = data
        self.active_strategy = active_strategy

    def become(self, strategy):
        return strategy.reify(self.template_for(strategy))

    def __copy__(self):
        result = Morpher(
            self.parameter_seed, self.template_seed,
            list(self.data), self.active_strategy
        )
        result.active_template = self.active_template
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

    def template_for(self, strategy):
        if strategy is self.active_strategy:
            return self.active_template
        self.active_strategy = strategy
        for i in hrange(len(self.data)):
            try:
                record = self.data[i]
                del self.data[i]
                self.active_template = strategy.from_basic(
                    record_to_basic(record))
                self.data.append(
                    StoredAsDeferred(strategy, self.active_template))
                return self.active_template
            except BadData:
                pass
        param = strategy.draw_parameter(Random(self.parameter_seed))
        self.active_template = strategy.draw_template(
            Random(self.template_seed), param)
        self.data.append(StoredAsDeferred(strategy, self.active_template))
        return self.active_template


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
        if template.active_strategy is None:
            return
        strategy = template.active_strategy
        for simplifier in strategy.simplifiers(
            random, template.active_template
        ):
            yield self.convert_simplifier(strategy, simplifier)

    def convert_simplifier(self, strategy, simplifier):
        def accept(random, template):
            converted = template.template_for(strategy)
            for simpler in simplifier(random, converted):
                new_template = copy(template)
                new_template.data.pop()
                new_template.data.append(StoredAsDeferred(
                    strategy, simpler
                ))
                new_template.active_template = simpler
                yield new_template
        accept.__name__ = str(
            'convert_simplifier(%r, %s)' % (strategy, simplifier.__name__))
        return accept
