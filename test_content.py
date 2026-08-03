"""
test_content.py -- tests for Emberworld's own content: the gameplay loop,
verbs, behaviors, and the self-documenting reference. The cat has its own
subsystem and its own test file -- see cat.py / test_cat.py.

Run it either way:
    python3 -m pytest test_content.py -v      # if you have pytest
    python3 test_content.py                    # if you don't (built-in runner)
"""

import json

from world import World, Entity
from content import (
    VERBS, BEHAVIORS, generate_reference, _crop_in, BUCKET_CAPACITY,
    bucket_state, WOOD_PER_GATHER, HEARTH_FUEL_START, FUEL_PER_WOOD,
    HEARTH_LOW_FUEL, hearth_state, FOUND_ITEMS,
    LAMP_FUEL_START, LAMP_LOW_FUEL,
    PATCH_VOLUNTEER_TURNS,
)
from cat import CAT_HUNGER_CAP
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
# 1b. RESOLVING THE RIGHT POTATO -- 'potato' is a substring of 'broiled
#     potato' too, so carrying both used to hand every verb the wrong one.
#     BUG WE HIT: a hand carrying both tried to plant fourteen turns running
#     and kept failing, because the substring match grabbed the broiled
#     potato first every time -- while a plantable raw one sat right there.
# ===========================================================================
def _cook_one_potato(w, actor):
    """Helper: get exactly one broiled potato into the actor's hands."""
    run(w, actor, "go out", "take potato", "go in", "light hearth", "cook potato")
    return next(e for e in w.contents(actor.id) if e.name == "broiled potato")


def test_planting_finds_the_raw_potato_even_when_a_cooked_one_is_carried_too():
    """The regression test for the fourteen-turn failure."""
    w, actor = fresh()
    broiled = _cook_one_potato(w, actor)
    raw = w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                        location=actor.id, portable=True))
    run(w, actor, "go out")
    result = w.act(actor, "plant potato")
    assert "press the potato" in result.lower(), \
        f"planting failed with both kinds carried: {result!r}"
    assert w.get(raw.id) is None, "the raw potato wasn't consumed by planting"
    assert w.get(broiled.id) is not None and w.get(broiled.id).location == actor.id, \
        "the broiled potato should be untouched, still in hand"


def test_cooking_targets_the_raw_potato_not_an_already_cooked_one():
    w, actor = fresh()
    broiled = _cook_one_potato(w, actor)
    raw = w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                        location=actor.id, portable=True))
    result = w.act(actor, "cook potato")
    assert "bury the potato" in result.lower(), \
        f"cooking failed with both kinds carried: {result!r}"
    recooked = w.get(raw.id)
    assert recooked is not None and recooked.name == "broiled potato", \
        "cook should have targeted the raw potato, not the already-cooked one"
    assert w.get(broiled.id).name == "broiled potato", \
        "the already-cooked potato shouldn't be disturbed"


def test_eating_targets_the_cooked_potato_not_the_raw_one():
    w, actor = fresh()
    broiled = _cook_one_potato(w, actor)
    raw = w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                        location=actor.id, portable=True))
    before = actor.attrs["hunger"]
    result = w.act(actor, "eat potato")
    assert "settles you" in result.lower(), \
        f"eating failed with both kinds carried: {result!r}"
    assert w.get(broiled.id) is None, "eating should have consumed the broiled potato"
    assert w.get(raw.id) is not None and w.get(raw.id).location == actor.id, \
        "the raw potato should be untouched by eating"
    assert actor.attrs["hunger"] < before, "eating didn't reduce hunger"


def test_feeding_cat_prefers_the_raw_potato_reserving_cooked_food_for_the_player():
    w, actor = fresh()
    broiled = _cook_one_potato(w, actor)
    raw = w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                        location=actor.id, portable=True))
    w.get("cat").location = actor.location
    result = w.act(actor, "feed cat")
    assert "purrs" in result, f"feeding didn't land: {result!r}"
    assert w.get(raw.id) is None, "feeding should have consumed the raw potato"
    assert w.get(broiled.id) is not None and w.get(broiled.id).location == actor.id, \
        "the broiled potato should be reserved for the player, not fed to the cat"


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


