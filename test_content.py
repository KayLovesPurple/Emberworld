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
    VERBS, BEHAVIORS, CAT_HUNGER_CAP, cat_wander, cat_hunger, cat_idle,
    generate_reference, _crop_in, BUCKET_CAPACITY, bucket_state,
    WOOD_PER_GATHER, HEARTH_FUEL_START, FUEL_PER_WOOD, HEARTH_LOW_FUEL,
    hearth_state,
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
# 2. THE WELL, THE BUCKET, AND WATERING -- a pure accelerator: crops still
#    grow unwatered, just slower. Nothing can fail or be harmed by this.
# ===========================================================================
def test_draw_water_fills_the_bucket_and_caps_at_capacity():
    w, actor = fresh()
    run(w, actor, "go out")
    result = w.act(actor, "draw water")
    bucket = w.get("bucket")
    assert bucket.attrs["water"] == BUCKET_CAPACITY, f"bucket not filled: {bucket.attrs}"
    assert str(BUCKET_CAPACITY) in result

    again = w.act(actor, "draw water")
    assert "already full" in again.lower()
    assert bucket.attrs["water"] == BUCKET_CAPACITY, "drawing again overfilled the bucket"


def test_watering_requires_a_plant_and_water_in_the_bucket():
    w, actor = fresh()
    run(w, actor, "go out")
    # no plant yet
    result = w.act(actor, "water crop")
    assert "nothing planted" in result.lower()

    run(w, actor, "take potato", "plant potato")
    # bucket still empty
    result = w.act(actor, "water crop")
    assert "empty" in result.lower()

    w.act(actor, "draw water")
    result = w.act(actor, "water crop")
    assert "pour" in result.lower()
    assert w.get("bucket").attrs["water"] == BUCKET_CAPACITY - 1


def test_watered_plant_ripens_faster_than_unwatered():
    """The core mechanic: a crop watered whenever possible ripens in fewer
    ticks than one left dry -- without ever failing or needing exact timing."""
    def ticks_to_ripen(water_it):
        w, actor = fresh()
        run(w, actor, "go out", "take potato", "plant potato")
        if water_it:
            w.act(actor, "draw water")
        ticks = 0
        while not _crop_in(w, "yard").attrs.get("ready"):
            if water_it and w.get("bucket").attrs.get("water", 0) > 0:
                w.act(actor, "water crop")
            else:
                w.act(actor, "wait")
            ticks += 1
            assert ticks < 30, "never ripened"
        return ticks

    unwatered = ticks_to_ripen(False)
    watered = ticks_to_ripen(True)
    assert watered < unwatered, \
        f"watered ({watered} ticks) should ripen faster than unwatered ({unwatered})"


