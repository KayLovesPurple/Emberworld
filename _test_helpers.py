"""
_test_helpers.py -- tiny helpers shared by the test_*.py files. Not a test
module itself (no test_ functions), and the leading underscore keeps pytest
from trying to collect it as one.
"""

from content import build_world


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
