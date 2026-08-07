"""
test_content.py -- tests for Emberworld's own content: the gameplay loop,
verbs, behaviors, and the self-documenting reference. The cat has its own
subsystem and its own test file -- see cat.py / test_cat.py.

Run it either way:
    python3 -m pytest test_content.py -v      # if you have pytest
    python3 test_content.py                    # if you don't (built-in runner)
"""

import json
import random

from world import World, Entity, check_world, DAY_LENGTH
from content import (
    VERBS, BEHAVIORS, generate_reference, _crop_in, BUCKET_CAPACITY,
    bucket_state, WOOD_PER_GATHER, HEARTH_FUEL_START, FUEL_PER_WOOD,
    HEARTH_LOW_FUEL, hearth_state, FOUND_ITEMS, _found_description,
    FOREST_FIND_CHANCE, _STRAY_WOOD_SHARE, WOOD_PER_STRAY_FIND,
    LISTEN_LINES, cmd_listen,
    WATCH_CLOUD_LINES, WATCH_CLOUDS_NIGHT_MSG, cmd_watch_clouds,
    CALM_ACK_AT, CALM_ACK_LINE,
    CAIRN_ID, CAIRN_GROWTH_CM, CAIRN_BANDS, _cairn_description,
    ensure_cairn, cmd_stack_stone,
    LAMP_FUEL_START, LAMP_LOW_FUEL,
    PATCH_VOLUNTEER_TURNS,
    FOREST_FRAGMENTS, _forest_band, describe_forest, cmd_venture, cmd_return, cmd_mark_trail,
    SAFE_DEPTH_THRESHOLD, OFF_COURSE_CHANCE, OFF_COURSE_LINES,
    FOREST_AMBIENT_CHANCE, FOREST_AMBIENT, _forest_ambient,
    STATUE_MIN_DEPTH, STATUE_DISCOVERY_CHANCE, STATUE_DISCOVERY_TEXT,
    STATUE_WISH_LINE, ensure_statue, _statue_reachable, cmd_wish,
    MOON_CYCLE_DAYS, MOON_LINES, _is_full_moon,
    MOON_NEAR_NIGHTS, MOON_PHASE_OFFSET, MOON_VIEW_LINES, _moon_view,
    WILDLIFE_CHANCE, WILDLIFE_LINES, wildlife_glimpse,
    SHELF_CAPACITY, _shelf_description,
    WAIT_DARK_LINES, WAIT_DARK_HUT_LINES, WAIT_DARK_CAT_LINE, _wait_dark_lines,
    SEED_NAME, BLOOM_TICKS, BLOOM_SHOWING_AT, BLOOM_BUDDING_AT, BLOOM_BANDS,
    BLOOM_KINDS, _seed_in_world, _mystery_plant, _bloom_description,
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
def test_gather_wood_at_the_forest_edge_increases_carried_wood():
    """FOREST_SPEC.md Stage 7: wood-gathering relocated here from the yard."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    result = w.act(actor, "gather wood")
    assert actor.attrs["wood"] == WOOD_PER_GATHER, \
        f"gather didn't add {WOOD_PER_GATHER} wood: {actor.attrs}"
    assert str(WOOD_PER_GATHER) in result, f"result didn't name the new amount: {result!r}"


def test_gather_wood_is_gated_to_the_forest_edge_not_the_yard():
    w, actor = fresh()
    result = w.act(actor, "gather wood")           # still in the hut
    assert actor.attrs.get("wood", 0) == 0, "gathered wood outside the forest's edge"
    assert "forest" in result.lower()
    run(w, actor, "go out")                        # the yard -- no longer valid either
    result = w.act(actor, "gather wood")
    assert actor.attrs.get("wood", 0) == 0, "the yard should no longer yield wood"
    assert "forest" in result.lower()


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
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "gather wood")
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
    w.rng = _Unlucky()
    run(w, actor, "go out")
    assert "gather wood" not in w.available_actions(actor), \
        "gather wood should no longer be offered in the yard"

    run(w, actor, "go forest")
    assert "gather wood" in w.available_actions(actor), \
        "gather wood should be offered at the forest's edge"

    run(w, actor, "gather wood", "go yard", "go in")
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
    a lucky turn at the forest's edge sometimes turns up a small found
    object alongside the wood -- purely cosmetic, freely carried, named in
    the result. FOREST_SPEC.md Stage 7: this now comes via forest_finds'
    own per-tick roll (which fires on ANY forest-edge turn, gather-wood
    included), not a separate roll cmd_gather makes itself -- see the
    comment above cmd_gather for why a second roll would double-dip."""
    class Lucky:                             # force the find roll to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    w.rng = _Unlucky()          # don't let arrival itself roll a find first
    run(w, actor, "go out", "go forest")
    w.rng = Lucky()
    result = w.act(actor, "gather wood")
    found = [e for e in w.contents(actor.id) if e.location == actor.id]
    assert len(found) == 1, f"a lucky gather should add exactly one found item: {found}"
    name, look_line, reaction = FOUND_ITEMS[0]
    assert found[0].name == name
    assert found[0].description == _found_description(look_line, reaction)
    assert found[0].portable, "a found item must be carryable"
    assert found[0].attrs.get("curio"), "a found item should be marked as a curio"
    assert found[0].attrs.get("cat_reaction") == reaction
    assert name in result, f"result didn't name the find: {result!r}"


def test_found_items_table_is_well_formed():
    """Guards the data itself: every curio needs a unique name and a cat
    reaction the give-to-cat verb actually knows how to handle."""
    names = [name for name, _, _ in FOUND_ITEMS]
    assert len(names) == len(set(names)), "duplicate curio name in FOUND_ITEMS"
    for name, look_line, reaction in FOUND_ITEMS:
        assert reaction in ("plays", "ignores"), f"{name!r} has an unknown cat_reaction {reaction!r}"
        assert look_line == look_line.strip() and not look_line.endswith("."), \
            f"{name!r}'s look_line should be a bare fragment, not pre-punctuated: {look_line!r}"


def test_found_item_look_line_ends_with_a_cat_hint_only_when_cat_eligible():
    plays_line = _found_description("tight and resinous, one scale broken", "plays")
    ignores_line = _found_description("river-worn, a pale band round its middle", "ignores")
    assert plays_line == "tight and resinous, one scale broken — the cat might bat at it."
    assert ignores_line == "river-worn, a pale band round its middle."


def test_gather_wood_found_item_is_rare_not_guaranteed():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.act(actor, "gather wood")
    assert w.contents(actor.id) == [], "an unlucky gather shouldn't add a found item"
    assert actor.attrs["wood"] == WOOD_PER_GATHER, "wood itself must still be gathered"


def _stone_tuple():
    return next(t for t in FOUND_ITEMS if t[0] == "a smooth grey stone")


def test_shelf_displays_a_found_item_and_lets_a_later_hand_retrieve_it():
    """The shelf is persistent, legible storage rather than a decorative prop."""
    w, actor = fresh()
    assert "curio shelf" in w.get("shelf").description, \
        "the shelf should make its purpose legible to a visiting agent"
    stone_name, stone_look_line, stone_reaction = _stone_tuple()
    stone_description = _found_description(stone_look_line, stone_reaction)
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


def test_taking_the_last_item_off_the_shelf_reverts_its_description():
    """BUG WE HIT: taking an item back off the shelf left the shelf still
    describing itself as holding it -- _shelf_description was only ever
    recomputed by cmd_place (and the load-time migration), never by
    cmd_take, so a shelf a hand had emptied still read as holding the thing
    a later hand had already carried away."""
    w, actor = fresh()
    w.get("knife").location = actor.id
    run(w, actor, "place knife on shelf")
    shelf = w.get("shelf")
    assert "knife" in shelf.description
    run(w, actor, "take knife")
    assert "knife" not in shelf.description, f"stale shelf description: {shelf.description!r}"
    assert shelf.description == "a narrow curio shelf, empty but for a little dust"


def test_taking_one_of_two_shelf_items_still_lists_the_other():
    w, actor = fresh()
    w.get("knife").location = actor.id
    stone_name, stone_look_line, stone_reaction = _stone_tuple()
    stone = w.add(Entity(w.fresh_id("found"), stone_name,
                         _found_description(stone_look_line, stone_reaction),
                         location=actor.id, portable=True))
    run(w, actor, "place knife on shelf", f"place {stone_name} on shelf")
    shelf = w.get("shelf")
    run(w, actor, "take knife")
    assert "knife" not in shelf.description
    assert stone_name in shelf.description, f"the remaining item vanished too: {shelf.description!r}"


def test_taking_a_found_curio_does_not_double_the_article():
    """FOUND_ITEMS bakes its own article into the name (so the discovery and
    carried-item lines read naturally), but a verb response that prepends its
    own 'the' must strip it first, or it reads 'the a smooth grey stone'."""
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()   # "a smooth grey stone"
    desc = _found_description(look_line, reaction)
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location="yard", portable=True, attrs={"curio": True}))
    run(w, actor, "go out")
    result = w.act(actor, f"take {name}").splitlines()[0]
    assert result == "You take the smooth grey stone.", f"double article: {result!r}"


def test_dropping_a_found_curio_does_not_double_the_article():
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()
    desc = _found_description(look_line, reaction)
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    result = w.act(actor, f"drop {name}").splitlines()[0]
    assert result == "You set down the smooth grey stone.", f"double article: {result!r}"


def test_placing_a_found_curio_on_the_shelf_does_not_double_the_article():
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()
    desc = _found_description(look_line, reaction)
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    result = w.act(actor, f"place {name} on shelf").splitlines()[0]
    assert result == "You set the smooth grey stone on the shelf.", f"double article: {result!r}"


# ===========================================================================
# GIVE TO CAT -- the shelf's counterpart affordance. Every found curio has a
# cat_reaction ("plays"/"ignores"); either way, giving it consumes it from
# the pack and leaves a durable trace in the room, same as the shelf. Reset
# or richer: neither affordance may touch a maintenance resource (fire,
# food, water) -- see test_giving_or_placing_a_curio_touches_no_maintenance_
# resource below, which pins that line.
# ===========================================================================
def _curio_tuple(name):
    return next(t for t in FOUND_ITEMS if t[0] == name)