def test_carried_duplicate_items_are_grouped_with_a_count():
    """Two potatoes shouldn't read as 'potato, potato' -- group identical
    carried items into one line with a count, the way wood already does."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato")
    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                 location=actor.id, portable=True))
    seen = w.perceive(actor)
    assert "potato (2)" in seen, f"duplicate potatoes weren't grouped: {seen!r}"
    assert "potato, potato" not in seen, f"duplicates still listed separately: {seen!r}"


def test_carried_single_item_has_no_count_suffix():
    w, actor = fresh()
    run(w, actor, "take knife")
    seen = w.perceive(actor)
    assert "knife" in seen and "knife (1)" not in seen


def test_gather_wood_can_turn_up_a_found_item():
    """The curiosity nudge in the system prompt needs something to pay off:
    a lucky gather sometimes turns up a small found object alongside the
    wood -- purely cosmetic, freely carried, named in the result."""
    class Lucky:                             # force the find roll to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    run(w, actor, "go out")
    w.rng = Lucky()
    result = w.act(actor, "gather wood")
    found = [e for e in w.contents(actor.id) if e.location == actor.id]
    assert len(found) == 1, f"a lucky gather should add exactly one found item: {found}"
    name, desc = FOUND_ITEMS[0]
    assert found[0].name == name and found[0].description == desc
    assert found[0].portable, "a found item must be carryable"
    assert found[0].attrs.get("curio"), "a found item should be marked as a curio"
    assert name in result, f"result didn't name the find: {result!r}"


def test_gather_wood_found_item_is_rare_not_guaranteed():
    class Unlucky:                           # never let the find roll succeed
        def random(self): return 0.99
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    run(w, actor, "go out")
    w.rng = Unlucky()
    w.act(actor, "gather wood")
    assert w.contents(actor.id) == [], "an unlucky gather shouldn't add a found item"
    assert actor.attrs["wood"] == WOOD_PER_GATHER, "wood itself must still be gathered"


def test_shelf_displays_a_found_item_and_lets_a_later_hand_retrieve_it():
    """The shelf is persistent, legible storage rather than a decorative prop."""
    w, actor = fresh()
    assert "curio shelf" in w.get("shelf").description, \
        "the shelf should make its purpose legible to a visiting agent"
    stone_name, stone_description = FOUND_ITEMS[0]
    stone = w.add(Entity(w.fresh_id("found"), stone_name, stone_description,
                         location=actor.id, portable=True))

    actions = w.available_actions(actor)
    assert f"place {stone_name} on shelf" in actions, "shelf action wasn't offered"
    result = w.act(actor, f"place {stone_name} on shelf")
    shelf = w.get("shelf")
    assert stone.location == shelf.id and "set the" in result.lower()
    assert stone_name in w.perceive(actor), "displayed item isn't visible in the hut"
    assert f"take {stone_name}" in w.available_actions(actor), "retrieval wasn't offered"

    result = w.act(actor, f"take {stone_name}")
    assert stone.location == actor.id and "you take" in result.lower()


def test_taking_a_found_curio_does_not_double_the_article():
    """FOUND_ITEMS bakes its own article into the name (so the discovery and
    carried-item lines read naturally), but a verb response that prepends its
    own 'the' must strip it first, or it reads 'the a smooth grey stone'."""
    w, actor = fresh()
    name, desc = FOUND_ITEMS[0]           # "a smooth grey stone"
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location="yard", portable=True, attrs={"curio": True}))
    run(w, actor, "go out")
    result = w.act(actor, f"take {name}").splitlines()[0]
    assert result == "You take the smooth grey stone.", f"double article: {result!r}"


def test_dropping_a_found_curio_does_not_double_the_article():
    w, actor = fresh()
    name, desc = FOUND_ITEMS[0]
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    result = w.act(actor, f"drop {name}").splitlines()[0]
    assert result == "You set down the smooth grey stone.", f"double article: {result!r}"


def test_placing_a_found_curio_on_the_shelf_does_not_double_the_article():
    w, actor = fresh()
    name, desc = FOUND_ITEMS[0]
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    result = w.act(actor, f"place {name} on shelf").splitlines()[0]
    assert result == "You set the smooth grey stone on the shelf.", f"double article: {result!r}"


def test_actions_lists_the_current_options_without_passing_time():
    w, actor = fresh()
    w.get("knife").location = actor.id
    before = w.time
    result = w.act(actor, "actions")
    assert w.time == before, "asking for actions should be free"
    assert "Available actions:" in result and "go out" in result
    assert "place knife on shelf" in result, "contextual shelf action was omitted"


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
# 4. THE TIN LAMP -- a re-kindleable portable light, replacing the one-shot
#    candle entirely. Legibility over mechanics: the lamp's state is worn on
#    its sleeve everywhere it's shown, and there is now only ONE portable-
#    light object -- the potato-disambiguation lesson, applied by removal.
#    Paired with morning arrival: a fresh world starts in daylight, giving a
#    first hand a safe window to find the lamp before night falls.
# ===========================================================================
def test_fresh_world_has_an_unlit_lamp_and_no_candle():
    w, actor = fresh()
    lamp = w.get("lamp")
    assert lamp is not None and lamp.location == "hut", "lamp missing from the hut"
    assert not lamp.attrs.get("lit"), "fresh lamp should start unlit"
    desc = lamp.description.lower()
    assert "kindle" in desc and "hearth" in desc, \
        f"lamp's description doesn't advertise its verb/prerequisite: {lamp.description!r}"
    assert w.get("candle") is None, "the retired candle is still in the world"
    assert not any("candle" in e.name.lower() for e in w.entities.values()), \
        "something still mentions the candle by name"


def test_kindling_the_lamp_at_a_lit_hearth_lights_it_full():
    w, actor = fresh()
    run(w, actor, "light hearth")
    result = w.act(actor, "kindle lamp")
    lamp = w.get("lamp")
    assert lamp.attrs.get("lit"), f"lamp didn't light at a lit hearth: {result!r}"
    # kindling's own action also ticks the world once, so a lit lamp has
    # already burned one fuel by the time we check -- same pattern as
    # add_wood, which never asserts an exact value right after its own tick.
    assert lamp.attrs["fuel"] >= LAMP_FUEL_START - 1, \
        f"lamp should light to (near) full fuel: {lamp.attrs['fuel']}"


def test_kindling_the_lamp_at_a_cold_hearth_fails():
    w, actor = fresh()
    result = w.act(actor, "kindle lamp")
    lamp = w.get("lamp")
    assert not lamp.attrs.get("lit"), "lamp lit from a cold hearth"
    assert "feed it first" in result.lower(), \
        f"refusal doesn't point at feeding the fire: {result!r}"


def test_kindling_the_lamp_in_the_yard_fails():
    w, actor = fresh()
    run(w, actor, "light hearth", "take lamp", "go out")
    result = w.act(actor, "kindle lamp")
    lamp = w.get("lamp")
    assert not lamp.attrs.get("lit"), "lamp lit outside, with no fire to catch from"
    assert "fire's inside" in result.lower(), f"unclear refusal: {result!r}"


def test_rekindling_an_already_lit_lamp_tops_its_fuel_back_to_full():
    w, actor = fresh()
    run(w, actor, "light hearth", "kindle lamp")
    lamp = w.get("lamp")
    lamp.attrs["fuel"] = 1                       # nearly spent
    result = w.act(actor, "kindle lamp")
    assert lamp.attrs["fuel"] >= LAMP_FUEL_START - 1, \
        "re-kindling didn't top the fuel back up"
    assert lamp.attrs.get("lit"), f"re-kindling should leave it lit: {result!r}"


def test_light_lamp_and_kindle_lamp_are_synonyms():
    w, actor = fresh()
    run(w, actor, "light hearth")
    result = w.act(actor, "light lamp")
    assert w.get("lamp").attrs.get("lit"), f"'light lamp' didn't kindle it: {result!r}"


def test_lit_lamp_makes_the_yard_visible_and_actionable_at_night():
    w, actor = fresh()
    while w.phase() != "dusk":
        w.act(actor, "wait")
    run(w, actor, "light hearth", "take lamp", "kindle lamp", "go out")
    while w.phase() != "night":
        w.act(actor, "wait")
    seen = w.perceive(actor)
    assert "pitch dark" not in seen.lower(), \
        f"yard should stay visible by the carried, lit lamp at night: {seen!r}"
    result = w.act(actor, "draw water")
    assert "draw water" in result.lower(), f"an action should still succeed: {result!r}"


def test_lamp_burn_low_and_burn_out_messages_fire_then_it_goes_dark():
    w, actor = fresh()
    run(w, actor, "light hearth", "kindle lamp")
    low_seen = out_seen = None
    for _ in range(LAMP_FUEL_START):
        line = w.act(actor, "wait")
        if "shrinks" in line:
            low_seen = True
        if "goes dark" in line:
            out_seen = True
    assert low_seen, "never saw the lamp's low-fuel warning"
    assert out_seen, "never saw the lamp go dark"
    assert not w.get("lamp").attrs.get("lit"), "lamp should be out after its fuel span"

    while w.phase() != "night":
        w.act(actor, "wait")
    result = w.act(actor, "go out")
    assert "pitch dark" in result.lower(), "with the lamp spent, night should be dark again"


def test_dark_go_out_with_no_lamp_names_both_affordances():
    w, actor = fresh()
    while w.phase() != "night":
        w.act(actor, "wait")
    result = w.act(actor, "go out")
    low = result.lower()
    assert "kindle" in low and "lamp" in low, f"dark message doesn't mention the lamp: {result!r}"
    assert "dawn" in low, f"dark message doesn't mention waiting for dawn: {result!r}"


def test_carried_lamp_line_reflects_its_state():
    w, actor = fresh()
    run(w, actor, "take lamp")
    assert "lamp (unlit)" in w.perceive(actor)
    run(w, actor, "light hearth", "light lamp")
    assert "lamp (lit)" in w.perceive(actor)
    w.get("lamp").attrs["fuel"] = LAMP_LOW_FUEL
    assert "lamp (lit, low)" in w.perceive(actor)


def test_fresh_world_starts_in_early_morning_with_light():
    w, actor = fresh()
    assert w.phase() in ("dawn", "day"), \
        f"fresh world should start in daylight, not {w.phase()}"
    result = w.act(actor, "go out")
    assert "pitch dark" not in result.lower(), "the yard should be visible on a fresh morning"


# ===========================================================================
# 5. THE POTATO ECONOMY -- self-healing ground, a last-potato beat, and an
#    honest journal refusal. The economy stays deliberately tight (harvest
#    still yields exactly 2, planting is still the load-bearing act); the
#    volunteer is a floor against total sterility, not a second faucet.
# ===========================================================================
def _sprout_a_volunteer(w, actor):
    """Shared setup: advance exactly PATCH_VOLUNTEER_TURNS empty ticks with
    the actor in the yard, so one volunteer reliably sprouts. 'go out' itself
    ticks once (empty_turns -> 1), so only T-2 more waits are needed before
    the final, spawning wait -- avoids an off-by-one across every caller."""
    run(w, actor, "go out")
    for _ in range(PATCH_VOLUNTEER_TURNS - 2):
        w.act(actor, "wait")
    return w.act(actor, "wait")


def test_volunteer_sprouts_after_T_empty_turns_with_one_time_message():
    w, actor = fresh()
    run(w, actor, "go out")
    for _ in range(PATCH_VOLUNTEER_TURNS - 2):
        result = w.act(actor, "wait")
        assert "stray shoot" not in result.lower(), "volunteer sprouted early"
    assert _crop_in(w, "yard") is None, "patch shouldn't have anything yet"
    result = w.act(actor, "wait")
    assert "stray shoot" in result.lower(), f"volunteer never announced: {result!r}"
    crop = _crop_in(w, "yard")
    assert crop is not None and not crop.attrs.get("ready"), \
        "the volunteer should be a fresh, unripe plant"


def test_healthy_cadence_never_triggers_the_volunteer():
    """Replanting well before T empty turns means the counter never gets
    anywhere close -- the volunteer must stay invisible in a working lineage."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato")
    for _ in range(20):
        if "harvest" in w.available_actions(actor):
            break
        w.act(actor, "wait")
    run(w, actor, "harvest", "plant potato")
    for _ in range(PATCH_VOLUNTEER_TURNS * 2):
        result = w.act(actor, "wait")
        assert "stray shoot" not in result.lower(), \
            "volunteer fired despite a healthy replanting cadence"