def test_watered_water_is_consumed_by_growing():
    """One unit of stored water buys exactly one fast tick; once it's spent,
    growth returns to the normal +1 pace."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato", "draw water")
    plant = _crop_in(w, "yard")
    g0 = plant.attrs["growth"]
    w.act(actor, "water crop")
    assert plant.attrs.get("watered", 0) == 0, \
        "the stored water should be spent the same tick it's used"
    g1 = plant.attrs["growth"]
    assert g1 - g0 == 2, f"a watered tick should give +2 growth, got +{g1 - g0}"
    w.act(actor, "wait")
    g2 = plant.attrs["growth"]
    assert g2 - g1 == 1, f"growth should return to +1 once water is spent, got +{g2 - g1}"


def test_bucket_description_always_shows_its_water_count():
    w, actor = fresh()
    run(w, actor, "go out")
    bucket = w.get("bucket")
    assert "empty" in bucket.description.lower()
    w.act(actor, "draw water")
    assert str(BUCKET_CAPACITY) in bucket.description, \
        f"full bucket description doesn't show its count: {bucket.description!r}"
    bucket.attrs["water"] = 3
    bucket_state(w, bucket)
    assert "3" in bucket.description


def test_water_and_bucket_state_survive_save_load_roundtrip():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato", "draw water", "water crop")
    bucket = w.get("bucket")
    plant = _crop_in(w, "yard")
    bucket_water = bucket.attrs["water"]
    plant_watered = plant.attrs.get("watered", 0)
    plant_growth = plant.attrs["growth"]

    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    bucket2 = w2.get("bucket")
    plant2 = _crop_in(w2, "yard")
    assert bucket2.attrs["water"] == bucket_water
    assert plant2.attrs.get("watered", 0) == plant_watered
    assert plant2.attrs["growth"] == plant_growth


# ===========================================================================
# 3. FIREWOOD -- forage wood in the yard, feed the hearth, revive a dead fire.
#    BUG WE HIT: fire was a countdown with no reset, so a long lineage always
#    inherited a cold hearth with no recourse. Wood fixes that.
# ===========================================================================
def test_gather_wood_in_the_yard_increases_carried_wood():
    w, actor = fresh()
    run(w, actor, "go out")
    result = w.act(actor, "gather wood")
    assert actor.attrs["wood"] == WOOD_PER_GATHER, \
        f"gather didn't add {WOOD_PER_GATHER} wood: {actor.attrs}"
    assert str(WOOD_PER_GATHER) in result, f"result didn't name the new amount: {result!r}"


def test_gather_wood_is_gated_to_the_yard():
    w, actor = fresh()
    result = w.act(actor, "gather wood")           # still in the hut
    assert actor.attrs.get("wood", 0) == 0, "gathered wood outside the yard"
    assert "yard" in result.lower()


def test_add_wood_requires_wood_and_the_hearth_present():
    w, actor = fresh()
    # in the hut (hearth present) but no wood carried
    result = w.act(actor, "add wood")
    assert "no wood" in result.lower(), f"unclear refusal: {result!r}"
    assert w.get("hearth").attrs["fuel"] == HEARTH_FUEL_START, "fuel changed on a refusal"

    # wood carried, but the wrong room (no hearth in the yard)
    run(w, actor, "go out")
    actor.attrs["wood"] = 1
    result = w.act(actor, "add wood")
    assert "no hearth" in result.lower(), f"unclear refusal: {result!r}"
    assert actor.attrs["wood"] == 1, "wood was spent on a refusal"


def test_add_wood_moves_wood_from_actor_to_hearth():
    w, actor = fresh()
    actor.attrs["wood"] = 2
    hearth = w.get("hearth")
    fuel0 = hearth.attrs["fuel"]
    w.act(actor, "add wood")
    assert actor.attrs["wood"] == 1, "wood wasn't taken from the actor"
    assert hearth.attrs["fuel"] == fuel0 + FUEL_PER_WOOD, \
        "hearth fuel didn't rise by one wood's worth"


def test_add_wood_revives_a_spent_hearth():
    """The core fix, pinned: a spent hearth (fuel 0, unlit) can be fed and
    lit again -- a lineage is no longer stuck with a cold hearth forever."""
    w, actor = fresh()
    hearth = w.get("hearth")
    hearth.attrs["fuel"] = 0
    hearth.attrs["lit"] = False
    actor.attrs["wood"] = 1
    w.act(actor, "add wood")
    assert hearth.attrs["fuel"] > 0, "adding wood didn't restore fuel"
    assert not hearth.attrs["lit"], "add wood must not auto-light the hearth"

    result = w.act(actor, "light hearth")
    assert hearth.attrs["lit"], f"a refuelled hearth should be lightable again: {result!r}"


def test_add_wood_to_a_lit_hearth_extends_its_fuel():
    w, actor = fresh()
    hearth = w.get("hearth")
    hearth.attrs["lit"] = True
    hearth.attrs["fuel"] = 5
    actor.attrs["wood"] = 1
    w.act(actor, "add wood")
    assert hearth.attrs["fuel"] > 5, "adding wood to a lit hearth should extend it"
    assert hearth.attrs["lit"], "adding wood shouldn't snuff a lit hearth"


def test_carried_wood_shows_in_the_standing_perception():
    w, actor = fresh()
    run(w, actor, "go out", "gather wood")
    seen = w.perceive(actor)
    assert f"firewood ({WOOD_PER_GATHER})" in seen, \
        f"carried wood missing from the standing perception: {seen!r}"


def test_low_fuel_hearth_reads_as_needing_wood_a_well_fed_one_reads_steady():
    """A hand must be able to see a dying fire coming, not just be told after
    the fact that it went out."""
    w, actor = fresh()
    hearth = w.get("hearth")
    hearth.attrs["lit"] = True
    hearth.attrs["fuel"] = HEARTH_LOW_FUEL
    hearth_state(w, hearth)
    low_desc = hearth.description.lower()
    assert "wood" in low_desc or "low" in low_desc or "dying" in low_desc, \
        f"low-fuel hearth doesn't read as needing wood: {hearth.description!r}"

    hearth.attrs["fuel"] = HEARTH_FUEL_START
    hearth_state(w, hearth)
    steady_desc = hearth.description.lower()
    assert "dying" not in steady_desc and "wants more wood" not in steady_desc, \
        f"well-fed hearth still reads as needing wood: {hearth.description!r}"


def test_hearth_description_moves_healthy_low_spent_across_a_real_burn():
    """The full arc, driven by real ticking (not direct calls): a freshly-lit
    hearth reads healthy, sinks to low as fuel runs down, and still reads as
    ash once spent -- display only, doesn't touch burn timing."""
    w, actor = fresh()
    hearth = w.get("hearth")
    w.act(actor, "light hearth")
    healthy = hearth.description.lower()
    assert "dying" not in healthy and "ash" not in healthy, \
        f"freshly-lit hearth doesn't read healthy: {hearth.description!r}"

    while hearth.attrs["fuel"] > HEARTH_LOW_FUEL:
        w.act(actor, "wait")
    low = hearth.description.lower()
    assert "dying" in low or "wants more wood" in low, \
        f"low-fuel hearth doesn't read as needing wood: {hearth.description!r}"

    while hearth.attrs["lit"]:
        w.act(actor, "wait")
    spent = hearth.description.lower()
    assert "ash" in spent, f"spent hearth should still read as ash: {hearth.description!r}"


