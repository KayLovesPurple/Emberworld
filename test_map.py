"""
test_map.py -- tests for map.py's outer-world ASCII layout and the `map`
verb (cmd_map in content.py) that surfaces it.

Run it either way:
    python3 -m pytest test_map.py -v   # if you have pytest
    python3 test_map.py                 # if you don't (built-in runner)
"""

from map import ROOM_LABELS, render_map
from _test_helpers import fresh, run


def test_render_map_contains_every_known_room_label():
    text = render_map()
    for label in ROOM_LABELS.values():
        assert label in text


def test_render_map_has_no_position_marker():
    """Deliberately no "you are here" -- this reads as a hand-drawn map the
    hero carries, not a live GPS overlay, and `look`'s own room header
    already says where you are every turn without this. See map.py's own
    module docstring for the fuller reasoning."""
    text = render_map()
    assert "(you)" not in text.lower()
    assert "you are" not in text.lower()


def test_render_map_is_deterministic():
    """No actor, no randomness -- calling it twice must return the exact
    same string."""
    assert render_map() == render_map()


def test_render_map_mentions_the_forest_but_not_as_a_room():
    """The forest gets a hazy, labeled shape past Forest's Edge -- it says
    the forest is there, same as the room's own description already does,
    without claiming to know its shape. It must never be mistaken for one
    of the four real, mapped rooms."""
    text = render_map()
    assert "the forest" in text.lower()
    assert "the forest" not in {label.lower() for label in ROOM_LABELS.values()}


def test_map_completeness_against_the_live_room_graph():
    """Every room the world actually has (any entity with a non-empty
    `exits` dict -- the same trait `look`'s "Exits:" line relies on) must
    have a label in ROOM_LABELS. A room added later without updating
    map.py should fail here, loudly, rather than silently going missing
    from the picture -- the same role REFERENCE.md's docstring-coverage
    test plays for verbs and behaviors."""
    w, actor = fresh()
    room_ids = {e.id for e in w.entities.values() if e.exits}
    assert room_ids == set(ROOM_LABELS)


def test_map_verb_returns_the_same_thing_regardless_of_where_the_actor_is():
    w, actor = fresh()
    from_hut = w.act(actor, "map")
    run(w, actor, "go out")
    from_yard = w.act(actor, "map")
    assert from_hut == from_yard == render_map()


def test_map_is_a_free_verb_and_does_not_advance_the_clock():
    w, actor = fresh()
    before = w.time
    w.act(actor, "map")
    assert w.time == before


# ---------------------------------------------------------------------------
# Built-in runner, so you don't need pytest installed.
# ---------------------------------------------------------------------------
def _main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
