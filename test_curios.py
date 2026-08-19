"""
test_curios.py -- tests for the found-curio economy end to end: gathering
wood/firewood (the roll that surfaces a curio in the first place), the
stone-to-cairn legibility hint, give-to-cat and its durable trace, the
hut's curio shelf, curio visual compression in room listings, and the
charm-string (the fourth fate, alongside the shelf/cairn/journal-tuck,
for round found things with a hole or a gap a knot can catch in). Split
out of test_content.py -- see docs/ARCHITECTURE.md's note on that split.

Run it either way:
    python3 -m pytest test_curios.py -v   # if you have pytest
    python3 test_curios.py                 # if you don't (built-in runner)
"""

import json
import random
import re

from world import World, Entity
from content import (
    WOOD_PER_GATHER, HEARTH_FUEL_START, FUEL_PER_WOOD, HEARTH_LOW_FUEL,
    hearth_state, _cook_hint, FOUND_ITEMS, _found_description,
    CAIRN_ID, cmd_stack_stone, STONE_CAIRN_HINT,
    SHELF_CAPACITY, _shelf_description, ensure_shelf,
    BLOOM_KINDS,
    CURIO_GROUP_EXACT_MAX, CURIO_GROUP_SEVERAL_AT, _plural_of,
    _curio_groups, _group_look_summary,
    CHARM_STRING_ID, CHARM_ELIGIBLE_ITEMS, CHARM_CAPACITY, CHARM_BANDS,
    CHARM_STRING_HINT, CHARM_MISSING_TWINE_HINT,
    _charm_string_description, ensure_charm_string, cmd_thread,
)
from _test_helpers import fresh, run, _add_curio, _Unlucky


# ===========================================================================
# 1. FIREWOOD -- forage wood in the yard, feed the hearth, revive a dead fire.
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


def test_lit_hearth_hints_at_cooking_when_a_raw_potato_is_in_hand():
    """BUG WE HIT (see sessions/20260817-213212_thistlewick_day-56_35-turns.md):
    a hand spent something like ten turns re-checking `actions` across yard/
    hut/forest, unable to tell why `cook`/`eat` weren't listed, because
    nothing said the missing piece was simply "stand at a lit hearth holding
    a raw potato." The hint travels with the moment it's true, the same
    legibility principle as the stone's cairn mention and the shelf's
    capacity line."""
    w, actor = fresh()
    w.act(actor, "light hearth")
    hearth = w.get("hearth")
    assert "cook" not in hearth.description.lower(), \
        f"hint shouldn't appear with no raw potato in hand: {hearth.description!r}"

    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                  location=actor.id, portable=True))
    w.act(actor, "wait")
    assert "cook" in hearth.description.lower(), \
        f"hint should appear once a raw potato is in hand: {hearth.description!r}"


def test_cook_hint_disappears_once_the_hearth_or_the_potato_is_gone():
    w, actor = fresh()
    w.act(actor, "light hearth")
    hearth = w.get("hearth")
    raw = w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                        location=actor.id, portable=True))
    w.act(actor, "wait")
    assert "cook" in hearth.description.lower()

    w.act(actor, "drop potato")
    w.act(actor, "wait")
    assert "cook" not in hearth.description.lower(), \
        f"hint should clear once the raw potato leaves the actor's hands: {hearth.description!r}"


def test_cook_hint_ignores_an_already_cooked_potato():
    w, actor = fresh()
    w.act(actor, "light hearth")
    hearth = w.get("hearth")
    w.add(Entity(w.fresh_id("potato"), "broiled potato",
                  "a hot broiled potato, skin blistered and steaming -- ready to eat",
                  location=actor.id, portable=True, attrs={"food": 1}))
    w.act(actor, "wait")
    assert "cook" not in hearth.description.lower(), \
        f"an already-cooked potato shouldn't trigger the cook hint: {hearth.description!r}"


def test_cook_hint_requires_an_unlit_actor_here_check_via_direct_call():
    """Direct call, mirroring how hearth_state's own tests exercise banding
    without a full tick -- an unlit hearth never hints regardless of what's
    carried."""
    w, actor = fresh()
    hearth = w.get("hearth")
    w.add(Entity(w.fresh_id("potato"), "potato", "a firm potato",
                  location=actor.id, portable=True))
    assert _cook_hint(w, hearth) == "", "an unlit hearth must never hint at cooking"


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
    assert found[0].description == _found_description(look_line, reaction, name)
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


# ===========================================================================
# STONE -> CAIRN LEGIBILITY -- `stack stone on cairn` has worked since Stage
# 7, but the cairn was only ever mentioned in the forest-edge room text, a
# cue a hand loses the moment they carry a stone anywhere else. Across a
# long lineage, the shelf filled with duplicate stones and the cairn barely
# grew. Fix: the cue travels with the stone itself, the same way the shelf
# always describes its own held-capacity regardless of where a hand stands
# -- named directly (a real mechanic, not lore), every time, no fatigue
# gating. Found stones only; no other curio has a cairn-equivalent yet.
# ===========================================================================
def test_stone_description_mentions_the_cairn():
    stone_name, look_line, reaction = next(
        t for t in FOUND_ITEMS if t[0] == "a smooth grey stone")
    desc = _found_description(look_line, reaction, stone_name)
    assert "cairn" in desc.lower()
    assert "forest's edge" in desc.lower()