def test_patch_empty_counter_does_not_advance_while_non_empty():
    """No accumulation: once a plant exists, the counter must stay pinned at
    zero no matter how long it takes to ripen -- proving a second volunteer
    can never queue up behind the first."""
    w, actor = fresh()
    _sprout_a_volunteer(w, actor)
    patch = w.get("patch")
    for _ in range(PATCH_VOLUNTEER_TURNS * 2):
        w.act(actor, "wait")
        assert patch.attrs.get("empty_turns", 0) == 0, \
            "empty-turn counter advanced while the patch is non-empty"
    assert len(w.contents(patch.id)) == 1, \
        "a second plant appeared without the patch ever going empty"


def test_volunteer_ripens_and_harvests_normally():
    """Reuses the existing grow/ripen/harvest machinery -- a volunteer is
    mechanically identical to a planted crop, only its provenance differs."""
    w, actor = fresh()
    _sprout_a_volunteer(w, actor)
    for _ in range(20):
        if "harvest" in w.available_actions(actor):
            break
        w.act(actor, "wait")
    before = len([e for e in w.contents(actor.id) if "potato" in e.name])
    result = w.act(actor, "harvest")
    after = len([e for e in w.contents(actor.id) if "potato" in e.name])
    assert after - before == 2, f"volunteer harvest didn't yield 2: {result!r}"