def _add_curio(world, actor, name, location=None):
    n, look_line, reaction = _curio_tuple(name)
    return world.add(Entity(world.fresh_id("found"), n,
                             _found_description(look_line, reaction),
                             location=location or actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": reaction}))


def test_look_at_a_carried_curio_shows_its_odd_line_and_cat_hint():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    result = w.act(actor, "look pinecone")
    assert result == "tight and resinous, one scale broken — the cat might bat at it."


def test_giving_a_play_curio_to_the_cat_fires_the_reaction_and_leaves_a_trace():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    result = w.act(actor, "give pinecone to cat")
    assert result.splitlines()[0] == \
        "The cat pounces on the pinecone, batting it round before losing interest."
    assert not any(e.name == "a pinecone" and e.location == actor.id
                   for e in w.contents(actor.id)), "giving it away must consume it from the pack"
    assert "well-battered after a game with the cat" in w.perceive(actor)


def test_giving_an_ignored_curio_to_the_cat_still_leaves_a_trace():
    w, actor = fresh()
    _add_curio(w, actor, "a smooth grey stone")
    result = w.act(actor, "give stone to cat")
    assert result.splitlines()[0] == \
        "The cat sniffs the smooth grey stone once, unimpressed, and stalks off."
    assert "given to the cat and roundly ignored" in w.perceive(actor)


# ===========================================================================
# BUG WE HIT (real lineage transcript): a hand carrying two pinecones could
# never place OR give either one, turn after turn, because an earlier hand
# had already given a pinecone to the cat -- which leaves a permanent,
# non-portable trace behind in the room, still named "a pinecone". find_
# visible's default search order is room-contents-first, so that trace
# always matched before either carried pinecone, and cmd_place/cmd_give saw
# e.location != actor.id and refused -- forever, since the trace never goes
# away. Fixed by passing prefer=lambda e: _carrying(...) at every call site
# that requires a CARRIED match (place, give, drop, stack_stone) -- find_
# visible already had a `prefer` param built for exactly this. cmd_take is
# deliberately untouched: it SHOULD prefer a room item over one you already
# hold, so picking up a second copy still works.
# ===========================================================================
def test_place_finds_a_carried_curio_even_when_a_same_named_trace_is_in_the_room():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")          # given away, becomes a trace
    _add_curio(w, actor, "a pinecone")          # the one still carried
    w.act(actor, "give pinecone to cat")
    result = w.act(actor, "place pinecone on shelf")
    assert result.splitlines()[0] == "You set the pinecone on the shelf."


def test_give_finds_a_carried_curio_even_when_a_same_named_trace_is_in_the_room():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "give pinecone to cat")
    result = w.act(actor, "give pinecone to cat")
    assert "aren't carrying" not in result.lower()


def test_drop_finds_a_carried_item_even_when_a_same_named_one_already_lies_in_the_room():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone", location=actor.location)   # already on the ground
    _add_curio(w, actor, "a pinecone")                            # the carried one
    result = w.act(actor, "drop pinecone")
    assert result.splitlines()[0] == "You set down the pinecone."


def test_stack_stone_finds_a_carried_stone_even_when_a_same_named_item_lies_in_the_room():
    """The cat never reaches the forest's edge, so a give-to-cat trace can't
    land here the way it does for place/give/drop in the hut/yard -- but any
    non-carried, same-named item lying in the room is the same class of bug,
    however it got there."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.add(Entity(w.fresh_id("found"), "a smooth grey stone",
                 "a smooth grey stone, left behind by someone else",
                 location="forest_edge", portable=False,
                 attrs={"curio": True, "cat_reaction": "ignores"}))
    _add_curio(w, actor, "a smooth grey stone")   # the one actually carried
    result = cmd_stack_stone(w, actor, "")
    assert "no stone" not in result.lower()
    assert w.get(CAIRN_ID).attrs["height_cm"] > 0


def test_give_trace_persists_across_a_save_load_roundtrip():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "give pinecone to cat")
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert "well-battered after a game with the cat" in w2.perceive(w2.get("you"))


def test_putting_a_curio_on_the_shelf_via_the_put_alias():
    w, actor = fresh()
    _add_curio(w, actor, "a bone button")
    result = w.act(actor, "put bone button on shelf")
    assert "shelf" in result.lower()
    assert any(e.name == "a bone button" for e in w.contents("shelf"))


# ===========================================================================
# SHELF CAPACITY -- the shelf's deliberate contrast with the cairn: personal
# and curated (capped, reversible) rather than collective and boundless
# (unlimited, permanent). Nothing decays or is punished at capacity -- a
# hand just has to choose whether a new find is worth a spot.
# ===========================================================================
def _fill_shelf(world, actor):
    """Place SHELF_CAPACITY curios on the shelf directly (bypassing the
    verb, since we don't care about the placing turn-by-turn here)."""
    shelf = world.get("shelf")
    for _ in range(SHELF_CAPACITY):
        e = _add_curio(world, actor, "a pinecone")
        e.location = shelf.id
    shelf.description = _shelf_description(world, shelf)
    return shelf


def test_shelf_refuses_placement_once_it_holds_shelf_capacity_items():
    w, actor = fresh()
    _fill_shelf(w, actor)
    _add_curio(w, actor, "a bone button")
    result = w.act(actor, "place bone button on shelf")
    assert "full" in result.lower()
    assert not any(e.name == "a bone button" for e in w.contents("shelf"))


def test_shelf_accepts_a_placement_again_after_making_room():
    w, actor = fresh()
    _fill_shelf(w, actor)
    taken = w.contents("shelf")[0]
    w.act(actor, f"take {taken.name}")
    _add_curio(w, actor, "a bone button")
    result = w.act(actor, "place bone button on shelf")
    assert "full" not in result.lower()
    assert any(e.name == "a bone button" for e in w.contents("shelf"))


def test_shelf_description_reads_full_up_only_at_capacity():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "place pinecone on shelf")
    assert "full up" not in w.get("shelf").description
    shelf = _fill_shelf(w, actor)
    assert "full up" in shelf.description


def test_place_is_not_offered_once_the_shelf_is_full():
    w, actor = fresh()
    _fill_shelf(w, actor)
    _add_curio(w, actor, "a bone button")
    assert not any(a.startswith("place ") for a in w.available_actions(actor))


def test_gather_can_still_yield_a_find_after_giving_one_away():
    class Lucky:
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "give pinecone to cat")   # the cat starts in the hut
    w.rng = _Unlucky()                     # don't let arrival itself roll first
    run(w, actor, "go out", "go forest")
    w.rng = Lucky()
    result = w.act(actor, "gather wood")
    assert "you pocket it" in result, "a curio must stay refindable after one is given away"


def test_give_redirects_a_non_curio_to_feed():
    w, actor = fresh()
    run(w, actor, "go out", "take potato")
    w.get("cat").location = actor.location   # the cat wanders on its own; pin it here
    result = w.act(actor, "give potato to cat")
    assert "feed" in result.lower()
    assert any("potato" in e.name for e in w.contents(actor.id)), \
        "a redirected give must not consume the item"


def test_give_requires_a_cat_in_the_room():
    w, actor = fresh()          # actor starts in the hut; move the cat out
    _add_curio(w, actor, "a pinecone")
    w.get("cat").location = "yard"
    result = w.act(actor, "give pinecone to cat")
    assert "no cat here" in result.lower()


def test_give_requires_carrying_the_item():
    w, actor = fresh()
    result = w.act(actor, "give pinecone to cat")
    assert "aren't carrying" in result.lower()


def test_giving_or_placing_a_curio_touches_no_maintenance_resource():
    """The invariant that guards the whole feature: a found-thing affordance
    may only ever leave the world richer (a durable trace), never touch a
    resource that feeds a maintenance loop (cat hunger, water, firewood,
    fire-life), and must not itself advance the clock. Calls the handler
    directly rather than through world.act -- going through act() would tick
    the world and let unrelated autonomous behaviors (hunger rising, fire
    burning down) muddy exactly what THIS handler did or didn't touch."""
    from content import cmd_give, cmd_place
    handlers = {"give": (cmd_give, "to cat"), "put": (cmd_place, "on shelf")}
    for verb, item in (("give", "a pinecone"), ("give", "a smooth grey stone"),
                       ("put", "a bone button")):
        w, actor = fresh()
        cat = w.get("cat")
        cat.location = actor.location
        cat.attrs["hunger"] = 5
        hearth = w.get("hearth")
        hearth.attrs["lit"] = True
        hearth.attrs["fuel"] = 10
        actor.attrs["wood"] = 4
        w.get("bucket").attrs["water"] = 2
        time_before, day_before = w.time, w.day()

        _add_curio(w, actor, item)
        fn, suffix = handlers[verb]
        fn(w, actor, f"{item.split(' ', 1)[1]} {suffix}")

        assert cat.attrs["hunger"] == 5, "give/put must not touch cat hunger"
        assert w.get("bucket").attrs["water"] == 2, "must not touch the bucket"
        assert actor.attrs["wood"] == 4, "must not touch firewood"
        assert hearth.attrs["lit"] and hearth.attrs["fuel"] == 10, "must not touch fire-life"
        assert w.time == time_before, "the handler itself must not advance the clock"
        assert w.day() == day_before


def test_actions_lists_the_current_options_without_passing_time():
    w, actor = fresh()
    w.get("knife").location = actor.id
    before = w.time
    result = w.act(actor, "actions")
    assert w.time == before, "asking for actions should be free"
    assert "Available actions:" in result and "go out" in result
    assert "place knife on shelf" in result, "contextual shelf action was omitted"


def test_actions_offers_give_to_cat_when_carrying_a_curio_alongside_the_cat():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    actions = w.available_actions(actor)
    assert "give a pinecone to cat" in actions, "give-to-cat wasn't offered"


def test_actions_does_not_offer_give_to_cat_without_the_cat_present():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.get("cat").location = "yard"     # actor stays in the hut
    actions = w.available_actions(actor)
    assert not any(a.startswith("give ") for a in actions)


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


def _wait_to_night(w, actor):
    while w.phase() != "night":
        w.act(actor, "wait")


def test_pet_the_cat_works_in_the_dark():
    w, actor = fresh()
    _wait_to_night(w, actor)
    w.get("cat").location = actor.location    # the cat wanders on its own; pin it here
    result = w.act(actor, "pet cat")
    assert "purrs" in result.lower(), \
        f"a hand should be able to pet the cat in the dark: {result!r}"


def test_eat_a_held_cooked_potato_works_in_the_dark():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in", "light hearth", "cook potato",
        "snuff hearth")
    _wait_to_night(w, actor)
    result = w.act(actor, "eat broiled potato")
    assert "you eat" in result.lower(), \
        f"a hand should be able to eat held food in the dark: {result!r}"


def test_wait_in_the_dark_gives_a_quiet_line_not_the_daytime_stock_phrase():
    # world.act may append other rooms' ambient announcements (e.g. the cat
    # wandering) after the wait line itself, so compare only the first line.
    w, actor = fresh()
    _wait_to_night(w, actor)
    result = w.act(actor, "wait").splitlines()[0]
    assert result != "You wait. Time passes.", \
        "a dark wait should read differently from a daylight one"
    assert result in _wait_dark_lines(w, actor), \
        f"unexpected dark-wait line: {result!r}"


def test_wait_lines_vary_across_a_dark_stretch():
    # Repeated calls straight to the handler, not world.act -- world.act's
    # own tick would march time (and the phase) forward each call, and
    # night is only a handful of ticks long before it rolls into dawn.
    w, actor = fresh()
    _wait_to_night(w, actor)
    seen = {VERBS["wait"](w, actor, "") for _ in range(40)}
    assert len(seen) > 1, "40 dark waits should surface more than one line"


def test_wait_in_daylight_is_unaffected():
    w, actor = fresh()
    assert w.act(actor, "wait").splitlines()[0] == "You wait. Time passes."


def test_dark_wait_pool_includes_hut_only_lines_in_the_hut():
    w, actor = fresh()
    _wait_to_night(w, actor)
    assert actor.location == "hut"
    for line in WAIT_DARK_HUT_LINES:
        assert line in _wait_dark_lines(w, actor)


