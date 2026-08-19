"""
test_journal_and_seed.py -- tests for the journal (the seed entry every
fresh world ships with, reading it, its view/spread windowing) and the
mystery seed (found at the forest's edge, planted in the yard, blooming
into one of a handful of flowers on its own multi-visit schedule). Split
out of test_content.py -- see docs/ARCHITECTURE.md's note on that split.

Run it either way:
    python3 -m pytest test_journal_and_seed.py -v   # if you have pytest
    python3 test_journal_and_seed.py                 # if you don't (built-in runner)
"""

from world import Entity
from content import (
    SEED_NAME, BLOOM_TICKS, BLOOM_KINDS, _seed_in_world, _mystery_plant,
    JOURNAL_READ_LIMIT, JOURNAL_OLDER_SHOWN, JOURNAL_GAP, journal_view,
    _journal_view_indices,
)
from _test_helpers import fresh, run, _add_curio


# ===========================================================================
# 1. THE SEED JOURNAL -- a fresh world ships with a single seed entry: pure
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


def _fill_journal(world, actor, texts):
    """Fill the journal with known entries. Callers zero-pad their markers so
    no entry's marker is a substring of another's ("entry 1" would otherwise
    also match inside "entry 10")."""
    for text in texts:
        world.act(actor, f"write {text}")


def test_read_journal_keeps_the_most_recent_entries():
    w, actor = fresh()
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(JOURNAL_READ_LIMIT + 8)])
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == 1 + JOURNAL_READ_LIMIT + 8, "the full history must still be kept"
    result = w.act(actor, "read journal")
    recent = range(JOURNAL_READ_LIMIT + 8 - JOURNAL_READ_LIMIT, JOURNAL_READ_LIMIT + 8)
    for i in recent:
        assert f"entry {i:03d}" in result, "the recent tail must always be shown"


def test_read_journal_reaches_further_back_than_the_recent_tail():
    """THE REGRESSION THIS WHOLE POLICY EXISTS FOR. A plain tail means a run
    of similar entries becomes the entire inherited memory: in real play, a
    stretch where every hand wrote the same warning filled the whole view, so
    each new hand read nothing but that warning and wrote another one. The
    view must always reach past the tail into older history."""
    w, actor = fresh()
    _fill_journal(w, actor, [f"calm {i:03d}" for i in range(20)]
                            + [f"panic {i:03d}" for i in range(10)])
    result = w.act(actor, "read journal")
    assert any(f"calm {i:03d}" in result for i in range(20)), \
        "a run of recent entries must not be able to fill the entire view"


def test_read_journal_always_keeps_the_seed_entry():
    """The first entry is the one that orients someone with no memory --
    it's the only place the lamp/hearth relationship is spelled out."""
    w, actor = fresh()
    seed = w.get("journal").attrs["entries"][0]
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(30)])
    assert seed in w.act(actor, "read journal")


def test_read_journal_marks_where_it_skipped():
    """A hand should be able to tell it's reading an excerpt with gaps, not
    a complete record -- otherwise the journal quietly lies about the past."""
    w, actor = fresh()
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(30)])
    assert "..." in w.act(actor, "read journal")


def test_read_journal_is_stable_while_the_journal_is_unchanged():
    """Reading twice must show the same thing -- the LLM driver tells a hand
    the journal "won't change" once read, and a physical book doesn't
    reshuffle which pages fall open."""
    w, actor = fresh()
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(30)])
    assert w.act(actor, "read journal") == w.act(actor, "read journal")


def test_read_journal_shows_everything_when_within_the_limit():
    w, actor = fresh()
    w.act(actor, "write a second entry")
    result = w.act(actor, "read journal")
    assert "entry" in result.lower()
    assert "..." not in result, "nothing was skipped, so no gap marker"
    assert "of" not in result.split(":")[0], \
        "no truncation note should appear when nothing was actually cut"


def test_read_journal_notes_how_much_was_cut():
    w, actor = fresh()
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(JOURNAL_READ_LIMIT + 8)])
    total = len(w.get("journal").attrs["entries"])
    result = w.act(actor, "read journal")
    header = result.split("\n")[0]
    assert str(total) in header, "the header should say how many entries there are in all"
    assert str(total) != header.strip(), "and how many of them are being shown"


def test_read_journal_all_shows_every_entry():
    """The excerpt is the default, not a wall the archive hides behind --
    the whole record stays one command away, and the header says so."""
    w, actor = fresh()
    _fill_journal(w, actor, [f"entry {i:03d}" for i in range(30)])
    capped = w.act(actor, "read journal")
    assert "read journal all" in capped, "the excerpt must name the way to the full record"
    full = w.act(actor, "read journal all")
    for i in range(30):
        assert f"entry {i:03d}" in full
    assert "..." not in full, "the full record has no gaps to mark"


