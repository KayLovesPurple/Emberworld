"""
_test_helpers.py -- tiny helpers shared by the test_*.py files. Not a test
module itself (no test_ functions), and the leading underscore keeps pytest
from trying to collect it as one.

Only helpers actually used across more than one test_*.py file live here --
a helper used by tests in just one file stays defined in that file, right
next to the tests that use it. _add_curio/_curio_tuple and _Lucky/_Unlucky
moved here when test_content.py was split (see docs/ARCHITECTURE.md) because
each is used by tests that now live in different files.
"""

from world import Entity
from content import build_world
from curios import FOUND_ITEMS, _found_description


def fresh():
    """A brand-new world plus its actor."""
    return build_world()


def run(world, actor, *commands):
    """Apply a sequence of commands, returning the last result string."""
    out = ""
    for c in commands:
        out = world.act(actor, c)
    return out


def wait(world, actor, n):
    for _ in range(n):
        world.act(actor, "wait")


def _curio_tuple(name):
    return next(t for t in FOUND_ITEMS if t[0] == name)


def _add_curio(world, actor, name, location=None):
    n, look_line, reaction = _curio_tuple(name)
    return world.add(Entity(world.fresh_id("found"), n,
                             _found_description(look_line, reaction),
                             location=location or actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": reaction}))


class _Lucky:                                # force the find roll to fire
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


class _Unlucky:                              # never let the find roll fire
    def random(self): return 1.0
    def choice(self, seq): return seq[0]