def test_dark_wait_pool_excludes_hut_only_lines_outside_the_hut():
    w, actor = fresh()
    run(w, actor, "go out")
    _wait_to_night(w, actor)
    assert actor.location == "yard"
    pool = _wait_dark_lines(w, actor)
    for line in WAIT_DARK_HUT_LINES:
        assert line not in pool, "yard shouldn't get hut furniture in its wait lines"


def test_dark_wait_pool_includes_the_cat_line_only_when_the_cat_is_present():
    w, actor = fresh()
    _wait_to_night(w, actor)
    w.get("cat").location = actor.location    # the cat wanders on its own; pin it here
    assert WAIT_DARK_CAT_LINE.format(cat="The cat") in _wait_dark_lines(w, actor)

    w.get("cat").location = "yard"            # send it elsewhere
    pool = _wait_dark_lines(w, actor)
    assert WAIT_DARK_CAT_LINE.format(cat="The cat") not in pool, \
        "the cat shouldn't be heard from a room it isn't in"


def test_dark_wait_cat_line_uses_a_given_name_once_the_cat_has_one():
    w, actor = fresh()
    run(w, actor, "name cat Ember")
    _wait_to_night(w, actor)
    w.get("cat").location = actor.location    # the cat wanders on its own; pin it here
    assert WAIT_DARK_CAT_LINE.format(cat="Ember") in _wait_dark_lines(w, actor)


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


def test_write_stamps_plain_day_when_the_world_has_no_hand_name():
    w, actor = fresh()
    result = w.act(actor, "write hello")
    assert "ink dries" in result.lower()
    entry = w.get("journal").attrs["entries"][-1]
    assert entry.startswith("[Day 1] hello"), f"unexpected stamp: {entry!r}"


def test_write_stamps_day_and_name_when_the_world_has_a_hand_name():
    """The LLM driver sets world.hand_name once at session start (see
    drivers.py); cmd_write's stamp must pick it up so attribution lands in
    the stamp itself rather than needing a manual sign-off."""
    w, actor = fresh()
    w.hand_name = "Wren"
    w.act(actor, "write hello")
    entry = w.get("journal").attrs["entries"][-1]
    assert entry.startswith("[Day 1, Wren] hello"), f"unexpected stamp: {entry!r}"


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
# 6. THE SEED JOURNAL -- a fresh world ships with a single seed entry: pure
#    operational handover (hearth, lamp, potatoes, cat), giving a lineage's
#    own entries a clear, minimal model to follow.
# ===========================================================================
def test_fresh_world_seed_journal_has_one_seed_entry():
    w, actor = fresh()
    entries = w.get("journal").attrs["entries"]
    assert entries == [
        "[Day 1, Wren] To whoever comes next: the hearth cooks, and the lamp "
        "lights — kindle it at the hearth before the dark comes. Plant "
        "early; the potatoes take their time. There's a cat: feed it a "
        "potato when it's hungry, and it likes the fire lit. I left before "
        "the harvest.",
    ], f"seed journal entries don't match: {entries!r}"


def test_seed_journal_has_no_candle_reference():
    """Regression: the candle is retired (replaced by the tin lamp). Guards
    against the retired object's lore leaking into a new lineage's journal."""
    w, actor = fresh()
    entries = w.get("journal").attrs["entries"]
    assert not any("candle" in e.lower() for e in entries), \
        f"a seed entry still mentions the retired candle: {entries!r}"


def test_seed_journal_has_no_sign_off_tic():
    """Regression: the dated seed used to end '-- someone before you', which
    hands were copying into their own entries as '-- a visitor'. Now that
    attribution lives in the stamp (see cmd_write), no seed should model
    manual signing."""
    w, actor = fresh()
    entries = w.get("journal").attrs["entries"]
    assert not any(e.rstrip().endswith("you") and "—" in e for e in entries), \
        f"a seed entry still models a manual sign-off: {entries!r}"
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


def test_every_verb_docstring_is_a_single_physical_line():
    """BUG WE HIT: cmd_look grew a wrapped, multi-line docstring (explaining
    the "look actions" alias) -- _first_line only reads the docstring's
    literal first physical line, by convention documented on _first_line
    itself, so REFERENCE.md silently rendered a mid-sentence-truncated
    summary ("...dark hides" with no closing thought). Explanatory detail
    belongs in a regular comment above the function, not stuffed into the
    docstring past its first line."""
    wrapped = sorted({fn.__name__ for fn in {*VERBS.values()}
                      if fn.__doc__ and fn.__doc__.strip().count("\n") > 0})
    assert not wrapped, f"verb docstrings must be a single physical line: {wrapped}"


def test_reference_generates_and_mentions_key_things():
    ref = generate_reference()
    assert "## Verbs" in ref and "## Autonomous behaviors" in ref
    # a few anchors so a totally broken generator is caught
    for anchor in ("plant <potato|seed>", "feed cat", "burning", "cat_wander"):
        assert anchor in ref, f"reference missing '{anchor}'"
    assert str(CAT_HUNGER_CAP) in ref, "numeric rules didn't render"


# ===========================================================================
# 8. THE FOREST'S EDGE -- v1: a doorway, not the forest. One new room off the
#    yard that turns up curios far more reliably than a yard gather, so a
#    hand that wants one can go get one instead of waiting on an RNG roll
#    mid-chore. No statue, no herb, no wood-relocation, no going deeper --
#    the dark ahead stays description-only.
# ===========================================================================
class _Lucky:                                # force the find roll to fire
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


class _Unlucky:                              # never let the find roll fire
    def random(self): return 1.0
    def choice(self, seq): return seq[0]


def test_yard_lists_a_visible_exit_to_the_forest_edge():
    """Regression-guard against the invisible-affordance failure: a hand
    must be able to SEE it can go to the forest before it'll ever try."""
    w, actor = fresh()
    w.rng = _Unlucky()                       # keep the yard's own gather-adjacent chance out of it
    run(w, actor, "go out")
    seen = w.perceive(actor)
    assert "forest" in seen.lower(), f"forest exit isn't visible: {seen!r}"
    assert "go forest" in w.available_actions(actor)


def test_going_to_the_forest_edge_arrives_and_offers_the_way_back():
    w, actor = fresh()
    w.rng = _Unlucky()
    result = run(w, actor, "go out", "go forest")
    assert actor.location == "forest_edge"
    assert "FOREST" in result.upper()
    assert "yard" in result.lower()
    assert "go yard" in w.available_actions(actor)


def test_exits_line_uses_longer_descriptive_labels_not_bare_direction_words():
    """The Exits: line is scene-setting prose, not the literal command list --
    that's `actions`/available_actions, which still shows the short 'go in'/
    'go forest' commands untouched. So the label here can read as a longer,
    more legible phrase without costing a hand anything it could type."""
    w, actor = fresh()
    w.rng = _Unlucky()
    hut_seen = w.perceive(actor)
    assert "Exits: the yard" in hut_seen, f"hut exits: {hut_seen!r}"

    yard_seen = run(w, actor, "go out")
    assert "Exits: inside the hut, the forest's edge" in yard_seen, f"yard exits: {yard_seen!r}"

    forest_seen = w.act(actor, "go forest")
    assert "Exits: back to the yard" in forest_seen, f"forest exits: {forest_seen!r}"

    # the short forms a hand actually types are untouched
    assert "go yard" in w.available_actions(actor)


def test_lingering_at_the_forest_edge_can_turn_up_a_curio():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")         # arrive with no lucky roll yet
    assert w.contents(actor.id) == [], "setup should start carrying nothing"
    w.rng = _Lucky()
    result = w.act(actor, "wait")
    found = [e for e in w.contents(actor.id) if e.attrs.get("curio")]
    assert len(found) == 1, f"a lucky turn at the forest's edge should add a curio: {found}"
    name, look_line, reaction = FOUND_ITEMS[0]
    assert found[0].name == name
    assert found[0].description == _found_description(look_line, reaction)
    assert name in result, f"the wait result should name the find: {result!r}"


def test_forest_edge_find_is_not_guaranteed_every_turn():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "wait")
    assert w.contents(actor.id) == [], "an unlucky turn shouldn't add a curio"


def test_forest_edge_entries_do_not_always_yield_a_curio():
    """Pacing rebalance regression guard: the old FOREST_FIND_CHANCE (0.5)
    felt near-guaranteed per visit and flooded packs with curios. With real
    (unseeded) randomness, repeatedly leaving and re-entering the forest
    should sometimes come up empty -- a find is a delight, not a faucet."""
    w, actor = fresh()
    run(w, actor, "go out")
    misses = 0
    for _ in range(30):
        before = len([e for e in w.contents(actor.id) if e.attrs.get("curio")])
        run(w, actor, "go forest", "go yard")
        after = len([e for e in w.contents(actor.id) if e.attrs.get("curio")])
        if after == before:
            misses += 1
    assert misses > 0, "30 forest entries all found a curio -- finds aren't rare enough"


def test_forest_find_chance_was_cut_again_after_a_real_playtest_complaint():
    """Pacing rebalance, round two: a hand that lingered at the forest's
    edge for only a handful of turns (waiting, or -- once FOREST_SPEC.md
    Stage 1 landed -- shuttling depth with venture/return) kept landing
    3-4 curios in "a few steps." forest_finds rolls on ANY tick spent at
    forest_edge regardless of which verb burns it (see forest_finds below),
    so more turns there always means more rolls -- the fix is the per-tick
    chance itself, not which verb is used to linger. (The old yard-side
    FOUND_ITEM_CHANCE this used to be compared against is retired -- see
    FOREST_SPEC.md Stage 7, wood-gathering relocated here and dropped its
    own separate roll rather than double the effective chance.)"""
    assert FOREST_FIND_CHANCE <= 0.1


def test_forest_found_curio_behaves_like_any_other_curio():
    """No forked curio type: something found at the forest's edge can be
    carried home and given to the cat or set on the shelf exactly like a
    yard-found curio."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = _Lucky()
    run(w, actor, "wait")
    found = next(e for e in w.contents(actor.id) if e.attrs.get("curio"))
    w.rng = _Unlucky()
    run(w, actor, "go yard", "go in")            # carry it back to the hut and its shelf
    result = w.act(actor, f"place {found.name} on shelf")
    assert found.location == w.get("shelf").id
    assert "shelf" in result.lower()


class _LuckyWood:
    """Forces the forest-find roll into its wood sub-range specifically --
    _Lucky's flat 0.0 always lands in the curio sub-range instead (see
    forest_finds: the wood outcome is carved out of the HIGH end of the
    existing roll, precisely so 0.0 keeps meaning "curio" for every
    existing _Lucky-based test above)."""
    def random(self):
        threshold = FOREST_FIND_CHANCE * (1 - _STRAY_WOOD_SHARE)
        return (threshold + FOREST_FIND_CHANCE) / 2

    def choice(self, seq): return seq[0]


def test_forest_edge_can_turn_up_a_stray_piece_of_wood_unprompted():
    """The ask: wood should sometimes turn up while exploring the forest --
    waiting, venturing, returning -- even on a turn that was never
    `gather wood`."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    assert actor.attrs.get("wood", 0) == 0, "setup should start carrying no wood"
    w.rng = _LuckyWood()
    result = w.act(actor, "wait")
    assert actor.attrs.get("wood", 0) == WOOD_PER_STRAY_FIND
    assert "wood" in result.lower()


