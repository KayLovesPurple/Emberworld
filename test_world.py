"""
test_world.py -- tests for the engine: Entity/World, the tick loop,
persistence, and the invariant checker.

Run it either way:
    python3 -m pytest test_world.py -v      # if you have pytest
    python3 test_world.py                    # if you don't (built-in runner)

Many of these drive real content (the lamp, potato, patch) through
world.act()/perceive(), because that's how the engine's own guarantees --
event scoping, tick ordering, darkness, invariants, persistence -- actually
get exercised. The first few pin real bugs we hit, so they can never
silently come back.
"""

import json
import os

from world import World, IncompatibleSaveError, check_world
from content import LAMP_FUEL_START
from _test_helpers import fresh, run


# ===========================================================================
# 1. SCENARIO TESTS -- engine guarantees (event scoping, tick order, timing,
#    darkness), pinned via regressions for bugs we actually hit.
# ===========================================================================
def test_regression_lamp_is_heard_while_carried():
    """BUG WE HIT (candle-era): events were scoped to an entity's immediate
    container, so a carried light source (now 'inside you') fell silent. The
    tin lamp inherits the same guarantee -- you must still hear it burn low
    and go dark while you're holding it."""
    w, actor = fresh()
    run(w, actor, "light hearth", "take lamp", "kindle lamp")
    heard_low = heard_out = False
    for _ in range(LAMP_FUEL_START):
        line = w.act(actor, "wait")
        if "shrinks" in line:
            heard_low = True
        if "goes dark" in line:
            heard_out = True
    assert heard_low, "never heard the carried lamp's flame shrink"
    assert heard_out, "never heard the carried lamp go dark"


def test_lamp_burns_out_offscreen():
    """A living world changes when you're not watching. Kindle the lamp, leave
    it behind in the hut, go to the yard: you should NOT hear it, but it should
    still be spent when you return."""
    w, actor = fresh()
    run(w, actor, "light hearth", "light lamp", "go out")
    lines = [w.act(actor, "wait") for _ in range(LAMP_FUEL_START)]
    assert not any("goes dark" in ln for ln in lines), \
        "heard the lamp from another room -- scoping is too loose"
    run(w, actor, "go in")
    assert not w.get("lamp").attrs["lit"], "lamp should have burned out"


def test_regression_patch_reflects_its_crop_in_sync():
    """BUG WE HIT: the patch described itself one tick behind the plant, so it
    said 'not far off ripe' on the very turn the crop ripened. The patch text
    and the ripened state must agree on the same turn."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato")
    patch = w.get("patch")
    # freshly planted: the patch visibly shows *something* happened
    assert "mound" in patch.description, \
        f"planting didn't change the patch: {patch.description!r}"
    # wait until ripe; on the turn it ripens, the description must match
    ripened_turn_desc = None
    for _ in range(20):
        line = w.act(actor, "wait")
        if "ripened" in line:
            ripened_turn_desc = patch.description
            break
    assert ripened_turn_desc is not None, "crop never ripened"
    assert "ready to lift" in ripened_turn_desc, \
        f"patch lagged behind the ripen event: {ripened_turn_desc!r}"


def test_regression_watered_patch_description_stays_in_sync():
    """Same class of bug as the ripening lag: watering must show up as
    'well-watered' the moment it takes effect, and read dry again the very
    next tick once the stored water is spent -- never lagging a tick behind."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato", "draw water")
    patch = w.get("patch")
    w.act(actor, "water crop")
    assert "well-watered" in patch.description, \
        f"watering didn't show up as well-watered: {patch.description!r}"
    # the water was spent that same tick -- the next tick must read dry again
    w.act(actor, "wait")
    assert "well-watered" not in patch.description, \
        f"water should be spent by now: {patch.description!r}"


def test_time_only_passes_on_real_actions():
    w, actor = fresh()
    t0 = w.time
    run(w, actor, "look", "inventory", "read journal")   # all FREE verbs
    assert w.time == t0, "looking around advanced the clock"
    run(w, actor, "wait")
    assert w.time == t0 + 1, "waiting didn't advance the clock"


def _make_it_dark(w, actor):
    """Advance to night with nothing lit, so the actor's room is dark."""
    for _ in range(40):
        if w.is_dark(actor.location):
            return
        w.act(actor, "wait")
    raise AssertionError("couldn't make the room dark")


def test_regression_cannot_inspect_room_things_in_the_dark():
    """BUG WE HIT: room-level look respected darkness, but 'look <thing>' and
    'read' didn't -- you could examine the knife and read the journal in pitch
    black the world had just said you couldn't see through. Targeted look/read
    must respect darkness too."""
    w, actor = fresh()
    _make_it_dark(w, actor)
    assert "dark" in w.act(actor, "look knife").lower(), \
        "examined a room object in the dark"
    assert "dark" in w.act(actor, "read journal").lower(), \
        "read the journal in the dark"