def test_journal_view_is_bounded_however_long_the_journal_gets():
    """The whole point is that this never grows without bound. The count of
    real entries shown is what's fixed; the number of gap markers varies,
    since neighbouring picks need no gap between them."""
    def written(view):
        return [ln for ln in view if ln != JOURNAL_GAP]
    short = journal_view([f"entry {i}" for i in range(12)])
    long = journal_view([f"entry {i}" for i in range(400)])
    assert len(written(long)) == len(written(short)) == \
        1 + JOURNAL_OLDER_SHOWN + JOURNAL_READ_LIMIT, \
        "seed + sampled older + the recent tail, however long the journal is"
    assert len(long) <= 1 + JOURNAL_OLDER_SHOWN * 2 + JOURNAL_READ_LIMIT + 1, \
        "bounded even counting every possible gap marker"


def test_journal_view_indices_middle_picks_are_seeded_by_length_not_world_rng():
    """Real-play ask: weight the view toward history so a one-off entry
    (finding the statue, say) keeps getting real odds of being read, not
    just a lucky evenly-spaced window it eventually ages out of. The
    seeded picks must still be fully deterministic for a GIVEN length --
    two calls with the same n must be identical, with no dependence on
    world.rng or call order (nothing here is threaded a world or an rng
    at all, which is itself the guarantee: there's nothing mutable to
    depend on)."""
    a = _journal_view_indices(200)
    b = _journal_view_indices(200)
    assert a == b


def test_journal_view_indices_middle_picks_differ_as_the_journal_grows():
    """Unlike the old evenly-spaced spans (which moved smoothly and could
    permanently pass over a given entry once the span swept past it), a
    length-seeded pick should genuinely differ from one length to the
    next, not just slide -- most consecutive lengths should not reuse the
    exact same middle indices."""
    picks = [tuple(i for i in _journal_view_indices(n) if i not in (None,)
                    and i != 0 and i < n - JOURNAL_READ_LIMIT)
             for n in range(30, 60)]
    assert len(set(picks)) > 1, "middle picks never vary across journal lengths"


def test_journal_view_indices_middle_picks_are_unique_and_ordered():
    indices = _journal_view_indices(300)
    real = [i for i in indices if i is not None]
    assert real == sorted(set(real)), "no duplicate or out-of-order picks"


def test_journal_view_indices_a_specific_entry_gets_picked_at_some_length():
    """The actual motivation, made concrete: a single entry written once
    (say, index 15) should show up in SOME journal length's middle
    sample, not be permanently excluded the way a fixed evenly-spaced
    pattern could leave it stranded forever once the spans moved past it."""
    target = 15
    ever_shown = any(
        target in _journal_view_indices(n)
        for n in range(target + JOURNAL_READ_LIMIT + JOURNAL_OLDER_SHOWN + 1, target + 400)
    )
    assert ever_shown, f"entry {target} never appears across a long run of journal lengths"


# ===========================================================================
# TUCK-IN-JOURNAL -- the flat-and-pressable counterpart to the cairn: a
# feather (or the mystery seed's bloom) presses into the journal entry
# active this visit, permanently, discovered by reading the journal rather
# than by a dedicated inventory. Feathers and the bloom only -- round or
# dimensional curios (a pinecone, a stone, a button) get a plain refusal.
# ===========================================================================
def _add_bloom(world, actor, name="a rust-red flower", location=None):
    """A mystery-seed bloom, already opened -- identified by its blooms_at
    attr (see _is_tuckable), not by name; some bloom names (e.g. "a single
    black bloom") don't even contain the word "flower"."""
    return world.add(Entity(world.fresh_id("bloom"), name,
                             "ragged-edged petals, the colour of old iron",
                             location=location or actor.id, portable=True,
                             attrs={"curio": True, "cat_reaction": "ignores",
                                    "blooms_at": 400, "growth": 400, "ready": True}))


def test_tucking_a_feather_removes_it_and_attaches_it_to_an_entry():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    result = w.act(actor, "tuck jay's feather in journal")
    assert "press" in result.lower(), f"unexpected tuck response: {result!r}"
    assert not any("feather" in e.name for e in w.entities.values()), \
        "the tucked feather must be gone from the world, not just hidden"
    entries = w.get("journal").attrs["entries"]
    tucked = w.get("journal").attrs["tucked"]
    assert tucked[str(len(entries) - 1)] == ["a jay's feather"]


def test_tucking_the_mystery_seed_bloom_also_works():
    w, actor = fresh()
    _add_bloom(w, actor)
    result = w.act(actor, "tuck rust-red flower in journal")
    assert "press" in result.lower(), f"unexpected tuck response: {result!r}"
    assert not any("blooms_at" in e.attrs for e in w.entities.values()), \
        "the tucked bloom must be gone from the world"