def test_stray_wood_find_does_not_also_add_a_curio():
    """One roll, one outcome -- a stray-wood turn isn't a bonus curio too."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = _LuckyWood()
    run(w, actor, "wait")
    assert [e for e in w.contents(actor.id) if e.attrs.get("curio")] == []


def test_stray_wood_find_works_on_a_venture_turn_not_just_wait():
    """The whole point: it shouldn't matter which verb burned the turn --
    venture/return never move actor.location off forest_edge, so the same
    roll that already covers `wait` covers exploring deeper too."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = _LuckyWood()
    w.act(actor, "venture")
    assert actor.attrs.get("wood", 0) == WOOD_PER_STRAY_FIND


def test_stray_wood_find_is_a_smaller_haul_than_deliberate_gathering():
    """An ambient trickle, not a substitute for `gather wood` -- the
    deliberate action must still be the better haul."""
    assert WOOD_PER_STRAY_FIND < WOOD_PER_GATHER


def test_forest_edge_has_no_further_exit_into_the_woods():
    """Guards the creep-line: the dark ahead is description-only in v1, no
    second room, so nobody accidentally wires one in later without noticing."""
    w, actor = fresh()
    forest = w.get("forest_edge")
    assert set(forest.exits) == {"yard"}, f"unexpected exits: {forest.exits}"


def test_forest_edge_and_a_found_curio_survive_save_load_roundtrip():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = _Lucky()
    run(w, actor, "wait")
    found = next(e for e in w.contents(actor.id) if e.attrs.get("curio"))
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    actor2 = w2.get("you")
    assert actor2.location == "forest_edge"
    carried2 = next(e for e in w2.contents(actor2.id) if e.attrs.get("curio"))
    assert carried2.name == found.name


# ===========================================================================
# LISTEN -- the forest's-edge calm affordance. Pacing rebalance change 3: a
# chosen, unpressured turn that changes nothing, the counterpart to freer
# maintenance cadence and rarer finds (changes 1 and 2) -- the thing that
# catches the quiet turns those changes open up.
# ===========================================================================
def test_listen_is_offered_and_cued_at_the_forest_edge():
    """Legibility: a hand shouldn't have to guess the verb exists."""
    w, actor = fresh()
    w.rng = _Unlucky()
    result = run(w, actor, "go out", "go forest")
    assert "listen" in w.available_actions(actor)
    assert "listen" in result.lower(), f"no cue in the room text: {result!r}"


def test_listen_is_not_available_outside_the_forest_edge():
    w, actor = fresh()
    result = w.act(actor, "listen")
    assert "forest" in result.lower()
    assert "listen" not in w.available_actions(actor)


def test_listen_touches_no_world_state():
    """The constraint that must never break: listen grants nothing, ever --
    no curio, no state, no buff, no accumulation. Calling the handler
    directly (not through world.act) isolates that from the ambient ticking
    every non-free verb also triggers (fire burning, hunger rising, a forest
    find roll) -- the same reasoning as the give/place invariant test."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    before = w.to_data()
    cmd_listen(w, actor, "")
    after = w.to_data()
    assert before == after, "listen must not change anything, ever"


def test_listen_costs_a_turn_through_the_normal_dispatch():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    t0 = w.time
    w.act(actor, "listen")
    assert w.time == t0 + 1, "listen should cost exactly one turn, like any other real action"


def test_listen_returns_varied_lines_not_always_the_same_one():
    class Cycle:                             # walk the line pool in order
        def __init__(self):
            self.i = 0
        def choice(self, seq):
            v = seq[self.i % len(seq)]
            self.i += 1
            return v
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = Cycle()
    # strip the calm-axis ack: the 3rd call in this run carries it (see
    # CALM_ACK_AT), which would otherwise break the exact-line comparison.
    seen = {cmd_listen(w, actor, "").replace(CALM_ACK_LINE, "")
            for _ in range(len(LISTEN_LINES))}
    assert seen == set(LISTEN_LINES), "listen should draw from its full line pool"


# ===========================================================================
# WATCH CLOUDS -- the yard's (and forest's edge's) calm affordance, listen's
# sibling. Same shape, same invariant: a chosen, unpressured turn that
# changes nothing. The one difference is it reads the sky, so it's withdrawn
# outright at night rather than describing a fixed thing every time.
# ===========================================================================
def test_watch_clouds_is_offered_and_cued_in_the_yard():
    """Legibility, both signals: listed in actions, and cued in room text."""
    w, actor = fresh()
    result = run(w, actor, "go out")
    assert "watch clouds" in w.available_actions(actor)
    assert "cloud" in result.lower(), f"no cue in the room text: {result!r}"


def test_watch_clouds_is_also_available_at_the_forest_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    assert "watch clouds" in w.available_actions(actor)


def test_watch_clouds_is_not_available_in_the_hut():
    w, actor = fresh()
    assert "watch clouds" not in w.available_actions(actor)
    result = w.act(actor, "watch")
    assert "sky" in result.lower()


def test_watch_clouds_touches_no_world_state():
    """The same never-break constraint as listen: no reward, no state, no
    accumulation of any kind -- only the clock advances."""
    w, actor = fresh()
    run(w, actor, "go out")
    before = w.to_data()
    cmd_watch_clouds(w, actor, "")
    after = w.to_data()
    assert before == after, "watch clouds must not change anything, ever"


def test_watch_clouds_costs_a_turn_through_the_normal_dispatch():
    w, actor = fresh()
    run(w, actor, "go out")
    t0 = w.time
    w.act(actor, "watch")
    assert w.time == t0 + 1, "watch clouds should cost exactly one turn"


def test_watch_clouds_can_be_used_at_any_forest_depth_not_just_the_edge():
    """actor.location stays "forest_edge" at any depth (venturing is a
    counter, not a real room change), so watch clouds/gather wood/listen
    all already work deep in the forest, not just standing at the edge --
    this pins that so it can't regress."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert w.forest_depth == 3
    assert "watch clouds" in w.available_actions(actor)
    assert "gather wood" in w.available_actions(actor)
    assert "listen" in w.available_actions(actor)


def test_no_watch_cloud_line_names_a_specific_room():
    """BUG WE HIT: the day pool's "the yard dims and brightens" line was
    fine when watch clouds only worked in the yard, but it's shared by the
    yard, the forest's edge, AND every forest depth (see the test above) --
    a line naming one specific place reads wrong from all the others."""
    for pool in WATCH_CLOUD_LINES.values():
        for line in pool:
            assert "yard" not in line.lower(), f"line names a specific room: {line!r}"


def test_watch_clouds_returns_varied_lines_from_the_current_phases_pool():
    class Cycle:                             # walk the line pool in order
        def __init__(self):
            self.i = 0
        def choice(self, seq):
            v = seq[self.i % len(seq)]
            self.i += 1
            return v
    w, actor = fresh()
    run(w, actor, "go out")
    assert w.phase() in ("dawn", "day"), f"expected daylight, got {w.phase()}"
    pool = WATCH_CLOUD_LINES[w.phase()]
    w.rng = Cycle()
    seen = {cmd_watch_clouds(w, actor, "") for _ in range(len(pool))}
    assert seen == set(pool), "watch clouds should draw from the current phase's full pool"


def test_watch_clouds_line_matches_dusk_once_dusk_falls():
    w, actor = fresh()
    run(w, actor, "go out")
    while w.phase() != "dusk":
        w.act(actor, "wait")
    line = cmd_watch_clouds(w, actor, "")
    assert line in WATCH_CLOUD_LINES["dusk"], \
        f"a dusk call returned a line outside the dusk pool: {line!r}"


def test_watch_clouds_is_withdrawn_at_night():
    """Withdrawal, not a forced night line: the affordance quietly disappears
    when it wouldn't make sense, the same call the world already makes for
    darkness elsewhere.

    BUG WE HIT: this used to call w.act(actor, "watch") and assert the
    result equalled WATCH_CLOUDS_NIGHT_MSG exactly -- flaky, because going
    through world.act() also ticks the world, and the cat's own autonomous
    wandering can announce a line ("The cat pads out into the yard...") in
    that same tick, which gets appended to the result and breaks the exact
    match maybe 1 time in 5. Calling cmd_watch_clouds directly (as its
    sibling tests in this section already do) sidesteps the tick entirely,
    the same reasoning as test_watch_clouds_touches_no_world_state above."""
    w, actor = fresh()
    run(w, actor, "go out")
    while w.phase() != "night":
        w.act(actor, "wait")
    assert "watch clouds" not in w.available_actions(actor)
    result = cmd_watch_clouds(w, actor, "")
    assert result == WATCH_CLOUDS_NIGHT_MSG
    all_lines = [ln for pool in WATCH_CLOUD_LINES.values() for ln in pool]
    assert result not in all_lines


# ===========================================================================
# THE FULL MOON -- the one exception to the night withdrawal above. A real,
# uncontrollable clock (MOON_CYCLE_DAYS, keyed off world.day(), not tied to
# any session-scoped state) rather than a dice roll, so it's the one case a
# hand can actually witness the world running on a schedule bigger than any
# single visit. Purely descriptive -- same never-break constraint as every
# other calm-axis verb.
# ===========================================================================
def _set_to_full_moon_night(world):
    """Jump straight to a full-moon night without ticking hundreds of turns
    through world.act (which would also run every other tick behavior).
    Finds the actual day satisfying the phase-offset formula rather than
    assuming day MOON_CYCLE_DAYS -- MOON_PHASE_OFFSET means the first full
    moon isn't on day MOON_CYCLE_DAYS at all (see _moon_view)."""
    day = next(d for d in range(1, MOON_CYCLE_DAYS * 2)
               if (d + MOON_PHASE_OFFSET) % MOON_CYCLE_DAYS == 0)
    world.time = (day - 1) * DAY_LENGTH + 20  # hour 20 -> phase() == "night"


def _moon_view_on_day(d):
    """Test-only stand-in: _moon_view only ever calls world.day(), so a
    bare object with that one method is enough to probe the whole
    29-day schedule without constructing or ticking a real World."""
    class _Day:
        def day(self):
            return d
    return _moon_view(_Day())


def test_full_moon_recurs_every_moon_cycle_days():
    w, actor = fresh()
    assert not _is_full_moon(w)             # day 1 is never a full moon
    _set_to_full_moon_night(w)
    assert w.phase() == "night"
    assert _is_full_moon(w)
    w.time += DAY_LENGTH * MOON_CYCLE_DAYS   # exactly one cycle later
    assert _is_full_moon(w)
    w.time += DAY_LENGTH                     # one day past that
    assert not _is_full_moon(w)


def test_watch_clouds_returns_a_moon_line_on_a_full_moon_night():
    w, actor = fresh()
    run(w, actor, "go out")
    _set_to_full_moon_night(w)
    assert "watch clouds" in w.available_actions(actor)
    result = cmd_watch_clouds(w, actor, "")
    assert result in MOON_LINES
    assert result != WATCH_CLOUDS_NIGHT_MSG


