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

"""This module provides support for a stateful style of testing, where tests
attempt to find a sequence of operations that cause a breakage rather than just
a single value.

Notably, the set of steps available at any point may depend on the
execution to date.

"""

from __future__ import division, print_function, absolute_import, \
    unicode_literals

import inspect
import traceback
from random import Random
from unittest import TestCase
from collections import namedtuple

from hypothesis.core import find
from hypothesis.errors import Flaky, NoSuchExample, InvalidDefinition, \
    UnsatisfiedAssumption
from hypothesis.settings import Settings, Verbosity
from hypothesis.reporting import report, verbose_report, current_verbosity
from hypothesis.strategies import lists
from hypothesis.internal.compat import hrange
from hypothesis.searchstrategy.misc import JustStrategy, \
    SampledFromStrategy
from hypothesis.searchstrategy.morpher import MorpherStrategy
from hypothesis.searchstrategy.strategies import MappedSearchStrategy, \
    strategy, one_of_strategies
from hypothesis.searchstrategy.collections import TupleStrategy, \
    FixedKeysDictStrategy

Settings.define_setting(
    name='stateful_step_count',
    default=50,
    description="""
Number of steps to run a stateful program for before giving up on it breaking.
"""
)


class TestCaseProperty(object):  # pragma: no cover

    def __get__(self, obj, typ=None):
        if obj is not None:
            typ = type(obj)
        return typ._to_test_case()

    def __set__(self, obj, value):
        raise AttributeError('Cannot set TestCase')

    def __delete__(self, obj):
        raise AttributeError('Cannot delete TestCase')


def find_breaking_runner(state_machine_factory, settings=None):
    def is_breaking_run(runner):
        try:
            runner.run(state_machine_factory())
            return False
        except (InvalidDefinition, UnsatisfiedAssumption):
            raise
        except Exception:
            verbose_report(traceback.format_exc)
            return True
    if settings is None:
        try:
            settings = state_machine_factory.TestCase.settings
        except AttributeError:
            settings = Settings.default

    search_strategy = StateMachineSearchStrategy(settings)
    if settings.database is not None:
        storage = settings.database.storage(
            getattr(
                state_machine_factory, '__name__',
                type(state_machine_factory).__name__))
    else:
        storage = None

    return find(
        search_strategy,
        is_breaking_run,
        settings=settings,
        storage=storage,
    )


def run_state_machine_as_test(state_machine_factory, settings=None):
    """Run a state machine definition as a test, either silently doing nothing
    or printing a minimal breaking program and raising an exception.

    state_machine_factory is anything which returns an instance of
    GenericStateMachine when called with no arguments - it can be a class or a
    function. settings will be used to control the execution of the test.

    """
    try:
        breaker = find_breaking_runner(state_machine_factory, settings)
    except NoSuchExample:
        return

    breaker.run(state_machine_factory(), print_steps=True)
    raise Flaky(
        'Run failed initially but succeeded on a second try'
    )


class GenericStateMachine(object):

    """A GenericStateMachine is the basic entry point into Hypothesis's
    approach to stateful testing.

    The intent is for it to be subclassed to provide state machine descriptions

    The way this is used is that Hypothesis will repeatedly execute something
    that looks something like:

    x = MyStatemachineSubclass()
    for _ in range(n_steps):
        x.execute_step(x.steps().example())

    And if this ever produces an error it will shrink it down to a small
    sequence of example choices demonstrating that.

    """

    def steps(self):
        """Return a SearchStrategy instance the defines the available next
        steps."""
        raise NotImplementedError('%r.steps()' % (self,))

    def execute_step(self, step):
        """Execute a step that has been previously drawn from self.steps()"""
        raise NotImplementedError('%r.execute_steps()' % (self,))

    def print_step(self, step):
        """Print a step to the current reporter.

        This is called right before a step is executed.

        """
        self.step_count = getattr(self, 'step_count', 0) + 1
        report('Step #%d: %s' % (self.step_count, repr(step)))

    def teardown(self):
        """Called after a run has finished executing to clean up any necessary
        state.

        Does nothing by default

        """
        pass

    _test_case_cache = {}

    TestCase = TestCaseProperty()

    @classmethod
    def _to_test_case(state_machine_class):
        try:
            return state_machine_class._test_case_cache[state_machine_class]
        except KeyError:
            pass

        class StateMachineTestCase(TestCase):
            settings = Settings()

            def runTest(self):
                run_state_machine_as_test(state_machine_class)

        base_name = state_machine_class.__name__
        StateMachineTestCase.__name__ = str(
            base_name + '.TestCase'
        )
        StateMachineTestCase.__qualname__ = str(
            getattr(state_machine_class, '__qualname__', base_name) +
            '.TestCase'
        )
        state_machine_class._test_case_cache[state_machine_class] = (
            StateMachineTestCase
        )
        return StateMachineTestCase

GenericStateMachine.find_breaking_runner = classmethod(find_breaking_runner)


def seeds(starting, n_steps):
    random = Random(starting)

    result = []
    for _ in hrange(n_steps):
        result.append(random.getrandbits(64))
    return result


# Sentinel value used to mark entries as deleted.
TOMBSTONE = [object(), ['TOMBSTONE FOR STATEFUL TESTING']]


class StateMachineRunner(object):

    """A StateMachineRunner is a description of how to run a state machine.

    It contains values that it will use to shape the examples.

    """

    def __init__(self, morphers):
        self.morphers = morphers

    def __trackas__(self):
        return self.morphers

    def __repr__(self):
        return 'StateMachineRunner(%d steps)' % (len(self.morphers),)

    def run(self, state_machine, print_steps=None):
        if print_steps is None:
            print_steps = current_verbosity() >= Verbosity.debug

        try:
            for morpher in self.morphers:
                value = morpher.become(state_machine.steps())
                if print_steps:
                    state_machine.print_step(value)
                state_machine.execute_step(value)
        finally:
            state_machine.teardown()