def test_volunteer_timing_is_deterministic_not_random():
    def run_scenario():
        w, actor = fresh()
        run(w, actor, "go out")
        ticks = 0
        while _crop_in(w, "yard") is None:
            w.act(actor, "wait")
            ticks += 1
            assert ticks < PATCH_VOLUNTEER_TURNS + 5, "volunteer never sprouted"
        return ticks

    assert run_scenario() == run_scenario(), \
        "volunteer timing should be exactly reproducible, not randomized"


def test_legacy_save_without_empty_counter_does_not_instantly_spawn():
    """Backward-compat: a save predating this feature has no empty_turns
    field on the patch at all. It must default to 0, not to something that
    would spawn a volunteer the instant the save is loaded."""
    w, actor = fresh()
    run(w, actor, "go out")   # a couple of empty ticks, well under T
    run(w, actor, "wait")
    data = w.to_data()
    for e in data["entities"]:
        if e["id"] == "patch":
            e["attrs"].pop("empty_turns", None)   # simulate a genuinely old save

    w2 = World.from_data(data)
    actor2 = w2.get("you")
    result = w2.act(actor2, "wait")
    assert "stray shoot" not in result.lower(), \
        "a save missing the counter should not instantly spawn a volunteer"


def test_cooking_the_last_raw_potato_with_a_bare_patch_appends_the_beat():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in", "light hearth")
    result = w.act(actor, "cook potato")
    assert "blistered and steaming" in result.lower(), \
        f"cooking itself should still succeed: {result!r}"
    assert "last potato" in result.lower() and "patch lies bare" in result.lower(), \
        f"last-potato beat missing: {result!r}"