def test_watch_clouds_still_refuses_on_an_ordinary_night():
    w, actor = fresh()
    run(w, actor, "go out")
    while w.phase() != "night":
        w.act(actor, "wait")
    assert _moon_view(w) is None, \
        "day 1 must fall outside the near-full window, not just off the exact full night"
    assert "watch clouds" not in w.available_actions(actor)
    assert cmd_watch_clouds(w, actor, "") == WATCH_CLOUDS_NIGHT_MSG


def test_moon_line_touches_no_world_state():
    """Same never-break constraint as listen/watch_clouds by day: the moon
    line must not light the room, advance anything, or change state -- it's
    a rarer gate on the exact same no-op, not a new kind of grant."""
    w, actor = fresh()
    run(w, actor, "go out")
    _set_to_full_moon_night(w)
    before = w.to_data()
    cmd_watch_clouds(w, actor, "")
    after = w.to_data()
    assert before == after, "the full-moon line must not change anything, ever"
    assert w.is_dark("yard"), "moonlight must not substitute for a lit lamp"


def test_moon_calm_ack_still_applies_at_the_forest_edge():
    """The calm-axis acknowledgment doesn't care which pool the line came
    from -- a full-moon night at the forest's edge should still count
    toward it, same as any other watch_clouds/listen call there."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    _set_to_full_moon_night(w)
    cmd_watch_clouds(w, actor, "")
    cmd_watch_clouds(w, actor, "")
    third = cmd_watch_clouds(w, actor, "")
    assert CALM_ACK_LINE in third


def test_a_fresh_world_reaches_a_visible_moon_within_a_few_days():
    """BUG: unoffset, a fresh world's first full moon lands on day
    MOON_CYCLE_DAYS (29) -- roughly 23 visits of blank, withdrawn nights
    before there is ever anything to see. MOON_PHASE_OFFSET exists
    specifically so a new lineage doesn't start in that dead zone; this is
    the assertion that makes the fix durable, not just the constant."""
    first_visible = next(d for d in range(1, MOON_CYCLE_DAYS + 1)
                         if _moon_view_on_day(d) is not None)
    assert first_visible <= 7


def test_the_moon_is_visible_on_a_minority_of_nights():
    """The window was widened to fix a dead feature, not to make the moon
    the default night sky -- most nights must still show nothing, or
    "watch clouds" at night stops being a rare thing worth choosing."""
    visible = [d for d in range(1, MOON_CYCLE_DAYS + 1)
              if _moon_view_on_day(d) is not None]
    assert 5 <= len(visible) <= 9


def test_waxing_and_waning_lines_touch_no_world_state():
    """Same never-break constraint as the full-moon line: a wider window
    must not become a lamp-substitute on more nights than before."""
    w, actor = fresh()
    run(w, actor, "go out")
    day = next(d for d in range(1, MOON_CYCLE_DAYS * 2)
              if _moon_view_on_day(d) in ("waxing", "waning"))
    w.time = (day - 1) * DAY_LENGTH + 20
    before = w.to_data()
    cmd_watch_clouds(w, actor, "")
    after = w.to_data()
    assert before == after, "a near-full line must not change anything, ever"
    assert w.is_dark("yard"), "moonlight must not substitute for a lit lamp"


def test_near_full_lines_are_their_own_pool():
    waxing, waning = MOON_VIEW_LINES["waxing"], MOON_VIEW_LINES["waning"]
    assert waxing and waning
    assert not (set(waxing) & set(waning))
    assert not (set(waxing) | set(waning)) & set(MOON_LINES)


# ===========================================================================
# AMBIENT WILDLIFE -- glimpsed, not met. No verb triggers it, no verb
# resolves it, same restraint as the statue: it's texture that exists
# whether or not a hand notices, phase-keyed per room, and it never adds
# anything to a pack (unlike forest_finds, its cousin).
# ===========================================================================
class _AlwaysGlimpse:
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


def test_wildlife_glimpse_is_silent_when_no_pool_matches_the_room_and_phase():
    w, actor = fresh()
    run(w, actor, "go out")            # yard, no "day" entry in WILDLIFE_LINES
    assert w.phase() == "dawn" or w.phase() == "day"
    w.rng = _AlwaysGlimpse()
    room = w.get("yard")
    before = w.to_data()
    wildlife_glimpse(w, room)
    assert w.to_data() == before, "no matching pool means nothing should fire"


def test_wildlife_glimpse_is_silent_when_the_actor_is_elsewhere():
    w, actor = fresh()
    room = w.get("yard")
    w.rng = _AlwaysGlimpse()
    # actor starts in the hut, not the yard
    before = w.to_data()
    wildlife_glimpse(w, room)
    assert w.to_data() == before, "nothing should fire for an empty room"


def test_wildlife_glimpse_announces_a_matching_line_when_present_and_rolled():
    w, actor = fresh()
    run(w, actor, "go out")
    while w.phase() != "dusk":
        w.act(actor, "wait")
    room = w.get("yard")
    w.rng = _AlwaysGlimpse()
    wildlife_glimpse(w, room)
    heard = [m for (m, where) in w.log if where in (None, "yard")]
    assert any(m in WILDLIFE_LINES["yard"]["dusk"] for m in heard)


def test_wildlife_glimpse_never_creates_or_removes_an_entity():
    """The one real difference from forest_finds: this is pure texture, not
    a find -- it must never touch world.entities, only world.log."""
    w, actor = fresh()
    run(w, actor, "go out")
    while w.phase() != "dusk":
        w.act(actor, "wait")
    room = w.get("yard")
    w.rng = _AlwaysGlimpse()
    entities_before = set(w.entities.keys())
    wildlife_glimpse(w, room)
    assert set(w.entities.keys()) == entities_before


# ===========================================================================
# CALM-AXIS SESSION ACKNOWLEDGMENT -- listen and watch_clouds share one
# session-scoped counter at the forest's edge (world.calm_visits), so a hand
# who keeps choosing to pause there gets a single, quiet acknowledgment on the
# third calm act -- never a running status, never a buff, and only at the
# edge, since it's the one calm spot nothing forces a hand to visit.
# ===========================================================================
def test_calm_ack_is_silent_for_the_first_two_calm_acts_at_the_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    assert CALM_ACK_LINE not in cmd_listen(w, actor, "")
    assert CALM_ACK_LINE not in cmd_watch_clouds(w, actor, "")


def test_calm_ack_fires_once_on_the_third_calm_act_and_never_again():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(CALM_ACK_AT - 1):
        cmd_listen(w, actor, "")
    third = cmd_listen(w, actor, "")
    assert CALM_ACK_LINE in third
    fourth = cmd_listen(w, actor, "")
    assert CALM_ACK_LINE not in fourth


def test_calm_ack_counter_is_shared_between_listen_and_watch_clouds():
    """It's tracking chosen presence at the spot, not mastery of one verb --
    mixing the two verbs should still reach the third-act acknowledgment."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    cmd_listen(w, actor, "")
    cmd_watch_clouds(w, actor, "")
    third = cmd_listen(w, actor, "")
    assert CALM_ACK_LINE in third


def test_calm_ack_never_fires_for_watch_clouds_in_the_yard():
    """The yard is constant through-traffic for chores -- counting visits
    there would count the forced loop, not calm, so it's excluded outright."""
    w, actor = fresh()
    result = ""
    for _ in range(CALM_ACK_AT + 2):
        result = cmd_watch_clouds(w, actor, "")
    assert CALM_ACK_LINE not in result
    assert w.calm_visits.get("yard", 0) == 0


def test_calm_visits_is_episodic_like_forest_depth():
    """Session-scoped, not part of the save -- a hand's own sense of having
    lingered doesn't carry over to whoever loads the world next."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    cmd_listen(w, actor, "")
    assert w.calm_visits["forest_edge"] == 1
    assert "calm_visits" not in w.to_data()


# ===========================================================================
# THE CAIRN -- a collective, permanent counterpart to the hut's shelf. Unlike
# the shelf, a stacked stone can never be taken back: it stops being anyone's
# the moment it joins the pile. Height only ever grows, and (unlike
# forest_depth/calm_visits) DOES persist through save/load, since this is
# lineage-scale state, not a single hand's session.
# ===========================================================================
def _give_stone(world, actor):
    return world.add(Entity(world.fresh_id("found"), "a smooth grey stone",
                             "river-worn, a pale band round its middle.",
                             location=actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "ignores"}))


def test_fresh_world_has_an_empty_cairn_at_the_forest_edge():
    w, actor = fresh()
    cairn = w.get(CAIRN_ID)
    assert cairn is not None
    assert cairn.location == "forest_edge"
    assert cairn.attrs["height_cm"] == 0
    assert cairn.description == CAIRN_BANDS[0][1]


def test_stacking_a_stone_requires_being_at_the_forest_edge():
    w, actor = fresh()
    _give_stone(w, actor)
    result = cmd_stack_stone(w, actor, "")
    assert "forest's edge" in result
    assert w.get(CAIRN_ID).attrs["height_cm"] == 0


def test_stacking_a_stone_requires_carrying_one():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    result = cmd_stack_stone(w, actor, "")
    assert "no stone" in result.lower()
    assert w.get(CAIRN_ID).attrs["height_cm"] == 0


def test_stacking_a_non_stone_curio_is_refused():
    """The default arg only ever matches something actually named 'stone' --
    carrying some other curio and typing plain 'stack' must not silently
    consume it."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    pinecone = w.add(Entity(w.fresh_id("found"), "a pinecone",
                             "tight and resinous, one scale broken — the cat "
                             "might bat at it.", location=actor.id,
                             portable=True, attrs={"curio": True, "cat_reaction": "plays"}))
    result = cmd_stack_stone(w, actor, "pinecone")
    assert "no stone" in result.lower()
    assert w.get(pinecone.id) is not None, "a non-stone curio must not be consumed"
    assert w.get(CAIRN_ID).attrs["height_cm"] == 0


def test_stacking_a_stone_consumes_it_and_raises_the_cairns_height():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    stone = _give_stone(w, actor)
    result = cmd_stack_stone(w, actor, "")
    assert w.get(stone.id) is None, "the stone must be consumed, not just moved"
    height = w.get(CAIRN_ID).attrs["height_cm"]
    assert height in CAIRN_GROWTH_CM
    assert w.get(CAIRN_ID).description in result


def test_cairn_description_bands_match_height():
    for threshold, line in CAIRN_BANDS:
        assert _cairn_description(threshold) == line
    just_below = CAIRN_BANDS[1][0] - 1
    assert _cairn_description(just_below) == CAIRN_BANDS[0][1]