def test_non_stone_found_item_descriptions_do_not_mention_the_cairn():
    for name, look_line, reaction in FOUND_ITEMS:
        if "stone" in name.lower():
            continue
        desc = _found_description(look_line, reaction, name)
        assert "cairn" not in desc.lower(), f"{name!r} wrongly mentions the cairn: {desc!r}"


def test_found_description_omits_the_cairn_hint_when_no_name_is_given():
    """Existing call sites that don't pass a name (or pass one with no
    "stone" in it) must see the exact same text as before this feature --
    the two other tests above pin the wired-in cases directly."""
    assert _found_description("river-worn, a pale band round its middle", "ignores") \
        == "river-worn, a pale band round its middle."


def test_a_found_stone_from_the_forest_names_the_cairn_on_look():
    class Lucky:
        def random(self): return 0.0
        def choice(self, seq):
            return next(t for t in seq if t[0] == "a smooth grey stone") \
                if seq is FOUND_ITEMS else seq[0]
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    w.rng = Lucky()
    w.act(actor, "gather wood")
    stone = next(e for e in w.contents(actor.id) if e.name == "a smooth grey stone")
    assert "cairn" in stone.description.lower()
    assert "cairn" in w.act(actor, f"look {stone.name}").lower()


def test_ensure_shelf_does_not_backfill_the_cairn_hint_onto_a_cat_given_stone():
    """BUG WE HIT: the STONE_CAIRN_HINT backfill matched any found_* entity
    named a stone, with no check for whether it was still an actual,
    reachable curio -- a stone already given to the cat (non-portable, its
    description already rewritten to a cat-trace by cmd_give) got the hint
    appended too, reading as "given to the cat and roundly ignored -- it
    could go on the cairn", which is false: that stone can never be
    stacked, it's stuck in the room forever. Caught via the identical bug
    in CHARM_STRING_HINT (see the test below) -- both backfills need the
    same guard."""
    w, actor = fresh()
    trace = w.add(Entity(w.fresh_id("found"), "a smooth grey stone",
                          "a smooth grey stone, given to the cat and roundly ignored",
                          location="hut", portable=False,
                          attrs={"curio": True, "cat_reaction": "ignores"}))
    ensure_shelf(w)
    assert "cairn" not in w.get(trace.id).description.lower()


def test_ensure_shelf_does_not_backfill_the_charm_hint_onto_a_cat_given_curio():
    """Same bug, same fix, for CHARM_STRING_HINT -- a button or pebble
    already given to the cat must never read as threadable, since it's
    non-portable and can never reach the hut's charm-string again."""
    w, actor = fresh()
    trace = w.add(Entity(w.fresh_id("found"), "a pebble of blue glass",
                          "a pebble of blue glass, given to the cat and roundly ignored",
                          location="hut", portable=False,
                          attrs={"curio": True, "cat_reaction": "ignores"}))
    ensure_shelf(w)
    assert "charm-string" not in w.get(trace.id).description.lower()


def test_ensure_shelf_repairs_a_trace_already_corrupted_before_the_portable_guard():
    """BUG WE HIT (real save file): the two tests above guard against ADDING
    a hint to a cat trace going forward, but a world saved before that guard
    shipped already has the wrong text baked directly into the trace's own
    .description -- "given to the cat and roundly ignored -- it could be
    threaded onto the charm-string in the hut." The guard alone never heals
    that; ensure_shelf must also actively strip a hint it finds on a
    non-portable curio, not just refuse to add a new one."""
    w, actor = fresh()
    stone_trace = w.add(Entity(w.fresh_id("found"), "a smooth grey stone",
        f"a smooth grey stone, given to the cat and roundly ignored — {STONE_CAIRN_HINT}.",
        location="hut", portable=False,
        attrs={"curio": True, "cat_reaction": "ignores"}))
    button_trace = w.add(Entity(w.fresh_id("found"), "a bone button",
        f"a bone button, given to the cat and roundly ignored — {CHARM_STRING_HINT}.",
        location="hut", portable=False,
        attrs={"curio": True, "cat_reaction": "ignores"}))
    ensure_shelf(w)
    assert w.get(stone_trace.id).description == \
        "a smooth grey stone, given to the cat and roundly ignored."
    assert w.get(button_trace.id).description == \
        "a bone button, given to the cat and roundly ignored."


def test_ensure_shelf_repair_is_idempotent_and_leaves_a_live_curios_hint_alone():
    w, actor = fresh()
    live = w.add(Entity(w.fresh_id("found"), "a bone button",
        f"four holes, one thread still knotted through — {CHARM_STRING_HINT}.",
        location="hut", portable=True,
        attrs={"curio": True, "cat_reaction": "ignores"}))
    ensure_shelf(w)
    ensure_shelf(w)
    assert w.get(live.id).description == \
        f"four holes, one thread still knotted through — {CHARM_STRING_HINT}."


def test_a_bloomed_flower_never_mentions_the_cairn():
    """_found_description is reused to build a bloomed flower's description
    (see `blooming`) -- none of BLOOM_KINDS names a stone, and the cairn
    hint must never leak onto a flower just because both paths share a
    helper."""
    from content import BLOOM_KINDS
    for name, look, reaction in BLOOM_KINDS:
        assert "cairn" not in _found_description(look, reaction, name).lower()


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


