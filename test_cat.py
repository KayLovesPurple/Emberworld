"""
test_cat.py -- tests for the cat as its own subsystem: the gentle guarantee,
its verbs (feed/pet/name), and its autonomous behaviors (wander/hunger/idle).

Run it either way:
    python3 -m pytest test_cat.py -v      # if you have pytest
    python3 test_cat.py                    # if you don't (built-in runner)
"""

import json

from world import World, Entity, check_world
from cat import (CAT_HUNGER_CAP, CAT_MEOW_THRESHOLD, cat_wander, cat_hunger,
                  cat_idle, cat_replay, ensure_cat_replay)
from _test_helpers import fresh, run


# ===========================================================================
# THE CAT -- must never come to harm, and behaves sensibly.
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


def test_cat_departure_and_arrival_messages_match_the_actual_direction():
    """BUG (reported from a real playtest transcript): the cat's move
    messages were hardcoded 'src always says slips out, dest always says
    pads in' regardless of which room was actually which -- so a yard->hut
    move announced 'slips out' in the yard (backwards: it was coming
    inside) and a hut->yard move announced 'pads in' in the yard (also
    backwards: it was going outside). The wording must key off the real
    direction instead."""
    from cat import _cat_go
    w, actor = fresh()
    cat = w.get("cat")

    cat.location = "hut"
    w.log = []
    _cat_go(w, cat, "out")                     # hut -> yard
    assert cat.location == "yard"
    heard_hut = next(m for (m, where) in w.log if where == "hut")
    heard_yard = next(m for (m, where) in w.log if where == "yard")
    assert heard_hut == "The cat slips out through the doorway."
    assert heard_yard == "The cat pads out into the yard, tail high."

    cat.location = "yard"
    w.log = []
    _cat_go(w, cat, "in")                      # yard -> hut
    assert cat.location == "hut"
    heard_yard2 = next(m for (m, where) in w.log if where == "yard")
    heard_hut2 = next(m for (m, where) in w.log if where == "hut")
    assert heard_yard2 == "The cat slips in through the doorway."
    assert heard_hut2 == "The cat pads in, tail high."


def test_cat_meow_is_heard_only_in_its_own_room():
    """Scoping stress test with a non-player mover: a hungry cat in the yard
    meows in the yard, never the hut."""
    class Meow:                              # force the meow to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD
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
    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD
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
    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD
    w.rng = Meow()
    w.log = []
    cat_hunger(w, cat)
    assert any("Shadow" in m for (m, _) in w.log), "meow didn't use the cat's name"


def test_content_cat_idle_line_is_heard_only_in_its_own_room():
    """Sibling scoping stress test to the meow: a content cat's idle line
    scopes to its own room, never through a wall."""
    class Roll:                              # force the idle roll to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = 0                  # content, not hungry
    cat.location = "yard"
    w.rng = Roll()
    w.log = []
    cat_idle(w, cat)
    heard_in_hut = [m for (m, where) in w.log
                    if where is None or where == "hut"]
    heard_in_yard = [m for (m, where) in w.log
                     if where is None or where == "yard"]
    assert not heard_in_hut, "heard the content cat through a wall"
    assert heard_in_yard, "content cat stayed silent where it was"


def test_hungry_cat_never_produces_an_idle_line():
    """The gate must hold: a hungry cat meows, it doesn't also mooch. Force
    the roll and confirm the idle behaviour stays silent."""
    class Roll:                              # force the idle roll to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD  # hungry
    cat.location = "yard"
    w.rng = Roll()
    w.log = []
    cat_idle(w, cat)
    assert w.log == [], f"hungry cat produced an idle line: {w.log}"


def test_named_content_cat_idle_line_uses_its_name():
    class Roll:
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["given_name"] = "Shadow"
    cat.attrs["hunger"] = 0
    w.rng = Roll()
    w.log = []
    cat_idle(w, cat)
    assert any("Shadow" in m for (m, _) in w.log), "idle line didn't use the cat's name"


def test_cat_does_not_meow_until_the_new_higher_threshold():
    """The threshold was raised (~doubled from 6) so a feeding lasts
    meaningfully longer -- pin that a cat just under it stays silent even
    when the meow roll is forced to succeed. cat_hunger increments hunger by
    1 before checking the gate, so start one tick further back than the
    boundary being tested."""
    class Meow:                              # force the meow roll to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    w.rng = Meow()

    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD - 2
    w.log = []
    cat_hunger(w, cat)                       # hunger becomes THRESHOLD - 1
    assert not any("meow" in m for (m, _) in w.log), \
        f"cat meowed below the new threshold: {w.log}"

    w.log = []
    cat_hunger(w, cat)                       # hunger becomes THRESHOLD
    assert any("meow" in m for (m, _) in w.log), \
        "cat should meow once hunger reaches the threshold"