def test_can_inspect_carried_things_in_the_dark():
    """The sensible exception: you can always examine what's in your own hands,
    and read it by feel. This is also a learnable strategy -- pick it up."""
    w, actor = fresh()
    run(w, actor, "take journal", "take knife")
    _make_it_dark(w, actor)
    assert "iron knife" in w.act(actor, "look knife"), \
        "couldn't examine a carried item in the dark"
    assert "journal reads" in w.act(actor, "read journal"), \
        "couldn't read a carried item in the dark"


def test_look_shows_what_youre_carrying():
    """BUG WE HIT: an agent with no memory between turns back-calculated its
    inventory from memory it doesn't have, and got it badly wrong. Carried
    items must be part of the standing room view, not hidden behind a
    separate 'inventory' command the agent has to choose to run."""
    w, actor = fresh()
    run(w, actor, "take lamp")
    assert "lamp" in w.perceive(actor), "carried lamp missing from perception"


def test_look_says_hands_are_empty_when_carrying_nothing():
    w, actor = fresh()
    assert "hands are empty" in w.perceive(actor).lower()


def test_carried_items_stay_visible_in_the_dark_but_the_room_does_not():
    """Mirrors the existing rule: darkness hides the room, not what's in your
    own hands. The standing perception must keep showing carried items even
    when the room itself goes dark."""
    w, actor = fresh()
    run(w, actor, "take knife")
    _make_it_dark(w, actor)
    seen = w.perceive(actor)
    assert "pitch dark" in seen.lower(), "the room should still be hidden"
    assert "knife" in seen, "carried knife should stay visible in the dark"


def test_empty_handed_in_the_dark_says_so():
    w, actor = fresh()
    _make_it_dark(w, actor)
    seen = w.perceive(actor)
    assert "pitch dark" in seen.lower()
    assert "hands are empty" in seen.lower()


# ===========================================================================
# 2. INVARIANTS -- must hold no matter what features exist.
# ===========================================================================
def test_fresh_world_is_well_formed():
    w, _ = fresh()
    assert check_world(w) == []


def test_invariants_survive_a_scripted_session():
    w, actor = fresh()
    script = ["go out", "take potato", "plant potato", "go in",
              "light hearth", "take lamp", "light lamp", "snuff lamp",
              "wait", "wait", "go out",
              "wait", "wait", "wait", "wait", "wait", "wait", "wait",
              "harvest", "go in", "cook potato"]
    for cmd in script:
        w.act(actor, cmd)
        assert check_world(w) == [], f"invariant broke after '{cmd}'"


def test_checker_actually_catches_corruption():
    """A checker that never fires is worthless. Prove it screams when we break
    the world on purpose."""
    w, _ = fresh()
    w.get("lamp").location = "nowhere-real"
    issues = check_world(w)
    assert any("doesn't exist" in i for i in issues)

    w2, _ = fresh()
    w2.get("lamp").attrs["fuel"] = -5
    assert any("negative" in i for i in check_world(w2))

    w3, _ = fresh()
    del w3.entities["you"]
    assert any("actor" in i for i in check_world(w3))


# ===========================================================================
# 3. PERSISTENCE -- save/load round-trips exactly; bad saves are refused.
# ===========================================================================
def test_save_load_roundtrip_is_identical():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato", "wait", "wait")
    data1 = w.to_data()
    w2 = World.from_data(json.loads(json.dumps(data1)))   # through real JSON
    data2 = w2.to_data()
    assert data1 == data2, "world changed shape across a save/load round-trip"


def test_save_writes_unicode_readably_not_escaped():
    """Regression: json.dump's default ensure_ascii=True turned an em dash in
    a journal note into a literal '\\u2014' in the on-disk save file. It still
    round-tripped fine through load(), but the raw file was unreadable -- fix
    it so real text stays real text on disk."""
    import tempfile
    w, actor = fresh()
    journal = w.get("journal")
    journal.attrs.setdefault("entries", []).append("a note with an em dash — right here")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        path = tmp.name
    try:
        w.save(path)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        assert "—" in raw, "the actual character should be on disk"
        assert "\\u2014" not in raw, f"em dash was escaped instead of written plainly: {raw!r}"
    finally:
        os.remove(path)


def test_incompatible_version_is_refused():
    w, _ = fresh()
    data = w.to_data()
    data["version"] = 1                       # pretend it's an old save
    try:
        World.from_data(data)
        assert False, "loaded an incompatible save instead of refusing it"
    except IncompatibleSaveError:
        pass


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