def test_tucking_a_non_qualifying_curio_refuses_gracefully_with_no_state_change():
    w, actor = fresh()
    pinecone = _add_curio(w, actor, "a pinecone")
    before_entries = list(w.get("journal").attrs["entries"])
    result = w.act(actor, "tuck pinecone in journal")
    assert "won't press flat" in result.lower(), f"a pinecone should be refused: {result!r}"
    assert w.get(pinecone.id) is not None and pinecone.location == actor.id, \
        "a refused tuck must leave the item exactly where it was"
    assert w.get("journal").attrs["entries"] == before_entries, \
        "a refused tuck must not touch the journal"
    assert "tucked" not in w.get("journal").attrs or not w.get("journal").attrs["tucked"]


def test_tucking_without_writing_first_still_succeeds_via_a_placeholder_entry():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    before = len(w.get("journal").attrs["entries"])
    w.act(actor, "tuck jay's feather in journal")
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == before + 1, "a placeholder entry should have been created"
    assert "a jay's feather is pressed into this page" in w.act(actor, "read journal all")


def test_two_tucks_in_one_visit_with_no_write_share_the_same_placeholder():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    _add_curio(w, actor, "a small brown feather")
    before = len(w.get("journal").attrs["entries"])
    w.act(actor, "tuck jay's feather in journal")
    w.act(actor, "tuck small brown feather in journal")
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == before + 1, "both tucks should land on one placeholder entry"
    tucked = w.get("journal").attrs["tucked"][str(len(entries) - 1)]
    assert tucked == ["a jay's feather", "a small brown feather"]


def test_tucked_item_appears_in_the_spread_read_journal():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "write a quiet day")
    w.act(actor, "tuck jay's feather in journal")
    result = w.act(actor, "read journal")
    assert "a jay's feather is pressed into this page" in result


def test_tucked_item_appears_in_read_journal_all():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "write a quiet day")
    w.act(actor, "tuck jay's feather in journal")
    result = w.act(actor, "read journal all")
    assert "a jay's feather is pressed into this page" in result


def test_a_tucked_item_attaches_to_the_entry_just_written_this_visit():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "write a quiet day")
    entries_before = len(w.get("journal").attrs["entries"])
    w.act(actor, "tuck jay's feather in journal")
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == entries_before, "an already-written entry needs no placeholder"
    tucked = w.get("journal").attrs["tucked"]
    assert tucked[str(len(entries) - 1)] == ["a jay's feather"]


def test_a_tuck_placeholder_is_upgraded_by_a_later_write_in_the_same_visit():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    before = len(w.get("journal").attrs["entries"])
    w.act(actor, "tuck jay's feather in journal")
    w.act(actor, "write a quiet day")
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == before + 1, \
        "the write should upgrade the tuck's placeholder, not add a second entry"
    assert entries[-1].endswith("a quiet day")
    tucked = w.get("journal").attrs["tucked"]
    assert tucked[str(len(entries) - 1)] == ["a jay's feather"]
    result = w.act(actor, "read journal all")
    assert "a jay's feather is pressed into this page" in result
    assert "a quiet day" in result
    assert "nothing written" not in result


def test_a_second_write_after_the_tuck_upgrade_still_adds_a_fresh_entry():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "tuck jay's feather in journal")
    w.act(actor, "write a quiet day")
    before = len(w.get("journal").attrs["entries"])
    w.act(actor, "write and then a nap")
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == before + 1
    assert entries[-1].endswith("and then a nap")


def test_there_is_no_take_verb_for_a_tucked_item():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "tuck jay's feather in journal")
    result = w.act(actor, "take jay's feather")
    assert "there's no" in result.lower(), f"a tucked item should be unreachable: {result!r}"


def test_a_tucked_item_never_duplicates_across_room_inventory_shelf_or_cairn():
    w, actor = fresh()
    _add_curio(w, actor, "a jay's feather")
    w.act(actor, "tuck jay's feather in journal")
    shelf = w.get("shelf")
    live_feathers = [e for e in w.entities.values() if "feather" in e.name]
    assert live_feathers == [], "a tucked feather must not still exist as an entity anywhere"
    assert "feather" not in (shelf.description if shelf else "")


def test_tuck_action_is_offered_only_with_a_qualifying_curio_in_hand():
    w, actor = fresh()
    assert not any(a.startswith("tuck ") for a in w.available_actions(actor)), \
        "tuck shouldn't be offered with nothing tuckable in hand"
    _add_curio(w, actor, "a jay's feather")
    assert "tuck a jay's feather in journal" in w.available_actions(actor)
    _add_curio(w, actor, "a pinecone")
    assert not any(a == "tuck a pinecone in journal" for a in w.available_actions(actor)), \
        "a pinecone is not tuckable and must not be offered"


# ===========================================================================
# 2. THE MYSTERY SEED -- a seed found at the forest's edge, planted in the
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