def test_taking_one_of_several_same_named_curios_reaches_a_still_available_copy():
    """BUG WE HIT: with one stone already carried and more of the same name
    left on the shelf, `take a smooth grey stone` again reported "already
    carrying" -- find_visible's default order sorts a carried match ahead of
    any other still-available copy of the same name, and cmd_take never said
    otherwise. `take` must prefer a copy that ISN'T already in hand."""
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()
    desc = _found_description(look_line, reaction)
    run(w, actor, "place knife on shelf")   # ensure the shelf exists
    shelf = w.get("shelf")
    w.add(Entity(w.fresh_id("found"), name, desc, location=shelf.id,
                 portable=True, attrs={"curio": True}))
    w.add(Entity(w.fresh_id("found"), name, desc, location=shelf.id,
                 portable=True, attrs={"curio": True}))
    first = w.act(actor, f"take {name}").splitlines()[0]
    second = w.act(actor, f"take {name}").splitlines()[0]
    assert first == second == "You take the smooth grey stone."
    assert sum(1 for e in w.contents(actor.id) if e.name == name) == 2


def test_several_same_named_curios_collapse_to_one_action_each():
    """A room or a pack holding several curios sharing a name used to list
    "take <name>" (or "look <name>", or "give <name> to <cat>") once per
    physical copy -- three stones meant three identical lines. They're the
    same action regardless of which copy answers it, so only one of each
    should appear."""
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()
    desc = _found_description(look_line, reaction)
    for _ in range(3):
        w.add(Entity(w.fresh_id("found"), name, desc, location="yard",
                     portable=True, attrs={"curio": True}))
    run(w, actor, "go out")
    actions = w.available_actions(actor)
    assert actions.count(f"take {name}") == 1
    assert actions.count(f"look {name}") == 1

    # carrying several of the same curio must likewise offer "give ... to
    # cat" only once
    w2, actor2 = fresh()
    for _ in range(3):
        w2.add(Entity(w2.fresh_id("found"), name, desc, location=actor2.id,
                      portable=True, attrs={"curio": True}))
    cat_name = w2.get("cat").name
    give_actions = w2.available_actions(actor2)
    assert give_actions.count(f"give {name} to {cat_name}") == 1


def test_dropping_a_found_curio_does_not_double_the_article():
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()
    desc = _found_description(look_line, reaction)
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    result = w.act(actor, f"drop {name}").splitlines()[0]
    assert result == "You set down the smooth grey stone.", f"double article: {result!r}"


def test_a_dropped_curio_names_itself_in_the_room_listing():
    """BUG WE HIT: a dropped curio's bare look_line ("sea-frosted, edges
    gone soft.") showed up alone in the room listing, with no indication of
    what it even was -- look_line is meant to stand on its own only for
    `look <item>`, where the name is already implied by having typed it."""
    w, actor = fresh()
    name, look_line, reaction = _stone_tuple()   # "a smooth grey stone"
    desc = _found_description(look_line, reaction)
    w.add(Entity(w.fresh_id("found"), name, desc,
                 location=actor.id, portable=True, attrs={"curio": True}))
    w.act(actor, f"drop {name}")
    assert f"- {name}, {look_line}" in w.act(actor, "look")


def test_a_curio_given_to_the_cat_does_not_double_its_name_in_the_room_listing():
    """The give-to-cat trace already names itself ("a pinecone, well-battered
    after a game with the cat") -- prefixing the name again on top of that
    (as a naive curio-flag check would) reads as "a pinecone, a pinecone,
    ..."."""
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "give pinecone to cat")
    listing = w.act(actor, "look")
    assert "a pinecone, well-battered after a game with the cat" in listing
    assert "a pinecone, a pinecone," not in listing


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


def test_taking_a_cat_given_trace_names_the_cat_specifically():
    """`take`'s generic non-portable refusal ("The {thing} won't budge")
    also covers real fixtures (the cairn, the charm-string, shaped clay) --
    for those "won't budge" is simply true. A curio already given to the
    cat is different: it isn't heavy or fixed in place, it's just not
    yours anymore, so it gets its own, more accurate refusal. A curio
    already given to the cat is the one entity that's ever both
    `attrs["curio"]` and non-portable at once -- every other permanent
    fate (the cairn, the charm-string, the journal-tuck) consumes the
    entity outright rather than leaving a claimed trace behind, and the
    mystery seed's bloom flips `curio`/`portable` together in the same
    tick, never separately -- so that combination is a safe, unambiguous
    signal, not a name-based guess."""
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    w.act(actor, "give pinecone to cat")
    result = w.act(actor, "take pinecone")
    assert result.splitlines()[0] == "It's the cat's now, you can't have it."


def test_taking_a_genuine_fixture_still_says_it_wont_budge():
    """The generic refusal must still fire for anything non-portable that
    was never a curio at all -- shaped clay, in this case -- so the
    cat-specific message doesn't leak onto unrelated fixtures."""
    w, actor = fresh()
    w.act(actor, "go out")
    w.act(actor, "go river")
    w.act(actor, "gather clay")
    w.act(actor, "shape clay into a squat dish")
    result = w.act(actor, "take clay squat dish")
    assert result.splitlines()[0] == "The clay squat dish won't budge."