def test_gather_and_add_wood_are_surfaced_in_available_actions():
    """The wood loop only helps if it's discoverable: an agent reads the
    action list, not the room prose, so the verbs must appear there when
    legal."""
    w, actor = fresh()
    run(w, actor, "go out")
    assert "gather wood" in w.available_actions(actor), \
        "gather wood should be offered in the yard"

    run(w, actor, "gather wood", "go in")
    assert "add wood" in w.available_actions(actor), \
        "add wood should be offered when carrying wood near the hearth"


def test_yard_description_does_not_mention_wood():
    """Deliberate choice: discovery comes from the action list alone, not
    from hinting at wood in the room prose. Pin it so a future edit can't
    silently add it without us deciding to."""
    w, actor = fresh()
    run(w, actor, "go out")
    desc = w.get("yard").description.lower()
    assert "wood" not in desc and "branch" not in desc, \
        f"yard description hints at wood, undermining the action-list test: {desc!r}"


def test_wood_and_hearth_fuel_survive_save_load_roundtrip():
    w, actor = fresh()
    run(w, actor, "go out", "gather wood")
    hearth = w.get("hearth")
    hearth.attrs["fuel"] = 15                    # mid-burn, partially fuelled
    actor.attrs["wood"] = 2                        # leftover after gathering

    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.get("you").attrs.get("wood", 0) == 2
    assert w2.get("hearth").attrs["fuel"] == 15


# ===========================================================================
# 4. THE CAT -- must never come to harm, and behaves sensibly.
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
    cat.attrs["hunger"] = 10                 # hungry
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
# 5. DOCUMENTATION -- the reference generates from code, and nothing new can
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