def test_feeding_the_last_raw_potato_to_the_cat_with_a_bare_patch_appends_the_beat():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in")
    w.get("cat").location = actor.location
    result = w.act(actor, "feed cat")
    assert "purrs" in result.lower()
    assert "last potato" in result.lower() and "patch lies bare" in result.lower(), \
        f"last-potato beat missing: {result!r}"


def test_last_potato_beat_does_not_repeat_on_later_turns():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in", "light hearth")
    w.act(actor, "cook potato")
    for _ in range(5):
        result = w.act(actor, "wait")
        assert "last potato" not in result.lower(), \
            "the one-shot beat repeated on a later turn"
    assert "last potato" not in w.perceive(actor).lower(), \
        "the beat leaked into the standing perception as a persistent warning"


def test_no_beat_when_another_raw_potato_remains():
    w, actor = fresh()
    run(w, actor, "go out", "take potato")
    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                 location=actor.id, portable=True))
    run(w, actor, "go in", "light hearth")
    result = w.act(actor, "cook potato")
    assert "last potato" not in result.lower(), \
        f"beat fired with a raw potato still in hand: {result!r}"


def test_no_beat_when_a_crop_is_still_growing():
    w, actor = fresh()
    run(w, actor, "go out", "take potato")
    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                 location=actor.id, portable=True))
    run(w, actor, "plant potato")             # one raw potato goes into the ground
    run(w, actor, "go in", "light hearth")
    result = w.act(actor, "cook potato")      # cook the other, now-last, raw potato
    assert "last potato" not in result.lower(), \
        f"beat fired while a crop is still growing: {result!r}"