def test_take_prefers_a_real_shelved_curio_over_an_unrelated_cat_given_trace():
    """Same class of bug as test_stack_stone_finds_a_carried_stone_even_when
    _a_same_named_item_lies_in_the_room, and the "already carrying" bug
    documented at the top of cmd_take: find_visible's match order is here +
    carried + displayed, so a cat's trace sitting directly in the room
    shadows a same-named, still-live curio sitting on the shelf, even
    though the shelf item is the one `take` could actually satisfy. `take`
    must prefer a portable, obtainable copy over an inert trace, the same
    "prefer one you can actually get" rule already applied to the
    already-carried case."""
    w, actor = fresh()
    actor.location = "hut"
    w.add(Entity(w.fresh_id("found"), "a pinecone",
                 "a pinecone, well-battered after a game with the cat",
                 location="hut", portable=False,
                 attrs={"curio": True, "cat_reaction": "plays"}))
    shelf = w.get("shelf")
    live = w.add(Entity(w.fresh_id("found"), "a pinecone",
                         "tight and resinous, one scale broken.",
                         location=shelf.id, portable=True,
                         attrs={"curio": True, "cat_reaction": "plays"}))
    result = w.act(actor, "take pinecone")
    assert result.splitlines()[0] == "You take the pinecone."
    assert any(e.id == live.id and e.location == actor.id for e in w.contents(actor.id))


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
# 2. CURIO VISUAL COMPRESSION -- a presentation-only pass over the room
#     listing. Curios are intentionally persistent (nothing decays, nothing
#     is auto-cleared), so a hut that's had many visitors accumulates loose
#     pinecones and feathers without bound -- fine for the world, noisy for
#     the room description. Compression changes only what a hand READS, never
#     what exists: no entity is merged, destroyed, or altered, `take`/`give`/
#     `place` still resolve to one real underlying entity exactly as before,
#     and the exact count is always recoverable via `look <name>`. The one
#     thing compression must never do is erase a curio's own distinct state
#     (see CURIO_VISUAL_COMPRESSION.md's "compress repetition, not
#     character") -- so grouping keys on (name, description), not name
#     alone, and a curio with different text from its neighbors always gets
#     its own line rather than being silently folded into their count.
# ===========================================================================
def test_a_single_loose_curio_renders_exactly_as_before():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone", location="hut")
    listing = w.act(actor, "look")
    assert "a pinecone, tight and resinous, one scale broken — the cat might bat at it." in listing
    assert "pinecones" not in listing, "a single curio must never get plural/count treatment"


def test_two_identical_curios_render_as_a_count_line():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone", location="hut")
    _add_curio(w, actor, "a pinecone", location="hut")
    listing = w.act(actor, "look")
    assert "  - two pinecones" in listing
    assert "tight and resinous" not in listing, "grouped lines drop the repeated description text"


def test_three_and_four_identical_curios_use_exact_count_words():
    for n, word in ((3, "three"), (4, "four")):
        w, actor = fresh()
        for _ in range(n):
            _add_curio(w, actor, "a pinecone", location="hut")
        listing = w.act(actor, "look")
        assert f"  - {word} pinecones" in listing, f"count {n} should read '{word} pinecones': {listing!r}"


def test_curio_group_exact_max_is_where_several_takes_over():
    w, actor = fresh()
    for _ in range(CURIO_GROUP_EXACT_MAX):
        _add_curio(w, actor, "a pinecone", location="hut")
    assert "several" not in w.act(actor, "look"), \
        f"CURIO_GROUP_EXACT_MAX ({CURIO_GROUP_EXACT_MAX}) should still show an exact count"

    w, actor = fresh()
    for _ in range(CURIO_GROUP_SEVERAL_AT):
        _add_curio(w, actor, "a pinecone", location="hut")
    assert "  - several pinecones" in w.act(actor, "look")


def test_compression_never_merges_curios_with_different_descriptions():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone", location="hut")
    _add_curio(w, actor, "a pinecone", location="hut")
    odd_one = _add_curio(w, actor, "a pinecone", location="hut")
    odd_one.description = "a pinecone, well-battered after a game with the cat"
    listing = w.act(actor, "look")
    assert "  - two pinecones" in listing, "the two ordinary ones may still group"
    assert "well-battered after a game with the cat" in listing, \
        "the distinctive one must keep its own line, not vanish into a count of three"
    assert "  - three pinecones" not in listing


def test_room_listing_keeps_organic_ordering_for_a_compressed_group():
    """A group's line appears where its FIRST member was found, not sorted
    to the front or back -- the spec is explicit that compression must not
    turn the room into an alphabetised inventory."""
    w, actor = fresh()
    _add_curio(w, actor, "a bone button", location="hut")
    _add_curio(w, actor, "a pinecone", location="hut")
    _add_curio(w, actor, "a pinecone", location="hut")
    listing = w.act(actor, "look")
    button_idx = listing.index("a bone button")
    pinecones_idx = listing.index("two pinecones")
    assert button_idx < pinecones_idx


def test_compression_does_not_apply_to_carried_curios():
    """Carried duplicates already have their own, older summarisation
    (_carried_names' "potato (2)" style) -- compression is a room-listing
    concern only and must not change that line's wording."""
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone")
    _add_curio(w, actor, "a pinecone")
    result = w.act(actor, "look")
    assert "a pinecone (2)" in result
    assert "two pinecones" not in result


def test_compression_does_not_apply_to_shelved_curios():
    w, actor = fresh()
    for _ in range(3):
        c = _add_curio(w, actor, "a pinecone")
        w.act(actor, f"place {c.name} on shelf")
    shelf_line = w.act(actor, "look shelf")
    assert shelf_line.count("a pinecone") == 3, \
        "the shelf stays individually legible -- it's a curated collection, not clutter"
    assert "three pinecones" not in shelf_line


def _trace(world, name, reaction, location="hut"):
    suffix = ("well-battered after a game with the cat" if reaction == "plays"
              else "given to the cat and roundly ignored")
    return world.add(Entity(world.fresh_id("found"), name, f"{name}, {suffix}",
                             location=location, portable=False,
                             attrs={"curio": True, "cat_reaction": reaction}))


