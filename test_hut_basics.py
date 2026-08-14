"""
test_hut_basics.py -- tests for the hut/yard core loop: the gameplay
smoke test, the well/bucket/watering chain, the tin lamp, the potato
economy, the self-documenting reference, and small parser conveniences
(exit aliases, "look actions", actor hunger legibility). Split out of
test_content.py -- see docs/ARCHITECTURE.md's note on that split for why
and how the pieces were grouped. The forest, the found-curio economy, the
journal/mystery seed, and the riverbank each have their own test file now.

Run it either way:
    python3 -m pytest test_hut_basics.py -v   # if you have pytest
    python3 test_hut_basics.py                 # if you don't (built-in runner)
"""

import json
import re

from world import World, Entity
from content import (
    VERBS, BEHAVIORS, generate_reference, _crop_in, BUCKET_CAPACITY,
    bucket_state,
    LAMP_FUEL_START, LAMP_LOW_FUEL,
    PATCH_VOLUNTEER_TURNS,
    WAIT_DARK_HUT_LINES, WAIT_DARK_CAT_LINE, _wait_dark_lines,
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
# 3. THE TIN LAMP -- a re-kindleable portable light, replacing the one-shot
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
# 4. THE POTATO ECONOMY -- self-healing ground, a last-potato beat, and an
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
# 6. EXIT ALIASES -- a hand's own wording for an exit doesn't always match
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
# 7. LOOK ACTIONS ALIAS -- an LLM hand playing the world reached for
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
# 7b. ACTOR HUNGER LEGIBILITY -- your own hunger used to be silent on every
#     turn's primary view (only cmd_inventory said anything, and only if a
#     hand thought to check), while the cat's hunger is loud on `look` and
#     the tending note both. That silence is why hands kept feeding every
#     spare potato to the cat and starving themselves. "look" now carries
#     the same "You feel X." line cmd_inventory always has, via the one
#     shared helper (content_common.actor_hunger_line) both call through
#     _carried_line -- so the two views can't drift apart again.
# ===========================================================================
def test_look_surfaces_actor_hunger_when_hungry():
    from content_common import ACTOR_HUNGER_HUNGRY
    w, actor = fresh()
    actor.attrs["hunger"] = ACTOR_HUNGER_HUNGRY - 1
    assert "You feel hungry." in w.act(actor, "look")


def test_look_in_the_dark_still_surfaces_actor_hunger():
    from content_common import ACTOR_HUNGER_HUNGRY
    w, actor = fresh()
    while w.phase() != "night":
        w.act(actor, "wait")
    actor.attrs["hunger"] = ACTOR_HUNGER_HUNGRY - 1
    assert "You feel hungry." in w.act(actor, "look")


def test_inventory_and_look_report_the_same_hunger_mood():
    from content_common import ACTOR_HUNGER_HUNGRY
    w, actor = fresh()
    actor.attrs["hunger"] = ACTOR_HUNGER_HUNGRY - 1
    inv = w.act(actor, "inventory")
    look = w.act(actor, "look")
    assert "You feel hungry." in inv and "You feel hungry." in look


# BUG WE HIT (real lineage transcript, see sessions/20260808-113503_*): once
# the hunger line above went live, a hand arriving at (or near) the cap ate
# a single cooked potato and was STILL told "you're getting hungry" a turn
# or two later -- the meal (food=8) didn't drop hunger below the nag
# threshold (ACTOR_HUNGER_FINE=10), so the now-visible note kept firing and
# the hand cooked and ate three more times chasing it. The relationship
# between the cap, the nag threshold, and one meal's restore is what
# matters, not any single constant in isolation -- pin it directly so a
# future tweak to any one of them can't silently reintroduce the chase.
def test_one_meal_from_the_hunger_cap_clears_the_getting_hungry_note():
    from content_common import ACTOR_HUNGER_CAP, ACTOR_HUNGER_FINE, actor_self_care_note
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in", "light hearth", "cook potato")
    actor.attrs["hunger"] = ACTOR_HUNGER_CAP
    w.act(actor, "eat broiled potato")
    assert actor.attrs["hunger"] < ACTOR_HUNGER_FINE, \
        f"one meal from the cap left hunger at {actor.attrs['hunger']}, still >= the nag threshold"
    assert actor_self_care_note(actor) == "", "the note should be fully clear after one meal from the cap"


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