def test_a_cooked_potato_in_hand_does_not_prevent_the_beat():
    w, actor = fresh()
    run(w, actor, "go out", "take potato")
    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                 location=actor.id, portable=True))
    run(w, actor, "go in", "light hearth", "cook potato")   # cooks one; 1 raw left
    result = w.act(actor, "cook potato")                     # cooks the last raw one
    assert "last potato" in result.lower(), \
        "a cooked potato already in hand shouldn't mask spending the last raw one"


def test_write_refusal_names_the_yard_when_the_journal_is_there():
    w, actor = fresh()
    w.get("journal").location = "yard"
    result = w.act(actor, "write hello")
    assert "yard" in result.lower(), f"refusal didn't name the yard: {result!r}"
    assert "hut" not in result.lower(), f"refusal still claims the hut: {result!r}"


def test_write_refusal_names_the_hut_by_default():
    w, actor = fresh()
    run(w, actor, "go out")   # journal stays behind in the hut
    result = w.act(actor, "write hello")
    assert "hut" in result.lower(), f"refusal didn't name the hut: {result!r}"


def test_write_refusal_uses_generic_fallback_for_an_unmapped_location():
    w, actor = fresh()
    w.get("journal").location = "patch"   # nowhere the refusal has a specific clause for
    result = w.act(actor, "write hello")
    assert "not here with you" in result.lower(), f"fallback clause missing: {result!r}"


def test_carried_journal_persists_across_a_reload_as_the_same_actor():
    """The journal is safe by construction: nothing drops inventory on
    departure, and the persistent 'you' entity keeps carrying it across
    visits. This regression-tests that guarantee directly."""
    w, actor = fresh()
    run(w, actor, "take journal", "go out")
    assert w.get("journal").location == actor.id, "journal should be carried"
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    actor2 = w2.get("you")
    assert w2.get("journal").location == actor2.id, \
        "a carried journal must still be held by the same actor after a reload"
    result = w2.act(actor2, "write still here")
    assert "ink dries" in result.lower()


# ===========================================================================
# 6. THE SEED JOURNAL -- widening what the journal is for. The three seed
#    entries a fresh world ships with model the register (operational
#    handover AND how-it-felt) so a lineage's own entries have somewhere
#    natural to land beyond pure handover. Seeded deliberately light on
#    specifics (see content.py's build_world) so later hands aren't just
#    echoing a plantable want back at the world.
# ===========================================================================
def test_fresh_world_seed_journal_has_the_three_widened_entries():
    w, actor = fresh()
    entries = w.get("journal").attrs["entries"]
    assert entries == [
        "[a while ago] To whoever comes next: the hearth cooks, and the lamp "
        "lights — kindle it at the hearth before the dark comes. Plant "
        "early; the potatoes take their time. There's a cat: feed it a "
        "potato when it's hungry, and it likes the fire lit.",
        "[some days later] Fed the cat, kept a potato in the ground, "
        "planted another before I left. Carry the rhythm on.",
        "[Day 1] Kept the fire fed and the cat fed — in that order, or the "
        "cat will let you know. Quiet few days, and I grew unexpectedly fond "
        "of the cat. Once or twice of an evening I caught myself wishing for "
        "a bit of company that wasn't four-legged; but you're a kind of "
        "company, reading this, even if we never share the room. I left "
        "before the harvest. — someone before you",
    ], f"seed journal entries don't match: {entries!r}"


def test_seed_journal_has_no_candle_reference():
    """Regression: the candle is retired (replaced by the tin lamp). Guards
    against the retired object's lore leaking into a new lineage's journal."""
    w, actor = fresh()
    entries = w.get("journal").attrs["entries"]
    assert not any("candle" in e.lower() for e in entries), \
        f"a seed entry still mentions the retired candle: {entries!r}"
    assert "lamp" in entries[0].lower() and "kindle" in entries[0].lower(), \
        f"day 1 should point at the lamp and kindling: {entries[0]!r}"


# ===========================================================================
# 7. DOCUMENTATION -- the reference generates from code, and nothing new can
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