# BUG WE HIT (real observed output): two pinecones separately given to the
# cat produced two IDENTICAL "a pinecone, well-battered after a game with
# the cat" bullets in the room listing -- exactly the clutter compression
# exists to fix, in a lineage-scale field (cat-given traces accumulate
# forever, same as loose finds) this feature's first version had excluded
# outright. The excluding reasoning ("a trace reads as permanent scenery,
# not accumulating clutter") turned out to be simply wrong -- it clutters
# just as visibly. A trace's description already names itself (see
# _room_listing_line), so a compressed trace group keeps that text
# attached instead of collapsing to a bare "two pinecones" the way an
# ordinary find does -- losing "well-battered..." would erase the exact
# character information the give-to-cat feature exists to record.
def test_curio_groups_includes_identical_cat_given_traces():
    w, actor = fresh()
    t1 = _trace(w, "a pinecone", "plays")
    t2 = _trace(w, "a pinecone", "plays")
    groups = _curio_groups(w.contents("hut"))
    matching = [es for _, _, es in groups if t1 in es]
    assert matching and t2 in matching[0] and len(matching[0]) == 2


def test_room_listing_compresses_identical_traces_and_keeps_the_trace_text():
    w, actor = fresh()
    _trace(w, "a pinecone", "plays")
    _trace(w, "a pinecone", "plays")
    listing = w.act(actor, "look")
    assert "  - two pinecones, well-battered after a game with the cat" in listing
    assert listing.count("well-battered after a game with the cat") == 1, \
        "the trace text should appear once, attached to the count -- not twice"


def test_traces_of_different_curios_never_merge_just_because_the_suffix_matches():
    w, actor = fresh()
    _trace(w, "a bone button", "ignores")
    _trace(w, "a curl of birch bark", "ignores")
    listing = w.act(actor, "look")
    assert "a bone button, given to the cat and roundly ignored" in listing
    assert "a curl of birch bark, given to the cat and roundly ignored" in listing
    assert "two " not in listing


def test_look_at_a_compressed_group_reveals_the_exact_count():
    w, actor = fresh()
    for _ in range(7):
        _add_curio(w, actor, "a pinecone", location="hut")
    result = w.act(actor, "look pinecone")
    assert "seven pinecones" in result.lower()
    assert "tight and resinous" in result, "the shared description should still be surfaced"


def test_look_at_a_compressed_trace_group_reveals_the_exact_count():
    """find_visible may resolve "look pinecone" to a non-portable trace
    just as easily as a loose one -- the group summary must fire either
    way, not only when the resolved target happens to still be portable."""
    w, actor = fresh()
    _trace(w, "a pinecone", "plays")
    _trace(w, "a pinecone", "plays")
    result = w.act(actor, "look pinecone")
    assert result == "There are two pinecones here. well-battered after a game with the cat"


def test_look_at_a_mixed_compressed_group_does_not_double_a_traces_own_name():
    """BUG WE HIT (real observed output): "look pinecone" on a compressed
    trace group read "There are two pinecones here. a pinecone,
    well-battered after a game with the cat" -- the name spoken twice,
    because _group_look_summary attached the trace's self-naming
    description as-is. Same fix as _group_count_line: strip the "{name}, "
    prefix a trace's own description always opens with before splicing it
    onto the count sentence."""
    w, actor = fresh()
    for _ in range(6):
        _add_curio(w, actor, "a pinecone", location="hut")
    _trace(w, "a pinecone", "plays")
    result = w.act(actor, "look pinecone")
    assert "a pinecone, well-battered" not in result
    assert "different: well-battered after a game with the cat" in result


def test_look_at_a_compressed_group_with_a_distinctive_member_names_it():
    w, actor = fresh()
    for _ in range(6):
        _add_curio(w, actor, "a pinecone", location="hut")
    odd_one = _add_curio(w, actor, "a pinecone", location="hut")
    odd_one.description = "a pinecone, well-battered after a game with the cat"
    result = w.act(actor, "look pinecone")
    assert "seven pinecones" in result.lower()
    assert "well-battered after a game with the cat" in result
    assert "different" in result.lower() or "ordinary" in result.lower()


def test_look_at_a_single_loose_curio_is_unaffected_by_group_summary():
    w, actor = fresh()
    _add_curio(w, actor, "a pinecone", location="hut")
    result = w.act(actor, "look pinecone")
    assert result == "tight and resinous, one scale broken — the cat might bat at it."
    assert "There are" not in result


def test_taking_one_curio_from_a_compressed_group_updates_the_rendered_count():
    w, actor = fresh()
    for _ in range(3):
        _add_curio(w, actor, "a pinecone", location="hut")
    assert "three pinecones" in w.act(actor, "look")
    w.act(actor, "take pinecone")
    assert "a pinecone" in [e.name for e in w.contents(actor.id)], \
        "take must still resolve to one real entity"
    listing = w.act(actor, "look")
    assert "two pinecones" in listing
    assert "three pinecones" not in listing


def test_compression_touches_no_maintenance_resource():
    """Same invariant as give/place: a purely presentational feature must
    not sneak in a side effect on fire, food, or water."""
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = 5
    hearth = w.get("hearth")
    hearth.attrs["lit"], hearth.attrs["fuel"] = True, 10
    for _ in range(3):
        _add_curio(w, actor, "a pinecone", location="hut")
    w.act(actor, "look")
    assert cat.attrs["hunger"] == 5
    assert hearth.attrs["lit"] and hearth.attrs["fuel"] == 10