def test_cairn_height_and_description_persist_through_save_load_roundtrip():
    """Unlike forest_depth/calm_visits, the cairn is lineage-scale: it must
    survive a reload, the opposite guarantee from the session-scoped state
    right above it in this file."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    _give_stone(w, actor)
    cmd_stack_stone(w, actor, "")
    height_before = w.get(CAIRN_ID).attrs["height_cm"]
    desc_before = w.get(CAIRN_ID).description
    reloaded = World.from_data(w.to_data())
    cairn_after = reloaded.get(CAIRN_ID)
    assert cairn_after.attrs["height_cm"] == height_before
    assert cairn_after.description == desc_before


def test_stack_stone_action_is_offered_only_when_carrying_a_stone_at_the_forest_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    assert "stack stone on cairn" not in w.available_actions(actor)
    _give_stone(w, actor)
    assert "stack stone on cairn" in w.available_actions(actor)


def test_ensure_cairn_is_idempotent_and_does_not_reset_an_existing_cairns_height():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    _give_stone(w, actor)
    cmd_stack_stone(w, actor, "")
    height = w.get(CAIRN_ID).attrs["height_cm"]
    ensure_cairn(w)
    assert w.get(CAIRN_ID).attrs["height_cm"] == height


# ===========================================================================
# 9. FOREST DEPTH SKELETON (FOREST_SPEC.md Stage 1) -- venture/return give a
#    hand something to push into past the edge, tracked by a plain depth
#    counter that lives on the World itself (like world.rng, world.hand_name)
#    rather than as a save-shaped field: the whole point is that POSITION is
#    episodic (gone the moment a session ends) while EFFECTS (a curio found,
#    wood carried out) persist normally through the save, same as ever. No
#    texture, no risk, no new room yet -- forest_edge stays the only room;
#    this stage only proves the plumbing.
# ===========================================================================
def test_fresh_world_starts_at_forest_depth_zero():
    w, actor = fresh()
    assert w.forest_depth == 0


def test_venture_is_only_available_from_the_forest_edge():
    w, actor = fresh()
    result = w.act(actor, "venture")
    assert w.forest_depth == 0, "venture shouldn't work outside the forest's edge"
    assert "forest" in result.lower()


def test_venturing_increases_depth_one_step_at_a_time():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    w.act(actor, "venture")
    assert w.forest_depth == 1
    w.act(actor, "venture")
    assert w.forest_depth == 2


def test_returning_decreases_depth_one_step_at_a_time():
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert w.forest_depth == 3
    w.act(actor, "return")
    assert w.forest_depth == 2


def test_return_never_takes_depth_below_zero():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    assert w.forest_depth == 0
    result = w.act(actor, "return")
    assert w.forest_depth == 0, "return must floor at zero, never go negative"
    assert "edge" in result.lower()


def test_venture_and_return_cost_a_turn_like_any_other_action():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    t0 = w.time
    w.act(actor, "venture")
    assert w.time == t0 + 1, "venture should cost exactly one turn"
    t1 = w.time
    w.act(actor, "return")
    assert w.time == t1 + 1, "return should cost exactly one turn"


def test_venture_is_always_offered_at_the_forest_edge_return_only_once_depth_is_above_zero():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    assert "venture" in w.available_actions(actor)
    assert "return" not in w.available_actions(actor), \
        "no point offering 'return' when there's nowhere to return from"
    w.act(actor, "venture")
    assert "return" in w.available_actions(actor)


def test_forest_depth_does_not_survive_a_save_load_roundtrip():
    """The load-bearing bit of the whole design: forest_depth is a plain
    runtime attribute on World (like world.rng), never written into
    to_data()/read back by from_data() -- so a fresh session always starts
    at the edge, depth 0, no matter how deep a previous session went before
    it saved."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "venture", "venture")
    assert w.forest_depth == 2
    assert "forest_depth" not in w.to_data(), "forest_depth must never be persisted"
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.forest_depth == 0, "a reloaded world must start a fresh visitor at depth 0"


def test_forest_depth_resets_but_committed_effects_survive_a_mid_visit_reload():
    """FOREST_SPEC.md Stage 3's exit criterion, made literal: end a visit
    deep in the forest, reload, and the next visitor starts at the edge with
    no memory of that depth -- while anything actually committed to the save
    while there (here: a found stone, since it's portable and easy to
    trace) is still in the world exactly where it was left."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture",
        "venture", "venture", "venture", "venture", "venture")
    assert w.forest_depth == 8
    stone = _give_stone(w, actor)
    reloaded = World.from_data(json.loads(json.dumps(w.to_data())))
    assert reloaded.forest_depth == 0, "position is episodic"
    found = reloaded.get(stone.id)
    assert found is not None and found.location == actor.id, \
        "an effect committed mid-visit must survive, unlike position"


def test_invariant_checker_passes_with_forest_depth_at_any_value():
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert check_world(w) == []


# ===========================================================================
# 10. FOREST TEXTURE GENERATION (FOREST_SPEC.md Stage 2) -- venture/return
#    now describe where you are with fragments recombined per depth band,
#    instead of one fixed line each, so two visits (or two steps at the same
#    depth) don't read alike. Still no map, still no risk -- this stage only
#    adds prose.
# ===========================================================================
class _Cycle:                                # walk an rng.choice pool in order
    def __init__(self):
        self.i = 0
    def choice(self, seq):
        v = seq[self.i % len(seq)]
        self.i += 1
        return v


def test_forest_bands_are_contiguous_and_gapless_from_depth_one_upward():
    """Every band declared in FOREST_FRAGMENTS must actually be reachable by
    walking depth upward from 1, with no depth landing outside all of them."""
    seen = {_forest_band(d) for d in range(1, 50)}
    assert seen == set(FOREST_FRAGMENTS)


def test_every_band_has_every_pool_populated():
    """No empty pool anywhere -- describe_forest would crash on rng.choice([])."""
    pool_names = {name for band in FOREST_FRAGMENTS.values() for name in band}
    for band_name, band in FOREST_FRAGMENTS.items():
        for pool_name in pool_names:
            assert band.get(pool_name), \
                f"{band_name}'s {pool_name} pool is missing or empty"


def test_describe_forest_is_deterministic_given_a_seeded_rng():
    """Same seed -> same output, so --fuzz stays reproducible."""
    first = describe_forest(3, random.Random(42))
    second = describe_forest(3, random.Random(42))
    assert first == second


def test_describe_forest_varies_across_different_rng_draws():
    rng = _Cycle()
    seen = {describe_forest(1, rng) for _ in range(6)}
    assert len(seen) > 1, "describe_forest should read differently across draws"


def test_venturing_returns_generated_texture_drawn_from_the_near_band():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    result = w.act(actor, "venture")
    assert w.forest_depth == 1
    band = FOREST_FRAGMENTS["near"]
    assert any(frag in result for pool in band.values() for frag in pool), \
        f"depth 1 should draw from the near band: {result!r}"


def test_venturing_deeper_reaches_the_deep_bands_texture():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    result = ""
    for _ in range(6):
        result = w.act(actor, "venture")
    assert w.forest_depth == 6
    band = FOREST_FRAGMENTS["deep"]
    assert any(frag in result for pool in band.values() for frag in pool), \
        f"depth 6 should draw from the deep band: {result!r}"


def test_returning_all_the_way_gives_a_distinct_back_at_the_edge_line():
    """Landing back at depth 0 is its own line, not generated forest-interior
    texture -- there's nothing to describe once you're back at the edge."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "venture")
    result = w.act(actor, "return")
    assert w.forest_depth == 0
    assert "edge" in result.lower()
    all_fragments = [f for band in FOREST_FRAGMENTS.values()
                      for pool in band.values() for f in pool]
    assert not any(f in result for f in all_fragments), \
        f"depth 0 shouldn't show forest-interior texture: {result!r}"


# ===========================================================================
# FOREST_SPEC.md Stage 4 -- getting lost: a bounded, opt-in risk. Below
# SAFE_DEPTH_THRESHOLD, `return` must be airtight-exact no matter what the
# rng says. Beyond it, a small chance can land a hand off-course -- never
# negative, never at the expected depth (or it wouldn't read as off-course).
# ===========================================================================
class _AlwaysOffCourse:
    """Forces the off-course branch every time (random() below any real
    threshold) and always picks the first candidate depth -- used to prove
    the branch can land exactly at 0 (the edge)."""
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


class _AlwaysOffCourseHigh:
    """Same forced trigger, but picks the last (highest) candidate depth --
    used to prove the branch can also land mid-forest, not just at 0."""
    def random(self): return 0.0
    def choice(self, seq): return seq[-1]


def test_return_below_the_safe_depth_threshold_is_always_exact_even_under_a_forced_roll():
    """The safety guarantee for a short, casual dip in: even an rng rigged
    to always trigger the off-course branch must not move the needle at or
    below SAFE_DEPTH_THRESHOLD, because the depth > threshold guard comes
    first."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD):
        w.act(actor, "venture")
    assert w.forest_depth == SAFE_DEPTH_THRESHOLD
    w.rng = _AlwaysOffCourse()
    for expected in range(SAFE_DEPTH_THRESHOLD - 1, -1, -1):
        cmd_return(w, actor, "")
        assert w.forest_depth == expected, \
            "return must stay exact at or below the safe threshold"


def test_return_above_the_safe_depth_threshold_can_land_off_course_at_the_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 1):
        w.act(actor, "venture")
    depth_before = w.forest_depth
    w.rng = _AlwaysOffCourse()
    result = cmd_return(w, actor, "")
    assert w.forest_depth == 0, "the lowest candidate should be picked"
    assert w.forest_depth != depth_before - 1
    assert "edge" in result.lower()


def test_return_above_the_safe_depth_threshold_can_land_off_course_mid_forest():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 2):
        w.act(actor, "venture")
    depth_before = w.forest_depth
    expected = depth_before - 1
    w.rng = _AlwaysOffCourseHigh()
    cmd_return(w, actor, "")
    assert 0 <= w.forest_depth < depth_before
    assert w.forest_depth != expected


def test_return_above_the_safe_depth_threshold_still_usually_stays_exact():
    """The off-course branch is a CHANCE, not a certainty -- an unlucky-for-
    disorientation rng (never rolls below OFF_COURSE_CHANCE) must still
    behave exactly like the pre-Stage-4 return, even deep in the forest."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 3):
        w.act(actor, "venture")
    depth_before = w.forest_depth
    cmd_return(w, actor, "")
    assert w.forest_depth == depth_before - 1


def test_off_course_never_produces_a_negative_or_repeated_depth():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 4):
        w.act(actor, "venture")
    for stub in (_AlwaysOffCourse(), _AlwaysOffCourseHigh()):
        w2, actor2 = fresh()
        w2.rng = _Unlucky()
        run(w2, actor2, "go out", "go forest")
        for _ in range(SAFE_DEPTH_THRESHOLD + 4):
            w2.act(actor2, "venture")
        depth_before = w2.forest_depth
        w2.rng = stub
        cmd_return(w2, actor2, "")
        assert w2.forest_depth >= 0
        assert w2.forest_depth != depth_before - 1


