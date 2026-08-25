"""
test_forest_venture.py -- tests for forest texture generation
(FOREST_SPEC.md Stage 2): venture/return's generated prose by depth band,
off-course chances, ambient lines, the statue's discovery/wish mechanic,
and the moon as seen from deep in the trees. Split out of
test_content.py -- see docs/ARCHITECTURE.md's note on that split. The
forest's-edge room itself and the depth counter it sits on top of live in
test_forest_edge.py.

Run it either way:
    python3 -m pytest test_forest_venture.py -v   # if you have pytest
    python3 test_forest_venture.py                 # if you don't (built-in runner)
"""

import json
import random
import re

from world import World, Entity
from content import (
    LISTEN_LINES, cmd_stack_stone,
    FOREST_FRAGMENTS, _forest_band, describe_forest, cmd_venture, cmd_return, cmd_mark_trail,
    SAFE_DEPTH_THRESHOLD, OFF_COURSE_CHANCE, OFF_COURSE_LINES,
    FOREST_AMBIENT, _forest_ambient,
    STATUE_MIN_DEPTH, STATUE_DISCOVERY_TEXT,
    STATUE_WISH_LINE, STATUE_WISH_HINT, ensure_statue, _statue_reachable, cmd_wish,
    PRESENCE_RULES, PRESENCE_LAST, _room_here,
    MOON_LINES, MOON_VIEW_LINES,
    WILDLIFE_LINES,
    BLOOM_BANDS, BLOOM_KINDS,
    ensure_shelf,
)
from _test_helpers import fresh, run, _add_curio, _Unlucky


# ===========================================================================
# 1. FOREST TEXTURE GENERATION (FOREST_SPEC.md Stage 2) -- venture/return
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


def test_forest_ambient_lines_are_well_formed_sentences():
    """BUG WE HIT, found in real play: FOREST_AMBIENT lines were bare
    lowercase clauses with no trailing period -- styled like FOREST_
    FRAGMENTS, which only get capitalized/punctuated once, after
    describe_forest joins several of them into one line. But
    _forest_ambient's pick is appended directly onto an already-complete,
    period-ended sentence (describe_forest's own line, or the statue's
    discovery text), so a hit read as a run-on: "...toss a coin in a
    fountain. something rustles low in the undergrowth, gone by the time
    you look" -- no capital, no closing period. Pin these to the same
    "complete sentence" convention their siblings already follow
    (LISTEN_LINES, WILDLIFE_LINES, MOON_LINES)."""
    for line in FOREST_AMBIENT:
        assert line[0].isupper(), f"not capitalized: {line!r}"
        assert line.endswith("."), f"missing trailing period: {line!r}"


def test_venture_composes_discovery_and_ambient_as_proper_sentences():
    """The exact real-play scenario: the statue discovery text and an
    ambient line landing on the same venture, back to back."""
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysAmbient()
    result = w.act(actor, "venture")
    assert "stone figure" in result
    assert any(line in result for line in FOREST_AMBIENT)
    assert result.rstrip().endswith(".")
    assert not re.search(r"\.\s+[a-z]", result), \
        f"a sentence boundary reads as a run-on: {result!r}"


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