def test_plural_of_handles_multi_word_curio_names():
    assert _plural_of("a pinecone") == "pinecones"
    assert _plural_of("a pebble of blue glass") == "pebbles of blue glass"
    assert _plural_of("a knot of bleached twine") == "knots of bleached twine"
    assert _plural_of("a jay's feather") == "jay's feathers"
    assert _plural_of("a smooth grey stone") == "smooth grey stones"


def test_every_found_item_has_a_hand_authored_plural():
    """_plural_of has a naive fallback so it can never crash, but every real
    FOUND_ITEMS entry should be hand-authored -- the fallback existing isn't
    permission to skip one."""
    for name, _, _ in FOUND_ITEMS:
        plural = _plural_of(name)
        assert not plural.startswith("a "), \
            f"{name!r} fell through to the naive fallback: {plural!r}"


# ===========================================================================
# 3. THE CHARM-STRING -- a fourth fate for found things: a wall-mounted,
#     collective object in the hut that hands can thread a button or a
#     glass pebble onto, permanently, using up one twine to do it. Sparse
#     to rich by count, the cairn's opposite in character (decorative
#     variety, not monument height) but its sibling in every other way:
#     collective, one-way, and its own resync-on-load fix.
# ===========================================================================
def _give_button(world, actor):
    return world.add(Entity(world.fresh_id("found"), "a bone button",
                             "four holes, one thread still knotted through.",
                             location=actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "ignores"}))


def _give_pebble(world, actor):
    return world.add(Entity(world.fresh_id("found"), "a pebble of blue glass",
                             "sea-frosted, edges gone soft.",
                             location=actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "ignores"}))


def _give_twine(world, actor):
    return world.add(Entity(world.fresh_id("found"), "a knot of bleached twine",
                             "sun-bleached, knotted twice, frayed at both ends.",
                             location=actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "plays"}))


def test_fresh_world_has_an_empty_charm_string_in_the_hut():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    assert charm is not None
    assert charm.location == "hut"
    assert charm.attrs["count"] == 0
    assert charm.description == CHARM_BANDS[0][1]


def test_threading_requires_being_in_the_hut():
    w, actor = fresh()
    w.act(actor, "go out")
    _give_button(w, actor)
    _give_twine(w, actor)
    result = cmd_thread(w, actor, "bone button on charm-string")
    assert "no charm-string" in result.lower()
    assert w.get(CHARM_STRING_ID).attrs["count"] == 0


def test_threading_with_no_argument_asks_what_to_thread():
    w, actor = fresh()
    result = cmd_thread(w, actor, "")
    assert "thread what" in result.lower()


def test_threading_requires_carrying_the_named_item():
    w, actor = fresh()
    _give_twine(w, actor)
    result = cmd_thread(w, actor, "bone button on charm-string")
    assert "not something you can thread" in result.lower()
    assert w.get(CHARM_STRING_ID).attrs["count"] == 0


def test_threading_a_non_eligible_curio_is_refused():
    """A stone belongs to the cairn, not the charm-string -- carrying one
    and typing thread must not consume it or touch the charm-string."""
    w, actor = fresh()
    _give_twine(w, actor)
    stone = w.add(Entity(w.fresh_id("found"), "a smooth grey stone",
                          "river-worn, a pale band round its middle.",
                          location=actor.id, portable=True,
                          attrs={"curio": True, "cat_reaction": "ignores"}))
    result = cmd_thread(w, actor, "stone on charm-string")
    assert "not something you can thread" in result.lower()
    assert w.get(stone.id) is not None, "a non-eligible curio must not be consumed"
    assert w.get(CHARM_STRING_ID).attrs["count"] == 0


def test_threading_a_pinecone_succeeds():
    """The broken-scale detail in a pinecone's own look_line is exactly the
    kind of gap a knot can catch in -- the same physical logic as a
    button's hole, not just "round like a button" -- so it's eligible too."""
    w, actor = fresh()
    _give_twine(w, actor)
    pinecone = w.add(Entity(w.fresh_id("found"), "a pinecone",
                             "tight and resinous, one scale broken.",
                             location=actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "plays"}))
    result = cmd_thread(w, actor, "pinecone on charm-string")
    assert w.get(pinecone.id) is None, "the pinecone must be consumed"
    assert w.get(CHARM_STRING_ID).attrs["count"] == 1
    assert "pinecone" in result.lower()


def test_threading_without_twine_is_refused_with_no_state_change():
    w, actor = fresh()
    button = _give_button(w, actor)
    result = cmd_thread(w, actor, "bone button on charm-string")
    assert "twine" in result.lower()
    assert w.get(button.id) is not None, "the button must not be consumed without twine"
    assert w.get(CHARM_STRING_ID).attrs["count"] == 0


def test_threading_consumes_the_item_and_the_twine_and_increments_count():
    w, actor = fresh()
    button = _give_button(w, actor)
    twine = _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    assert w.get(button.id) is None, "the button must be consumed, not just moved"
    assert w.get(twine.id) is None, "the twine must be consumed too"
    assert w.get(CHARM_STRING_ID).attrs["count"] == 1


def test_threading_works_without_the_on_charm_string_suffix():
    w, actor = fresh()
    _give_pebble(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "pebble of blue glass")
    assert w.get(CHARM_STRING_ID).attrs["count"] == 1


def test_threading_updates_the_charm_strings_description_immediately():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    result = cmd_thread(w, actor, "bone button on charm-string")
    charm = w.get(CHARM_STRING_ID)
    assert charm.description != CHARM_BANDS[0][1]
    assert charm.description in result