# ===========================================================================
# FOREST_SPEC.md Stage 5 -- trail-marking: a freely-chosen mitigation for
# Stage 4's risk. `mark trail` raises the safe floor for `return`'s
# off-course roll up to the deepest depth marked this session, so a hand
# who marks as it goes can push arbitrarily deep with bounded risk.
# ===========================================================================
def test_marking_below_the_original_threshold_does_nothing_return_still_risks():
    """Marking at depth 2 (below SAFE_DEPTH_THRESHOLD, which already covers
    it) shouldn't raise the floor past what depth 2 already grants -- deeper
    pushes still risk the original threshold, not an artificially lowered one."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture")
    assert w.forest_depth == 2
    result = cmd_mark_trail(w, actor, "")
    assert "mark" in result.lower()
    assert w.forest_mark_depth == 2
    for _ in range(SAFE_DEPTH_THRESHOLD + 2):
        w.act(actor, "venture")
    depth_before = w.forest_depth
    assert depth_before > SAFE_DEPTH_THRESHOLD
    w.rng = _AlwaysOffCourse()
    cmd_return(w, actor, "")
    assert w.forest_depth != depth_before - 1, \
        "still beyond the flat threshold, so off-course should still be reachable"


def test_marking_past_the_threshold_extends_the_safe_zone():
    """The mark raises the safe FLOOR (depth > safe_to triggers off-course),
    it doesn't create a magic corridor for ground gained since the last
    mark -- returning FROM the marked depth itself is exact, even forced
    off-course, precisely because that depth is no longer > the (now
    raised) safe floor. Without the mark this same depth would have been
    well past SAFE_DEPTH_THRESHOLD and at real risk."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 3):
        w.act(actor, "venture")
    mark_depth = w.forest_depth
    assert mark_depth > SAFE_DEPTH_THRESHOLD
    cmd_mark_trail(w, actor, "")
    assert w.forest_mark_depth == mark_depth
    w.rng = _AlwaysOffCourse()
    cmd_return(w, actor, "")
    assert w.forest_depth == mark_depth - 1, \
        "returning from the marked depth itself should be exact, even forced off-course"


def test_marking_requires_being_at_the_forest_edge():
    w, actor = fresh()
    result = cmd_mark_trail(w, actor, "")
    assert "forest's edge" in result
    assert w.forest_mark_depth == 0


def test_marking_at_the_edge_itself_is_refused():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    result = cmd_mark_trail(w, actor, "")
    assert "nothing to mark" in result.lower()
    assert w.forest_mark_depth == 0


def test_marking_never_lowers_an_existing_deeper_mark():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture",
        "venture", "venture")
    cmd_mark_trail(w, actor, "")
    assert w.forest_mark_depth == 5
    w.act(actor, "return")
    assert w.forest_depth == 4
    result = cmd_mark_trail(w, actor, "")
    assert "already marked" in result.lower()
    assert w.forest_mark_depth == 5, "marking shallower must not lower an existing mark"


def test_forest_mark_depth_does_not_survive_a_save_load_roundtrip():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture", "venture")
    cmd_mark_trail(w, actor, "")
    assert w.forest_mark_depth == 4
    assert "forest_mark_depth" not in w.to_data()
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.forest_mark_depth == 0


def test_mark_trail_costs_a_turn_through_the_normal_dispatch():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture")
    t0 = w.time
    w.act(actor, "mark trail")
    assert w.time == t0 + 1


def test_mark_trail_is_offered_only_at_the_forest_edge_past_depth_zero_and_not_yet_marked():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out")
    assert "mark trail" not in w.available_actions(actor)
    run(w, actor, "go forest")
    assert "mark trail" not in w.available_actions(actor), "nothing to mark at depth 0"
    w.act(actor, "venture")
    assert "mark trail" in w.available_actions(actor)
    w.act(actor, "mark trail")
    assert "mark trail" not in w.available_actions(actor), \
        "already marked at the current depth -- offering it again would be a no-op"


# ===========================================================================
# FOREST_SPEC.md Stage 6 -- ambient, unscripted texture. Layered on top of
# whatever describe_forest already returned, on any venture/return
# (including the Stage 4 off-course branch), never in place of it, and
# never referenced by any verb.
# ===========================================================================
class _AlwaysAmbient:
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


def test_forest_ambient_is_deterministic_given_a_seeded_rng():
    import random as random_module
    r1, r2 = random_module.Random(7), random_module.Random(7)
    assert _forest_ambient(r1) == _forest_ambient(r2)


def test_forest_ambient_returns_empty_string_most_of_the_time():
    assert _forest_ambient(_Unlucky()) == ""


def test_forest_ambient_draws_from_its_own_pool_when_it_fires():
    assert _forest_ambient(_AlwaysAmbient()).strip() in FOREST_AMBIENT


def test_venture_can_carry_an_ambient_line():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    w.rng = _AlwaysAmbient()
    result = cmd_venture(w, actor, "")
    assert any(line in result for line in FOREST_AMBIENT)


def test_venture_omits_ambient_when_the_roll_misses():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    result = cmd_venture(w, actor, "")
    assert not any(line in result for line in FOREST_AMBIENT)


def test_return_can_carry_an_ambient_line_on_the_normal_branch():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "venture")
    w.rng = _AlwaysAmbient()
    result = cmd_return(w, actor, "")
    assert any(line in result for line in FOREST_AMBIENT)


def test_return_to_the_edge_never_carries_ambient_text():
    """Depth 0 has its own fixed line, same reasoning describe_forest
    already applies -- nothing forest-interior to layer ambience onto."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture")
    w.rng = _AlwaysAmbient()
    result = cmd_return(w, actor, "")
    assert not any(line in result for line in FOREST_AMBIENT)


def test_ambient_can_co_occur_with_an_off_course_return_without_crashing():
    """The explicit FOREST_SPEC.md requirement: ambient lines must never
    crash when they land on the same turn as a Stage 4 off-course event.
    _AlwaysOffCourse forces random() to 0.0 too, so this also exercises the
    co-occurrence for free, not just the crash-safety."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(SAFE_DEPTH_THRESHOLD + 2):
        w.act(actor, "venture")
    w.rng = _AlwaysOffCourse()
    result = cmd_return(w, actor, "")   # must not raise
    assert isinstance(result, str) and result


# ===========================================================================
# FOREST_SPEC.md Stage 7 -- the statue. Randomly discovered past
# STATUE_MIN_DEPTH, mechanically inert: `wish` logs and confirms nothing,
# ever. statue_found_this_session is session-scoped (like forest_depth),
# so "found" doesn't survive a reload, but the statue entity itself
# (created lazily on first wish) persists normally once it exists.
# ===========================================================================
class _AlwaysDiscover:
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


def test_statue_discovery_never_fires_below_statue_min_depth():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH):
        result = w.act(actor, "venture")
        if w.forest_depth < STATUE_MIN_DEPTH:
            assert not w.statue_found_this_session
            assert "stone figure" not in result


def test_statue_can_be_discovered_past_the_min_depth():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    assert not w.statue_found_this_session
    w.rng = _AlwaysDiscover()
    result = w.act(actor, "venture")
    assert w.forest_depth >= STATUE_MIN_DEPTH
    assert w.statue_found_this_session
    assert "stone figure" in result


def test_statue_is_not_rediscovered_once_found_this_session():
    """No flickering in and out of existence on repeated ventures -- once
    found, later discovery text should not appear again."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysDiscover()
    w.act(actor, "venture")
    assert w.statue_found_this_session
    result = w.act(actor, "venture")
    assert "stone figure" not in result


def test_wish_requires_the_statue_to_have_been_found_this_session():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH):
        w.act(actor, "venture")
    assert not w.statue_found_this_session
    result = cmd_wish(w, actor, "a warm winter")
    assert "nothing here" in result.lower()


def test_wish_requires_currently_being_deep_enough():
    """Found once doesn't mean wishable from the edge -- the hand has to
    currently be at STATUE_MIN_DEPTH or beyond again."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysDiscover()
    w.act(actor, "venture")
    assert w.statue_found_this_session
    w.rng = _Unlucky()
    run(w, actor, "return", "return", "return", "return", "return", "return")
    assert w.forest_depth < STATUE_MIN_DEPTH
    result = cmd_wish(w, actor, "a warm winter")
    assert "nothing here" in result.lower()


def test_wish_works_again_at_a_different_depth_once_found():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysDiscover()
    w.act(actor, "venture")
    found_depth = w.forest_depth
    w.rng = _Unlucky()
    w.act(actor, "venture")   # one step deeper -- not the exact found depth
    assert w.forest_depth != found_depth
    assert w.forest_depth >= STATUE_MIN_DEPTH
    result = cmd_wish(w, actor, "a warm winter")
    assert result == STATUE_WISH_LINE


def test_wish_requires_actual_wish_text():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    result = cmd_wish(w, actor, "")
    assert "wish for what" in result.lower()


def test_wish_logs_the_wish_and_returns_a_fixed_line_with_no_confirmation():
    w, actor = fresh()
    w.hand_name = "Rin"
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    result = cmd_wish(w, actor, "a warm winter")
    assert result == STATUE_WISH_LINE
    statue = w.get("statue")
    assert any("a warm winter" in wish for wish in statue.attrs["wishes"])
    assert any("Rin" in wish for wish in statue.attrs["wishes"])


def test_wish_touches_no_state_besides_the_statues_own_wish_log():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    before = w.to_data()
    cmd_wish(w, actor, "a warm winter")
    after = w.to_data()
    before_entities = {e["id"] for e in before["entities"]}
    after_entities = {e["id"] for e in after["entities"]}
    assert after_entities - before_entities == {"statue"}
    before_by_id = {e["id"]: e for e in before["entities"]}
    for e in after["entities"]:
        if e["id"] == "statue":
            continue
        assert e == before_by_id[e["id"]], f"wish changed unrelated entity {e['id']}"


def test_ensure_statue_is_idempotent():
    w, actor = fresh()
    statue1 = ensure_statue(w)
    statue1.attrs["wishes"].append("a wish already logged")
    statue2 = ensure_statue(w)
    assert statue2 is statue1
    assert statue2.attrs["wishes"] == ["a wish already logged"]


def test_statue_found_this_session_does_not_survive_a_save_load_roundtrip():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert w.statue_found_this_session
    assert "statue_found_this_session" not in w.to_data()
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.statue_found_this_session is False


def test_statue_wishes_persist_through_a_save_load_roundtrip():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    cmd_wish(w, actor, "a warm winter")
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    statue2 = w2.get("statue")
    assert statue2 is not None
    assert any("a warm winter" in wish for wish in statue2.attrs["wishes"])
    assert w2.statue_found_this_session is False, "position/session facts still reset"


def test_wish_action_is_offered_only_when_the_statue_is_reachable():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    assert not any(a.startswith("wish ") for a in w.available_actions(actor))
    w.rng = _AlwaysDiscover()
    w.act(actor, "venture")
    assert any(a.startswith("wish ") for a in w.available_actions(actor))


# ===========================================================================
# BUG WE HIT: actor.location never actually leaves "forest_edge" at any
# depth (venturing is a session-scoped counter, not a real room change), so
# a flat world.contents(room.id) made two forest_edge fixtures reachable
# from everywhere in the whole forest, not just where they belong -- worst
# of all, the statue appeared in the room description PERMANENTLY once
# found, even back at depth 0, flatly contradicting its own "never a
# standing fixture" design. Fixed by _room_here: the cairn only appears
# (and is only reachable via find_visible) at depth 0; the statue only
# appears when _statue_reachable holds, the same gate `wish` already uses.
# ===========================================================================
def test_cairn_is_not_visible_or_reachable_below_the_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture")
    assert not any("cairn" in a for a in w.available_actions(actor))
    result = w.act(actor, "look cairn")
    assert "don't see" in result.lower()