def test_meow_threshold_description_and_idle_gate_all_agree():
    """The three things that key off hunger -- the meow, the description's
    hungry-text, and the idle behaviour's content-gate -- must all still
    switch at the same point, whatever that point is. cat_hunger increments
    hunger by 1 before using it, so start one tick further back than the
    boundary being tested."""
    class Roll:                              # force whichever roll is checked
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    w.rng = Roll()

    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD - 2
    cat_hunger(w, cat)                       # hunger becomes THRESHOLD - 1
    assert "hungry" not in cat.description.lower(), \
        "cat should still read content just under the threshold"
    w.log = []
    cat_idle(w, cat)
    assert w.log, "a not-yet-meowing cat should still be able to do idle things"

    cat_hunger(w, cat)                       # hunger becomes THRESHOLD
    assert "hungry" in cat.description.lower(), \
        "cat should read hungry right at the threshold, in step with the meow"
    w.log = []
    cat_idle(w, cat)
    assert w.log == [], "a hungry cat must not also produce idle content lines"


def test_cat_idle_is_purely_cosmetic():
    """No state change -- it only announces. Hunger, location, and every
    other attr must be untouched by a fired idle line."""
    class Roll:
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = 3
    cat.location = "yard"
    before_attrs = dict(cat.attrs)
    before_location = cat.location
    w.rng = Roll()
    cat_idle(w, cat)
    assert cat.attrs == before_attrs, "idle behaviour mutated an attr"
    assert cat.location == before_location, "idle behaviour moved the cat"


# ===========================================================================
# CAT REPLAY -- rarely, the cat bats again at a curio it's already been
# given and played with (a "plays"-reaction trace left behind by cmd_give
# in content.py), if that trace is lying in its current room.
# ===========================================================================
def _played_trace(world, room, reaction="plays"):
    return world.add(Entity(world.fresh_id("found"), "a pinecone",
                             "a pinecone, well-battered after a game with the cat",
                             location=room, portable=False,
                             attrs={"curio": True, "cat_reaction": reaction}))


class _AlwaysReplay:
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


def test_cat_replay_fires_when_a_played_trace_shares_its_room():
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    _played_trace(w, "yard")
    w.rng = _AlwaysReplay()
    w.log = []
    cat_replay(w, cat)
    assert w.log, "a played trace in the room should have triggered a replay line"


def test_cat_replay_is_silent_with_no_trace_present():
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    w.rng = _AlwaysReplay()
    w.log = []
    cat_replay(w, cat)
    assert w.log == []


def test_cat_replay_is_silent_for_an_ignored_trace():
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    _played_trace(w, "yard", reaction="ignores")
    w.rng = _AlwaysReplay()
    w.log = []
    cat_replay(w, cat)
    assert w.log == [], "an ignored curio was never played with in the first place"


def test_cat_replay_is_silent_for_a_still_portable_curio():
    """A freshly-found, not-yet-given curio is portable and hasn't been
    played with yet -- only the non-portable post-give trace should fire."""
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    w.add(Entity(w.fresh_id("found"), "a pinecone", "tight and resinous.",
                 location="yard", portable=True,
                 attrs={"curio": True, "cat_reaction": "plays"}))
    w.rng = _AlwaysReplay()
    w.log = []
    cat_replay(w, cat)
    assert w.log == []


def test_cat_replay_is_silent_while_hungry():
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD
    _played_trace(w, "yard")
    w.rng = _AlwaysReplay()
    w.log = []
    cat_replay(w, cat)
    assert w.log == []


def test_cat_replay_is_purely_cosmetic():
    w, actor = fresh()
    cat = w.get("cat")
    cat.location = "yard"
    trace = _played_trace(w, "yard")
    before_attrs = dict(cat.attrs)
    before_trace_attrs = dict(trace.attrs)
    w.rng = _AlwaysReplay()
    cat_replay(w, cat)
    assert cat.attrs == before_attrs
    assert trace.attrs == before_trace_attrs
    assert trace.location == "yard", "the trace itself must not move or vanish"


def test_ensure_cat_replay_backfills_an_old_save():
    w, actor = fresh()
    cat = w.get("cat")
    cat.behavior_names.remove("cat_replay")
    cat.behaviors = [b for b in cat.behaviors if b is not cat_replay]
    ensure_cat_replay(w)
    assert "cat_replay" in cat.behavior_names
    assert cat.behavior_names.count("cat_replay") == 1


def test_ensure_cat_replay_is_idempotent():
    w, actor = fresh()
    cat = w.get("cat")
    ensure_cat_replay(w)
    ensure_cat_replay(w)
    assert cat.behavior_names.count("cat_replay") == 1


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