def test_charm_string_description_bands_match_count():
    for threshold, line in CHARM_BANDS:
        assert _charm_string_description(threshold) == line
    just_below = CHARM_BANDS[1][0] - 1
    assert _charm_string_description(just_below) == CHARM_BANDS[0][1]


def test_charm_string_count_and_description_persist_through_save_load_roundtrip():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    count_before = w.get(CHARM_STRING_ID).attrs["count"]
    desc_before = w.get(CHARM_STRING_ID).description
    reloaded = World.from_data(w.to_data())
    charm_after = reloaded.get(CHARM_STRING_ID)
    assert charm_after.attrs["count"] == count_before
    assert charm_after.description == desc_before


def test_thread_action_is_offered_only_with_an_eligible_item_and_twine_in_the_hut():
    w, actor = fresh()
    assert not any(a.startswith("thread ") for a in w.available_actions(actor))
    _give_button(w, actor)
    assert not any(a.startswith("thread ") for a in w.available_actions(actor)), \
        "no twine yet -- threading can't do anything"
    _give_twine(w, actor)
    assert "thread a bone button on charm-string" in w.available_actions(actor)


def test_thread_action_is_not_offered_outside_the_hut():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    w.act(actor, "go out")
    assert not any(a.startswith("thread ") for a in w.available_actions(actor))


def test_look_charm_string_hints_at_missing_twine_when_carrying_an_eligible_curio():
    """An eligible curio in hand with no twine is a half-satisfied recipe --
    `carrying_actions` won't list `thread` at all (see the test above), so
    without this hint the missing ingredient is invisible: a hand can only
    ever discover it by blind-guessing the exact `thread` syntax. Surfaced
    on `look charm-string` instead, reusing cmd_thread's own wording. Checks
    for the specific hint phrase, not just the word "twine" -- the band-0
    description ("a bare length of twine hangs on the wall") already
    contains that word on its own."""
    w, actor = fresh()
    _give_button(w, actor)
    result = w.act(actor, "look charm-string")
    assert CHARM_MISSING_TWINE_HINT in result


def test_look_charm_string_has_no_hint_without_an_eligible_curio_carried():
    w, actor = fresh()
    result = w.act(actor, "look charm-string")
    assert CHARM_MISSING_TWINE_HINT not in result


def test_look_charm_string_has_no_hint_once_twine_is_also_carried():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    result = w.act(actor, "look charm-string")
    assert CHARM_MISSING_TWINE_HINT not in result


def test_look_charm_string_has_no_hint_at_capacity():
    w, actor = fresh()
    w.get(CHARM_STRING_ID).attrs["count"] = CHARM_CAPACITY
    _give_button(w, actor)
    result = w.act(actor, "look charm-string")
    assert CHARM_MISSING_TWINE_HINT not in result


def test_look_charm_at_zero_items_returns_the_same_empty_prose_line():
    """Phase 2: `look charm`/`look charm-string`'s dedicated ASCII view.
    At zero items there's nothing to render, so it must fall back to the
    exact same "bare length of twine" line the room's own prose tier uses
    -- no empty ASCII block, per the original spec."""
    w, actor = fresh()
    result = w.act(actor, "look charm-string")
    assert result.splitlines()[0] == CHARM_BANDS[0][1]


def test_look_charm_renders_an_ascii_strip_after_threading():
    w, actor = fresh()
    _give_button(w, actor)
    _give_button(w, actor)
    _give_pebble(w, actor)
    _give_twine(w, actor)
    _give_twine(w, actor)
    _give_twine(w, actor)
    run(w, actor, "thread bone button on charm-string",
        "thread bone button on charm-string",
        "thread pebble of blue glass on charm-string")
    result = w.act(actor, "look charm-string")
    assert "~~~o~~~o~~~•~~~" in result


def test_look_charm_wraps_at_five_symbols_per_row():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = 12
    charm.attrs["items"] = ["a bone button"] * 12
    result = w.act(actor, "look charm-string")
    rows = [line for line in result.splitlines() if line.startswith("~~~")]
    assert len(rows) == 3
    assert rows[0].count("o") == 5
    assert rows[1].count("o") == 5
    assert rows[2].count("o") == 2


def test_look_charm_glyph_mapping_is_stable_regardless_of_mix():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = 3
    charm.attrs["items"] = ["a pinecone", "a bone button", "a pebble of blue glass"]
    result = w.act(actor, "look charm-string")
    assert "~~~*~~~o~~~•~~~" in result


def test_look_charm_renders_at_capacity_without_error():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = CHARM_CAPACITY
    charm.attrs["items"] = ["a bone button"] * CHARM_CAPACITY
    result = w.act(actor, "look charm-string")
    rows = [line for line in result.splitlines() if line.startswith("~~~")]
    assert len(rows) == CHARM_CAPACITY // 5


def test_charm_items_persist_through_save_load_roundtrip():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    before = w.act(actor, "look charm-string")
    reloaded_world = World.from_data(w.to_data())
    reloaded_actor = reloaded_world.get(actor.id)
    after = reloaded_world.act(reloaded_actor, "look charm-string")
    assert before == after


