"""
test_forest_edge.py -- tests for the forest's edge as a room: the yard
exit, curio/wood finds while lingering, listen/watch-clouds at the edge,
the cairn (stone-stacking, height bands, permanence), the moon, wildlife
glimpses, and the forest depth skeleton (venture/return/mark-trail's
session-scoped counter, before the deeper texture-generation layer on top
of it). Split out of test_content.py -- see docs/ARCHITECTURE.md's note
on that split. Forest texture generation (the venture/return prose itself,
the statue) lives in test_forest_venture.py.

Run it either way:
    python3 -m pytest test_forest_edge.py -v   # if you have pytest
    python3 test_forest_edge.py                 # if you don't (built-in runner)
"""

import json
import random
import re

from world import World, Entity, check_world, DAY_LENGTH
from content import (
    WOOD_PER_GATHER,
    FOREST_FIND_CHANCE, _STRAY_WOOD_SHARE, WOOD_PER_STRAY_FIND,
    LISTEN_LINES, cmd_listen,
    WATCH_CLOUD_LINES, WATCH_CLOUDS_NIGHT_MSG, cmd_watch_clouds,
    CALM_ACK_AT, CALM_ACK_LINE,
    MOON_CYCLE_DAYS, MOON_LINES, _is_full_moon,
    MOON_PHASE_OFFSET, MOON_VIEW_LINES, _moon_view,
    WILDLIFE_LINES, wildlife_glimpse,
)
from curios import (
    FOUND_ITEMS, _found_description,
    CAIRN_ID, CAIRN_GROWTH_CM, CAIRN_BANDS, _cairn_description,
    ensure_cairn, cmd_stack_stone,
)
from _test_helpers import fresh, run, _Lucky, _Unlucky


# ===========================================================================
# 1. THE FOREST'S EDGE -- v1: a doorway, not the forest. One new room off the
#    yard that turns up curios far more reliably than a yard gather, so a
#    hand that wants one can go get one instead of waiting on an RNG roll
#    mid-chore. No statue, no herb, no wood-relocation, no going deeper --
#    the dark ahead stays description-only.
# ===========================================================================
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
    assert found[0].description == _found_description(look_line, reaction, name)
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


def test_any_stone_added_at_all_moves_the_cairn_off_its_unstarted_text():
    """BUG WE HIT: band 0's text claims a cairn hasn't been started yet, but
    stayed up even after real stones landed, since a single stone (2-5cm)
    can't clear the old first threshold (10cm) alone. height_cm is always
    at least CAIRN_GROWTH_CM's floor after one stone, so even the smallest
    possible single stack must read as no-longer-band-0."""
    assert _cairn_description(min(CAIRN_GROWTH_CM)) != CAIRN_BANDS[0][1]


def test_stacking_a_single_stone_updates_the_cairns_description_immediately():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    _give_stone(w, actor)
    result = cmd_stack_stone(w, actor, "")
    cairn = w.get(CAIRN_ID)
    assert cairn.description != CAIRN_BANDS[0][1]
    assert cairn.description in result


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


def test_ensure_cairn_resyncs_a_stale_description_to_the_current_bands():
    """BUG WE HIT: a cairn's description is only recomputed by cmd_stack_stone
    -- a save loaded after CAIRN_BANDS changed kept showing whatever text was
    current at the last real stacking, not what the height actually maps to
    now, until another stone happened to be added. ensure_cairn (called on
    every load) must resync it instead of leaving stale text sitting there."""
    w, actor = fresh()
    cairn = w.get(CAIRN_ID) or ensure_cairn(w)
    cairn.attrs["height_cm"] = 8
    cairn.description = "some stale description from an old band definition"
    ensure_cairn(w)
    assert w.get(CAIRN_ID).description == _cairn_description(8)


# ===========================================================================
# 2. FOREST DEPTH SKELETON (FOREST_SPEC.md Stage 1) -- venture/return give a
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