class StateMachineSearchStrategy(MappedSearchStrategy):

    def __init__(self, settings=None):
        super(StateMachineSearchStrategy, self).__init__(
            lists(
                MorpherStrategy(),
                max_size=(settings or Settings.default).stateful_step_count))

    def __repr__(self):
        return 'StateMachineSearchStrategy()'

    def pack(self, morphers):
        return StateMachineRunner(morphers)


Rule = namedtuple(
    'Rule',
    ('targets', 'function', 'arguments')

)

Bundle = namedtuple('Bundle', ('name',))


RULE_MARKER = 'hypothesis_stateful_rule'


def rule(targets=(), target=None, **kwargs):
    """Decorator for RuleBasedStateMachine. Any name present in target or
    targets will define where the end result of this function should go. If
    both are empty then the end result will be discarded.

    targets may either be a Bundle or the name of a Bundle.

    kwargs then define the arguments that will be passed to the function
    invocation. If their value is a Bundle then values that have previously
    been produced for that bundle will be provided, if they are anything else
    it will be turned into a strategy and values from that will be provided.

    """
    if target is not None:
        targets += (target,)

    converted_targets = []
    for t in targets:
        while isinstance(t, Bundle):
            t = t.name
        converted_targets.append(t)

    def accept(f):
        if not hasattr(f, RULE_MARKER):
            setattr(f, RULE_MARKER, [])
        getattr(f, RULE_MARKER).append(
            Rule(
                targets=tuple(converted_targets), arguments=kwargs, function=f
            )
        )
        return f
    return accept


VarReference = namedtuple('VarReference', ('name',))


class SimpleSampledFromStrategy(SampledFromStrategy):

    def draw_parameter(self, random):
        return None

    def draw_template(self, random, parameter_value):
        return random.randint(0, len(self.elements) - 1)


class RuleBasedStateMachine(GenericStateMachine):

    """A RuleBasedStateMachine gives you a more structured way to define state
    machines.

    The idea is that a state machine carries a bunch of types of data
    divided into Bundles, and has a set of rules which may read data
    from bundles (or just from normal strategies) and push data onto
    bundles. At any given point a random applicable rule will be
    executed.

    """
    _rules_per_class = {}
    _base_rules_per_class = {}

    def __init__(self):
        if not self.rules():
            raise InvalidDefinition('Type %s defines no rules' % (
                type(self).__name__,
            ))
        self.bundles = {}
        self.name_counter = 1
        self.names_to_values = {}

    def __repr__(self):
        return '%s(%s)' % (
            type(self).__name__,
            repr(self.bundles),
        )

    def upcoming_name(self):
        return 'v%d' % (self.name_counter,)

    def new_name(self):
        result = self.upcoming_name()
        self.name_counter += 1
        return result

    def bundle(self, name):
        return self.bundles.setdefault(name, [])

    @classmethod
    def rules(cls):
        try:
            return cls._rules_per_class[cls]
        except KeyError:
            pass

        for k, v in inspect.getmembers(cls):
            for r in getattr(v, RULE_MARKER, ()):
                cls.define_rule(
                    r.targets, r.function, r.arguments
                )
        cls._rules_per_class[cls] = cls._base_rules_per_class.pop(cls, [])
        return cls._rules_per_class[cls]

    @classmethod
    def define_rule(cls, targets, function, arguments):
        converted_arguments = {}
        for k, v in arguments.items():
            if not isinstance(v, Bundle):
                v = strategy(v)
            converted_arguments[k] = v
        if cls in cls._rules_per_class:
            target = cls._rules_per_class[cls]
        else:
            target = cls._base_rules_per_class.setdefault(cls, [])

        return target.append(
            Rule(targets, function, converted_arguments)
        )

    def steps(self):
        strategies = []
        for rule in self.rules():
            converted_arguments = {}
            valid = True
            for k, v in rule.arguments.items():
                if isinstance(v, Bundle):
                    bundle = self.bundle(v.name)
                    if not bundle:
                        valid = False
                        break
                    else:
                        v = SimpleSampledFromStrategy(bundle)
                converted_arguments[k] = v
            if valid:
                strategies.append(TupleStrategy((
                    JustStrategy(rule),
                    FixedKeysDictStrategy(converted_arguments)
                ), tuple))
        if not strategies:
            raise InvalidDefinition(
                'No progress can be made from state %r' % (self,)
            )
        return one_of_strategies(strategies)

    def print_step(self, step):
        rule, data = step
        data_repr = {}
        for k, v in data.items():
            if isinstance(v, VarReference):
                data_repr[k] = v.name
            else:
                data_repr[k] = repr(v)
        self.step_count = getattr(self, 'step_count', 0) + 1
        report('Step #%d: %s%s(%s)' % (
            self.step_count,
            '%s = ' % (self.upcoming_name(),) if rule.targets else '',
            rule.function.__name__,
            ', '.join('%s=%s' % kv for kv in data_repr.items())
        ))

    def execute_step(self, step):
        rule, data = step
        data = dict(data)
        for k, v in data.items():
            if isinstance(v, VarReference):
                data[k] = self.names_to_values[v.name]
        result = rule.function(self, **data)
        if rule.targets:
            name = self.new_name()
            self.names_to_values[name] = result
            for target in rule.targets:
                self.bundle(target).append(VarReference(name))