def test_ensure_charm_string_backfills_unknown_glyphs_for_a_legacy_count():
    """A charm-string threaded before item-tracking existed (or a save
    from before this pass) has a real count but no matching item history
    -- ensure_charm_string must not silently lose that accounting. Padding
    the front with CHARM_UNKNOWN_GLYPH keeps the ASCII view's total glyph
    count matching the count-based prose tier, while being honest that the
    earliest entries' actual type isn't known."""
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = 3
    del charm.attrs["items"]
    ensure_charm_string(w)
    assert len(w.get(CHARM_STRING_ID).attrs["items"]) == 3
    result = w.act(actor, "look charm-string")
    assert "~~~?~~~?~~~?~~~" in result


def test_ensure_charm_string_backfill_is_idempotent():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = 3
    del charm.attrs["items"]
    ensure_charm_string(w)
    ensure_charm_string(w)
    assert len(w.get(CHARM_STRING_ID).attrs["items"]) == 3


def test_charm_string_room_listing_stays_prose_only_even_with_items_threaded():
    """The dedicated `look charm-string` view is a separate, richer look --
    the room's own standing description (entity.description, what a bare
    `look` prints inline) must stay the count-based prose, never the ASCII
    strip, per the original spec's "room listing stays prose-only" rule."""
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    assert w.get(CHARM_STRING_ID).description == CHARM_BANDS[1][1]
    assert "~~~" not in w.get(CHARM_STRING_ID).description


def test_missing_twine_hint_still_appends_alongside_the_ascii_view():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    _give_pebble(w, actor)
    result = w.act(actor, "look charm-string")
    assert "~~~o~~~" in result
    assert CHARM_MISSING_TWINE_HINT in result


def test_charm_string_refuses_at_capacity_and_count_never_exceeds_it():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID)
    charm.attrs["count"] = CHARM_CAPACITY
    _give_button(w, actor)
    _give_twine(w, actor)
    result = cmd_thread(w, actor, "bone button on charm-string")
    assert "full" in result.lower()
    assert w.get(CHARM_STRING_ID).attrs["count"] == CHARM_CAPACITY


def test_thread_action_is_not_offered_once_the_charm_string_is_at_capacity():
    w, actor = fresh()
    w.get(CHARM_STRING_ID).attrs["count"] = CHARM_CAPACITY
    _give_button(w, actor)
    _give_twine(w, actor)
    assert not any(a.startswith("thread ") for a in w.available_actions(actor))


def test_no_way_exists_to_take_anything_back_off_the_charm_string():
    """The charm-string only ever tracks a count -- a threaded item is fully
    consumed (test_threading_consumes...), so there is structurally nothing
    left to `take`. This pins that as a real invariant, not an accident:
    `take charm-string` must fail exactly the way taking a non-portable
    fixture always does."""
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    result = w.act(actor, "take charm-string")
    assert "won't budge" in result.lower() or "no 'charm-string'" in result.lower() \
        or "no 'charm" in result.lower()


def test_ensure_charm_string_is_idempotent_and_does_not_reset_count():
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cmd_thread(w, actor, "bone button on charm-string")
    count = w.get(CHARM_STRING_ID).attrs["count"]
    ensure_charm_string(w)
    assert w.get(CHARM_STRING_ID).attrs["count"] == count


def test_ensure_charm_string_resyncs_a_stale_description_to_current_bands():
    w, actor = fresh()
    charm = w.get(CHARM_STRING_ID) or ensure_charm_string(w)
    charm.attrs["count"] = 3
    charm.description = "some stale description from an old band definition"
    ensure_charm_string(w)
    assert w.get(CHARM_STRING_ID).description == _charm_string_description(3)


def test_eligible_curio_descriptions_mention_the_charm_string():
    for name in CHARM_ELIGIBLE_ITEMS:
        _, look_line, reaction = next(t for t in FOUND_ITEMS if t[0] == name)
        desc = _found_description(look_line, reaction, name)
        assert "charm-string" in desc.lower()


def test_non_eligible_found_item_descriptions_do_not_mention_the_charm_string():
    for name, look_line, reaction in FOUND_ITEMS:
        if name in CHARM_ELIGIBLE_ITEMS:
            continue
        desc = _found_description(look_line, reaction, name)
        assert "charm-string" not in desc.lower(), \
            f"{name!r} wrongly mentions the charm-string: {desc!r}"


def test_ensure_shelf_backfills_the_charm_hint_onto_a_legacy_button():
    w, actor = fresh()
    button = _give_button(w, actor)
    button.description = "four holes, one thread still knotted through."
    ensure_shelf(w)
    assert CHARM_STRING_HINT in w.get(button.id).description


def test_threading_touches_no_other_maintenance_resource():
    """Same invariant, same technique, as
    test_gathering_and_shaping_clay_touch_no_other_maintenance_resource:
    call cmd_thread directly so an unrelated tick can't muddy the result."""
    w, actor = fresh()
    _give_button(w, actor)
    _give_twine(w, actor)
    cat = w.get("cat")
    cat.attrs["hunger"] = 5
    hearth = w.get("hearth")
    hearth.attrs["lit"], hearth.attrs["fuel"] = True, 10
    w.get("bucket").attrs["water"] = 2
    actor.attrs["wood"] = 4

    cmd_thread(w, actor, "bone button on charm-string")

    assert cat.attrs["hunger"] == 5, "threading must not touch cat hunger"
    assert hearth.attrs["lit"] and hearth.attrs["fuel"] == 10, "must not touch fire-life"
    assert w.get("bucket").attrs["water"] == 2, "must not touch the bucket"
    assert actor.attrs["wood"] == 4, "must not touch firewood"


# ---------------------------------------------------------------------------
# Built-in runner, so you don't need pytest installed.
# ---------------------------------------------------------------------------
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