def test_cairn_is_visible_and_reachable_again_back_at_the_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture", "return")
    assert w.forest_depth == 0
    assert any("cairn" in a for a in w.available_actions(actor))
    result = w.act(actor, "look cairn")
    assert "cairn" in result.lower() or "flat stone" in result.lower()


def test_stack_stone_refuses_below_the_edge_even_though_still_at_forest_edge():
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest", "venture")
    _add_curio(w, actor, "a smooth grey stone")
    result = cmd_stack_stone(w, actor, "")
    assert "too deep" in result.lower()


def test_statue_never_appears_in_the_room_listing_back_at_the_edge():
    """The actual bug: once found, the statue used to show up in the
    standing room description forever after, even at depth 0."""
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert w.statue_found_this_session
    cmd_wish(w, actor, "a warm winter")   # materializes the statue entity
    w.rng = _Unlucky()
    run(w, actor, "return", "return", "return")
    assert w.forest_depth == 0
    result = w.act(actor, "look")
    assert "stone figure" not in result
    assert not any("statue" in a for a in w.available_actions(actor))


def test_statue_is_not_listed_or_wishable_at_a_shallow_depth_even_once_found():
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    assert w.statue_found_this_session
    cmd_wish(w, actor, "a warm winter")
    w.rng = _Unlucky()
    w.act(actor, "return")   # depth 2 -- found this session, but too shallow now
    assert w.forest_depth < STATUE_MIN_DEPTH
    assert not any("statue" in a for a in w.available_actions(actor))
    result = w.act(actor, "look")
    assert "stone figure" not in result


def test_no_forest_fragment_reads_as_a_refusal_marker():
    """The LLM driver's _looks_like_refusal scans for substrings like "can't"
    to tell a real refusal from a landed action -- a forest fragment that
    happens to contain one would make a successful venture misread as a
    no-op in the visit's grounded `did` list. Guard it here, and every other
    generated-text pool that can land in a driver result string alongside
    it -- the moon lines, off-course lines, and wildlife glimpses are all
    new enough not to have been checked against this yet."""
    from drivers import _REFUSAL_MARKERS
    all_fragments = [frag for band in FOREST_FRAGMENTS.values()
                      for pool in band.values() for frag in pool]
    all_fragments += list(MOON_LINES) + list(OFF_COURSE_LINES) + list(FOREST_AMBIENT)
    all_fragments += list(MOON_VIEW_LINES["waxing"]) + list(MOON_VIEW_LINES["waning"])
    all_fragments += [look for _, look, _ in BLOOM_KINDS]
    all_fragments += [line for _, line in BLOOM_BANDS]
    all_fragments += [STATUE_DISCOVERY_TEXT, STATUE_WISH_LINE]
    all_fragments += [line for room in WILDLIFE_LINES.values()
                       for pool in room.values() for line in pool]
    for frag in all_fragments:
        low = frag.lower()
        assert not any(m in low for m in _REFUSAL_MARKERS), \
            f"fragment reads as a refusal marker: {frag!r}"


# ===========================================================================
# 11. EXIT ALIASES -- a hand's own wording for an exit doesn't always match
#    the short key a room is keyed by; "go inside" is a natural way to say
#    "go in" near the hut.
# ===========================================================================
def test_go_inside_acts_the_same_as_go_in_near_the_hut():
    w, actor = fresh()
    run(w, actor, "go out")
    assert actor.location == "yard"
    result = w.act(actor, "go inside")
    assert actor.location == "hut"
    assert "HUT" in result.upper()


def test_inside_only_works_where_an_in_exit_actually_exists():
    """The alias resolves to the canonical "in" key before room.exits is
    consulted, so it does nothing (rather than teleporting) anywhere "in"
    isn't a real exit -- the hut itself has no "in" exit of its own."""
    w, actor = fresh()
    result = w.act(actor, "go inside")
    assert actor.location == "hut", "shouldn't move at all -- no 'in' exit from the hut"
    assert "can't go" in result.lower()


# ===========================================================================
# 12. LOOK ACTIONS ALIAS -- an LLM hand playing the world reached for
#    "look actions" more than once (observed on Haiku 4.5, which has no
#    thinking to reason its way out of it), presumably pattern-matching
#    "look <thing>" onto the word "actions" from its own system prompt.
#    "actions" is already a real, free verb (cmd_actions) -- rather than
#    fight the guess, honor it: "look actions" behaves exactly like
#    "actions".
# ===========================================================================
def test_look_actions_behaves_the_same_as_actions():
    w, actor = fresh()
    before = w.time
    result = w.act(actor, "look actions")
    assert w.time == before, "the alias must stay free, like actions itself"
    assert "Available actions:" in result and "go out" in result


def test_look_actions_is_case_and_whitespace_insensitive():
    w, actor = fresh()
    assert "Available actions:" in w.act(actor, "look Actions")
    assert "Available actions:" in w.act(actor, "look   actions  ")


def test_look_still_examines_a_real_thing_named_actions_free_of_the_alias():
    """The alias is a narrow special-case on the literal argument "actions"
    -- it must not swallow a legitimate look at some other target that
    merely contains that substring."""
    w, actor = fresh()
    result = w.act(actor, "look actionsy")
    assert "Available actions:" not in result
    assert "you don't see any" in result.lower()


# ===========================================================================
# 13. THE MYSTERY SEED -- a seed found at the forest's edge, planted in the
#     yard, that blooms on its own multi-visit schedule and opens for
#     whoever happens to be around when it does. The first thing where one
#     hand changes what a LATER hand can do, not just what they can read.
# ===========================================================================
def _seed_count(w):
    return len([e for e in w.entities.values() if e.attrs.get("seed")])


def test_a_seed_turns_up_at_the_forest_edge_when_none_exists():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    seed = _seed_in_world(w)
    assert seed is not None
    assert seed.name == SEED_NAME
    assert seed.location == "forest_edge", \
        "the seed should be on the ground, not pocketed automatically"


def test_no_second_seed_while_one_is_carried_shelved_or_growing():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    assert _seed_count(w) == 1

    # carried: still at the edge, holding the only seed -- no second appears
    run(w, actor, "take seed")
    w.act(actor, "wait")
    assert _seed_count(w) == 1

    # shelved: off at the hut, not even carried -- still no second
    run(w, actor, "go yard", "go in", "place seed on shelf")
    run(w, actor, "go out", "go forest")
    w.act(actor, "wait")
    assert _seed_count(w) == 1

    # growing: planted and off the board entirely -- still no second
    run(w, actor, "go yard", "go in", "take seed", "go out", "plant seed")
    assert _seed_count(w) == 0
    assert _mystery_plant(w) is not None
    run(w, actor, "go forest")
    w.act(actor, "wait")
    assert _seed_count(w) == 0


def test_planting_a_seed_does_not_touch_the_vegetable_patch():
    """The one-crop-at-a-time rule belongs to the patch alone -- a seed
    planted in the yard must never compete with, consume, or otherwise
    touch it."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato")
    patch = w.get("patch")
    crop_id_before = w.contents(patch.id)[0].id
    run(w, actor, "go forest", "take seed", "go yard", "plant seed")
    assert [e.id for e in w.contents(patch.id)] == [crop_id_before], \
        "the seed must never enter or disturb the patch"
    assert _mystery_plant(w) is not None


def test_the_seed_cannot_be_planted_in_the_patch_itself():
    """Planting only ever succeeds in the yard at large -- there is no path
    that routes a seed into the patch entity the way a potato does."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "take seed", "go yard")
    from content import _plant_seed
    patch = w.get("patch")
    seed = next(e for e in w.contents(actor.id) if e.attrs.get("seed"))
    _plant_seed(w, actor, seed)
    assert w.contents(patch.id) == [], "the patch must stay empty"
    assert _mystery_plant(w).location == "yard"


def test_a_planted_seed_ignores_water_entirely():
    """Deliberately NOT `growing`'s water-boost path -- see blooming's
    docstring. cmd_water only ever targets a crop inside the patch, so a
    freestanding mystery plant was never even a reachable target for it;
    this pins the observable growth rate directly (always +1 per tick)
    rather than just the missing code path."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "take seed", "go yard", "plant seed")
    plant = _mystery_plant(w)
    run(w, actor, "draw water")
    before = plant.attrs["growth"]
    w.act(actor, "water crop")
    after = plant.attrs["growth"]
    assert after == before + 1, "growth must advance by exactly one tick, never boosted"


def test_a_bloom_outlives_a_single_visit():
    """The core design decision, made unbreakable: BLOOM_TICKS must exceed
    a typical visit (~30 turns), or a planter starts seeing their own
    bloom and the whole multi-visit point collapses into a slow potato."""
    assert BLOOM_TICKS > 30


def test_what_it_becomes_is_fixed_at_planting_and_hidden_until_it_opens():
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "take seed", "go yard", "plant seed")
    plant = _mystery_plant(w)
    assert plant.attrs.get("bloom_name") in [k[0] for k in BLOOM_KINDS]
    assert not plant.attrs.get("ready")
    assert plant.attrs["bloom_name"] not in plant.description
    assert plant.name != plant.attrs["bloom_name"]


def test_a_bloom_becomes_takeable_and_shelvable():
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "take seed", "go yard", "plant seed")
    plant = _mystery_plant(w)
    plant.attrs["growth"] = BLOOM_TICKS - 1
    w.act(actor, "wait")
    assert plant.attrs["ready"]
    assert plant.portable
    assert plant.attrs["curio"]
    assert plant.name in [k[0] for k in BLOOM_KINDS]
    w.act(actor, f"take {plant.name}")
    assert plant.location == actor.id
    run(w, actor, "go in")
    w.act(actor, f"place {plant.name} on shelf")
    assert plant.location == "shelf"


def test_planting_a_seed_touches_no_maintenance_resource():
    """Same invariant as give/place: planting is a real, deliberate state
    change (a seed becomes a growing plant), but must never touch a
    maintenance resource or advance the clock itself -- the tick that
    grows crops/fire/hunger belongs to world.act's dispatcher, not to any
    individual handler. Calling the handler directly isolates that from
    the ambient ticking any non-free verb also triggers."""
    from content import _plant_seed
    w, actor = fresh()
    run(w, actor, "go out", "go forest", "take seed", "go yard")
    cat = w.get("cat")
    cat.location = actor.location
    cat.attrs["hunger"] = 5
    hearth = w.get("hearth")
    hearth.attrs["lit"] = True
    hearth.attrs["fuel"] = 10
    actor.attrs["wood"] = 4
    w.get("bucket").attrs["water"] = 2
    time_before, day_before = w.time, w.day()

    seed = next(e for e in w.contents(actor.id) if e.attrs.get("seed"))
    _plant_seed(w, actor, seed)

    assert cat.attrs["hunger"] == 5, "planting must not touch cat hunger"
    assert w.get("bucket").attrs["water"] == 2, "must not touch the bucket"
    assert actor.attrs["wood"] == 4, "must not touch firewood"
    assert hearth.attrs["lit"] and hearth.attrs["fuel"] == 10, "must not touch fire-life"
    assert w.time == time_before, "the handler itself must not advance the clock"
    assert w.day() == day_before


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
