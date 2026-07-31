"""
test_content.py -- tests for Emberworld's own content: the gameplay loop,
verbs, behaviors, the cat, and the self-documenting reference.

Run it either way:
    python3 -m pytest test_content.py -v      # if you have pytest
    python3 test_content.py                    # if you don't (built-in runner)
"""

import json

from world import World, check_world
from content import (
    VERBS, BEHAVIORS, CAT_HUNGER_CAP, cat_wander, cat_hunger,
    generate_reference, _crop_in,
)
from _test_helpers import fresh, run


# ===========================================================================
# 1. GAMEPLAY -- the point-of-the-game loop, end to end.
# ===========================================================================
def test_full_grow_cook_eat_loop():
    """The whole point-of-the-game loop, end to end."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato")
    for _ in range(20):
        if "harvest" in w.available_actions(actor):
            break
        w.act(actor, "wait")
    run(w, actor, "harvest")
    assert any("potato" in e.name for e in w.contents(actor.id)), "no potato harvested"
    run(w, actor, "go in", "light hearth", "cook potato")
    cooked = [e for e in w.contents(actor.id) if e.attrs.get("food", 0) > 0]
    assert cooked, "cooking produced no food"
    before = actor.attrs["hunger"]
    run(w, actor, f"eat {cooked[0].name}")
    assert actor.attrs["hunger"] < before, "eating didn't reduce hunger"


def test_cannot_plant_without_a_seed():
    w, actor = fresh()
    run(w, actor, "go out")   # no potato in hand
    line = w.act(actor, "plant potato")
    assert "need a raw potato" in line
    assert _crop_in(w, "yard") is None, "planted something out of nothing"


# ===========================================================================
# 2. THE CAT -- must never come to harm, and behaves sensibly.
# ===========================================================================
def test_cat_is_never_harmed_however_long_it_goes_unfed():
    """The gentle guarantee, enforced: no matter how long nobody feeds it, the
    cat's hunger stays capped and it simply stays present. No harm state exists."""
    w, actor = fresh()
    cat = w.get("cat")
    for _ in range(300):
        w.act(actor, "wait")
        assert 0 <= cat.attrs["hunger"] <= CAT_HUNGER_CAP, "cat hunger left safe bounds"
        assert w.get("cat") is not None, "the cat vanished -- that must never happen"
    assert check_world(w) == []


def test_feeding_requires_the_cat_present_and_resets_hunger():
    class Stay:                              # rng that never moves the cat
        def random(self): return 1.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    w.rng = Stay()
    cat = w.get("cat")
    run(w, actor, "go out", "take potato", "go in")   # fetch a potato; cat stays
    cat.location = "hut"
    cat.attrs["hunger"] = 10
    result = w.act(actor, "feed cat")
    assert "purrs" in result, f"feeding didn't land: {result!r}"
    assert cat.attrs["hunger"] < 5, "feeding didn't satisfy the cat"   # 0, +1 for the tick

    cat.location = "yard"                     # cat elsewhere, you in hut
    cat.attrs["hunger"] = 10
    run(w, actor, "go out", "take potato", "go in")
    assert "no cat here" in w.act(actor, "feed cat").lower()


def test_petting_needs_the_cat_and_costs_nothing_useful():
    w, actor = fresh()
    w.get("cat").location = "hut"
    assert "purrs" in w.act(actor, "pet cat")


def test_cat_is_drawn_to_a_lit_hearth():
    """Lighting the fire should pull the cat toward you -- learnable, gentle
    agency. Tested deterministically with a controlled roll."""
    class Roll:                              # always 'move, first option'
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    w.rng = Roll()
    cat = w.get("cat")
    cat.location = "yard"                     # cat away from the (unlit) hut
    w.get("hearth").attrs["lit"] = True       # now the hut is warm
    cat_wander(w, cat)
    assert cat.location == "hut", "cat ignored the warm room next door"


def test_cat_meow_is_heard_only_in_its_own_room():
    """Scoping stress test with a non-player mover: a hungry cat in the yard
    meows in the yard, never the hut."""
    class Meow:                              # force the meow to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = 10
    cat.location = "yard"
    w.rng = Meow()
    w.log = []
    cat_hunger(w, cat)                     # cat meows in the yard
    heard_in_hut = [m for (m, where) in w.log
                    if where is None or where == "hut"]
    heard_in_yard = [m for (m, where) in w.log
                     if where is None or where == "yard"]
    assert not any("meow" in m for m in heard_in_hut), "heard the cat through a wall"
    assert any("meow" in m for m in heard_in_yard), "cat didn't meow where it was"


def test_hungry_cat_description_says_so():
    """Hunger used to only show up as a fleeting meow announcement, so agents
    missed it. The cat's own description (visible in the room every turn) must
    say it's hungry once hunger reaches the threshold, and stop once it isn't."""
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "hut"
    cat.attrs["hunger"] = 6
    cat_hunger(w, cat)
    assert "hungry" in cat.description.lower(), \
        f"hungry cat's description doesn't say so: {cat.description!r}"

    cat.attrs["hunger"] = 0
    cat_hunger(w, cat)
    assert "hungry" not in cat.description.lower(), \
        f"well-fed cat's description still claims hunger: {cat.description!r}"


def test_naming_the_cat_sticks_and_persists():
    w, actor = fresh()
    w.get("cat").location = "hut"
    assert "Shadow" in w.act(actor, "name cat Shadow")
    cat = w.get("cat")
    assert cat.attrs["given_name"] == "Shadow"
    assert cat.name == "Shadow"
    # the name survives a save/load round-trip -- Shadow is Shadow for everyone
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.get("cat").attrs["given_name"] == "Shadow"


def test_naming_needs_the_cat_present():
    w, actor = fresh()
    w.get("cat").location = "yard"           # you in hut, cat away
    assert "no cat here" in w.act(actor, "name cat Shadow").lower()


def test_named_cat_uses_its_name_in_announcements():
    class Meow:
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["given_name"] = "Shadow"
    cat.attrs["hunger"] = 10
    w.rng = Meow()
    w.log = []
    cat_hunger(w, cat)
    assert any("Shadow" in m for (m, _) in w.log), "meow didn't use the cat's name"


# ===========================================================================
# 3. DOCUMENTATION -- the reference generates from code, and nothing new can
#    slip in undocumented. If these fail, you added a verb/behavior without a
#    docstring: write one, and the reference picks it up for free.
# ===========================================================================
def test_every_verb_is_documented():
    undocumented = sorted({fn.__name__ for fn in VERBS.values() if not fn.__doc__})
    assert not undocumented, f"verbs missing a docstring: {undocumented}"


def test_every_behavior_is_documented():
    undocumented = sorted(n for n, fn in BEHAVIORS.items() if not fn.__doc__)
    assert not undocumented, f"behaviors missing a docstring: {undocumented}"


def test_reference_generates_and_mentions_key_things():
    ref = generate_reference()
    assert "## Verbs" in ref and "## Autonomous behaviors" in ref
    # a few anchors so a totally broken generator is caught
    for anchor in ("plant potato", "feed cat", "burning", "cat_wander"):
        assert anchor in ref, f"reference missing '{anchor}'"
    assert str(CAT_HUNGER_CAP) in ref, "numeric rules didn't render"


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