def test_statue_discovery_starts_on_its_own_paragraph():
    """Real-play ask: the discovery text used to run on directly from
    describe_forest's line with just a space ("...turning to something
    else. Between two trunks..."), reading as one more clause of forest
    texture rather than an actual find. A blank line ahead of it now marks
    it as its own thing."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysDiscover()
    result = w.act(actor, "venture")
    assert "\n\nBetween two trunks" in result


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


def test_leaving_the_forest_without_returning_resets_depth_on_next_entry():
    """BUG: `return` is what actually decrements forest_depth, but "go
    yard" is also a valid exit from forest_edge at any depth -- it skips
    `return`'s off-course risk entirely, and used to skip resetting depth
    too. That left forest_depth stuck deep across the trip to the yard, so
    a later "go forest" showed the fixed, shallow arrival text (this is
    the edge, nothing lurks yet) while the statue's presence rule -- keyed
    only on forest_depth and statue_found_this_session -- still passed,
    surfacing the statue at what reads as a fresh arrival. Leaving via the
    yard exit has to be as final as walking all the way back with
    `return`."""
    w, actor = fresh()
    w.rng = _Unlucky()
    run(w, actor, "go out", "go forest")
    for _ in range(STATUE_MIN_DEPTH - 1):
        w.act(actor, "venture")
    w.rng = _AlwaysDiscover()
    w.act(actor, "venture")
    assert w.statue_found_this_session
    assert w.forest_depth >= STATUE_MIN_DEPTH
    w.rng = _Unlucky()
    run(w, actor, "go yard")
    assert w.forest_depth == 0, "leaving the forest should reset depth even without `return`"
    result = w.act(actor, "go forest")
    assert "stone figure" not in result, \
        "arriving fresh at the edge must not show the statue"


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
    """Discovery itself now creates the statue's record (see cmd_venture --
    a hand has to be able to `look` at it before wishing on it), so by the
    time `wish` runs, the only thing left for it to change is the wish log
    on an already-existing entity -- no entity should be added or removed."""
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    before = w.to_data()
    before_entities = {e["id"] for e in before["entities"]}
    assert "statue" in before_entities, "discovery should have created the statue's record"
    cmd_wish(w, actor, "a warm winter")
    after = w.to_data()
    after_entities = {e["id"] for e in after["entities"]}
    assert after_entities == before_entities, "wish must not add or remove any entity"
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


def test_ensure_statue_backfills_the_wish_hint_onto_a_legacy_statue():
    """Real-play bug: a statue created before STATUE_WISH_HINT existed
    (any lineage where a wish was ever made pre-fix) keeps its old-style
    description forever otherwise -- `look statue` in an ongoing lineage
    kept showing the bare "a weathered stone figure..." with no hint,
    same class of bug ensure_shelf's STONE_CAIRN_HINT backfill already
    guards against for stones. ensure_statue must patch an existing
    statue in place, not just set the hint on newly-created ones."""
    w, actor = fresh()
    statue = ensure_statue(w)
    statue.description = "a weathered stone figure, worn past recognizing, moss thick in its folds"
    assert STATUE_WISH_HINT not in statue.description
    patched = ensure_statue(w)
    assert patched is statue
    assert STATUE_WISH_HINT in patched.description
    assert patched.description.startswith("a weathered stone figure")


def test_ensure_statue_does_not_double_the_hint_when_its_wording_changes():
    """BUG WE HIT, live: STATUE_WISH_HINT's exact wording changed ("a hand
    leaves a wish" -> "someone leaves a wish"), and the old backfill guard
    checked `STATUE_WISH_HINT not in statue.description` -- so every statue
    already carrying the OLD wording (any ongoing lineage) failed that
    check against the new constant and got the NEW wording appended on
    top, doubling the hint: "...folds -- the kind of thing a hand leaves a
    wish with... -- the kind of thing someone leaves a wish with...". The
    backfill guard now checks a fragment stable across that reword instead
    of the live constant itself."""
    w, actor = fresh()
    statue = ensure_statue(w)
    old_hint = "the kind of thing a hand leaves a wish with, the way you would a coin in a fountain"
    statue.description = ("a weathered stone figure, worn past recognizing, "
                           f"moss thick in its folds -- {old_hint}")
    resynced = ensure_statue(w)
    assert resynced.description.count("kind of thing") == 1, \
        f"the hint must not be duplicated by a wording change alone: {resynced.description!r}"


def test_look_statue_vaguely_hints_at_wishing():
    """README already claims "the statue's own description hints that
    wishing here is a thing people do" -- but that hint used to live only
    in the one-time discovery text, not the persistent `description` a
    later `look statue` actually returns. Fold it into the base
    description too, same folk-magic register (a coin in a fountain), and
    keep well clear of THE LINE THAT MUST NEVER APPEAR: nothing implying
    the statue listens, grants, or is aware."""
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    result = w.act(actor, "look statue")
    assert "wish" in result.lower()
    for forbidden in ("hears", "listens", "grants", "knows", "aware"):
        assert forbidden not in result.lower(), \
            f"statue description implies awareness/granting: {result!r}"


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


def test_the_statue_stays_last_in_the_room_listing_after_later_arrivals():
    """NEAR MISS, pinned here because nothing else caught it. _room_here used
    to get this for free -- it filtered the statue out and re-appended it, so
    it always landed at the end. Rewriting that as a straight filter over
    PRESENCE_RULES silently moved it to wherever insertion order put it, the
    moment anything at the edge was created after the statue was (a curio
    dropped there after finding it, say). The statue reads as a beat at the
    end of what you can see, not one item among the furniture -- see
    PRESENCE_LAST."""
    w, actor = fresh()
    w.rng = _AlwaysDiscover()
    run(w, actor, "go out", "go forest", "venture", "venture", "venture")
    cmd_wish(w, actor, "a warm winter")           # materializes the statue
    w.add(Entity(w.fresh_id("found"), "a late curio", "odd little thing",
                 location="forest_edge", portable=True, attrs={"curio": True}))
    here = _room_here(w, actor, w.get("forest_edge"))
    assert here[-1].id == "statue", \
        f"the statue must stay last, got {[e.id for e in here]}"


def test_presence_rules_are_how_the_forest_hides_its_two_landmarks():
    """The rules are registered by the forest, not hardcoded into the helper
    every verb in the game reaches through -- that's the whole point of the
    registry. If these two go missing, _room_here silently starts showing
    both landmarks from everywhere."""
    assert PRESENCE_RULES["statue"] is _statue_reachable
    w, actor = fresh()
    w.forest_depth = 0
    assert PRESENCE_RULES["cairn"](w, actor), "the cairn is present at the edge"
    w.forest_depth = 1
    assert not PRESENCE_RULES["cairn"](w, actor), "and gone one step in"
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
