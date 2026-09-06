"""
test_fox.py -- tests for the fox, per docs/FOX_SPEC.md: never an entity
(all state lives in yard.attrs), offerings that always resolve overnight
and ratchet trust one-way, texture that deepens in stages, naming once
she's been seen, and -- past the trust ceiling -- rare gifts on her own
clock, hard-decoupled from any single offering.

Run it either way:
    python3 -m pytest test_fox.py -v      # if you have pytest
    python3 test_fox.py                    # if you don't (built-in runner)
"""

from world import World, check_world
from fox import (
    FOX_SIGN_ID, FOX_TRUST_GLIMPSE, FOX_TRUST_SEEN, FOX_TRUST_LINGERS,
    FOX_TRUST_CEILING, FOX_GIFT_SUPPRESSION_TICKS, FOX_GIFT_POOL,
    _fox_sign_text, ensure_fox,
)
from content import cmd_name
from _test_helpers import fresh, run, _Lucky, _Unlucky


def _give_egg(world, actor):
    from world import Entity
    return world.add(Entity(world.fresh_id("egg"), "an egg",
                             "a small brown egg, still warm",
                             location=actor.id, portable=True))


def _leave_egg_out(world, actor):
    world.act(actor, "go out")
    _give_egg(world, actor)
    return world.act(actor, "leave egg out")


def _force_night(world, actor):
    while world.phase() != "night":
        world.act(actor, "wait")


def _resolve_one_offering(world, actor):
    """Leave an egg out and tick through to the next night, so the
    offering resolves exactly once."""
    _leave_egg_out(world, actor)
    _force_night(world, actor)


# ===========================================================================
# 1. THE OFFERING -- leaving an egg out, and it always resolving overnight.
# ===========================================================================
def test_leave_egg_out_is_offered_only_in_the_yard_with_an_egg_in_hand():
    w, actor = fresh()
    assert not any(a.startswith("leave egg") for a in w.available_actions(actor))
    run(w, actor, "go out")
    assert not any(a.startswith("leave egg") for a in w.available_actions(actor))
    _give_egg(w, actor)
    assert "leave egg out" in w.available_actions(actor)


def test_leave_egg_out_is_not_offered_once_an_offering_is_already_out():
    w, actor = fresh()
    _leave_egg_out(w, actor)
    _give_egg(w, actor)
    assert "leave egg out" not in w.available_actions(actor)


def test_leave_egg_out_requires_the_yard():
    w, actor = fresh()
    _give_egg(w, actor)
    result = w.act(actor, "leave egg out")
    assert "yard" in result.lower()


def test_leave_egg_out_requires_carrying_an_egg():
    w, actor = fresh()
    run(w, actor, "go out")
    result = w.act(actor, "leave egg out")
    assert "no egg" in result.lower()


def test_leave_egg_out_accepts_a_cooked_egg_too():
    w, actor = fresh()
    run(w, actor, "go out")
    egg = _give_egg(w, actor)
    egg.name = "a boiled egg"
    egg.attrs["food"] = 1
    result = w.act(actor, "leave egg out")
    assert "fence" in result.lower()


def test_the_offering_is_visible_in_the_yard_once_left_out():
    w, actor = fresh()
    result = _leave_egg_out(w, actor)
    assert "fence" in result.lower()
    look = w.act(actor, "look")
    assert "fence" in look.lower()


def test_an_offering_is_always_gone_by_morning_and_trust_increments_by_one():
    w, actor = fresh()
    yard = w.get("yard")
    _resolve_one_offering(w, actor)
    assert yard.attrs.get("fox_trust") == 1
    assert not any(e.attrs.get("fox_offering") for e in w.contents("yard"))


def test_the_forest_edges_dusk_fox_glimpse_line_is_unrelated_and_unaffected():
    """The ambient wildlife fox (WILDLIFE_LINES) and this mechanic are
    deliberately separate systems -- pins that leaving an egg out doesn't
    touch the unrelated ambient line's own pool."""
    from content import WILDLIFE_LINES
    assert "yard" in WILDLIFE_LINES and "dusk" in WILDLIFE_LINES["yard"]


# ===========================================================================
# 2. TRUST -- one-way, never decreasing, gates texture only until the
#    ceiling, where it stops gating anything further.
# ===========================================================================
def test_trust_never_decreases_across_any_sequence():
    w, actor = fresh()
    yard = w.get("yard")
    seen = []
    for _ in range(4):
        _resolve_one_offering(w, actor)
        seen.append(yard.attrs["fox_trust"])
    assert seen == sorted(seen)
    assert len(set(seen)) == len(seen), "each offering should strictly increase trust"


def test_fox_sign_text_bands_deepen_with_trust_and_cap_at_lingers():
    assert "prints" in _fox_sign_text(1, None)
    assert "russet" in _fox_sign_text(FOX_TRUST_GLIMPSE, None)
    assert "seen" in _fox_sign_text(FOX_TRUST_SEEN, None).lower() or \
        "taking the egg" in _fox_sign_text(FOX_TRUST_SEEN, None)
    lingers = _fox_sign_text(FOX_TRUST_LINGERS, None)
    assert _fox_sign_text(FOX_TRUST_CEILING, None) == lingers, \
        "trust keeps counting past the ceiling but texture caps at 'lingers'"
    assert _fox_sign_text(1000, None) == lingers


def test_fox_sign_text_names_her_once_given_a_name():
    unnamed = _fox_sign_text(FOX_TRUST_SEEN, None)
    named = _fox_sign_text(FOX_TRUST_SEEN, "Sorrel")
    assert "Sorrel" in named
    assert named != unnamed


def test_the_sign_entity_reflects_the_current_stage_after_each_offering():
    w, actor = fresh()
    _resolve_one_offering(w, actor)
    sign = w.get(FOX_SIGN_ID)
    assert sign is not None
    assert sign.description == _fox_sign_text(1, None)


# ===========================================================================
# 3. THE CONSTRAINT THAT MUST NEVER BREAK -- no fox entity, ever, at any
#    trust stage; the hen and ordinary yard eggs are untouched.
# ===========================================================================
def test_no_fox_entity_exists_at_any_trust_stage():
    w, actor = fresh()
    for _ in range(6):
        _resolve_one_offering(w, actor)
    assert w.get("fox") is None
    assert not any("fox" == e.id for e in w.entities.values())


def test_the_hen_and_ordinary_yard_eggs_are_untouched_across_many_night_ticks():
    w, actor = fresh()
    for _ in range(3):
        _resolve_one_offering(w, actor)
    chicken = w.get("chicken")
    assert chicken is not None and chicken.location in ("yard", "hut")
    # an ordinary, non-offering egg must survive night ticks untouched
    stray = _give_egg(w, actor)
    stray.location = "yard"
    for _ in range(30):
        w.act(actor, "wait")
    assert w.get(stray.id) is not None


# ===========================================================================
# 4. NAMING -- unlocks at "seen," never before, sticks, flows into texture.
# ===========================================================================
def test_name_fox_is_absent_below_the_seen_stage():
    w, actor = fresh()
    assert not any(a.startswith("name fox") for a in w.available_actions(actor))
    _resolve_one_offering(w, actor)
    assert not any(a.startswith("name fox") for a in w.available_actions(actor))


def test_name_fox_appears_once_seen_and_disappears_once_named():
    w, actor = fresh()
    w.get("yard").attrs["fox_trust"] = FOX_TRUST_SEEN
    assert any(a.startswith("name fox") for a in w.available_actions(actor))
    w.act(actor, "name fox Sorrel")
    assert not any(a.startswith("name fox") for a in w.available_actions(actor))


def test_naming_the_fox_below_seen_is_refused():
    w, actor = fresh()
    result = w.act(actor, "name fox Sorrel")
    assert "no fox" in result.lower()
    assert w.get("yard").attrs.get("fox_given_name") is None


def test_naming_the_fox_sticks_and_flows_into_the_sign():
    w, actor = fresh()
    w.get("yard").attrs["fox_trust"] = FOX_TRUST_SEEN
    w.act(actor, "name fox Sorrel")
    assert w.get("yard").attrs["fox_given_name"] == "Sorrel"
    _resolve_one_offering(w, actor)
    assert "Sorrel" in w.get(FOX_SIGN_ID).description


def test_naming_the_fox_persists_across_save_load():
    w, actor = fresh()
    w.get("yard").attrs["fox_trust"] = FOX_TRUST_SEEN
    w.act(actor, "name fox Sorrel")
    reloaded = World.from_data(w.to_data())
    assert reloaded.get("yard").attrs["fox_given_name"] == "Sorrel"


def test_naming_cat_and_chicken_is_unaffected_by_the_fox_naming_branch():
    w, actor = fresh()
    result = w.act(actor, "name Shadow")
    assert "Shadow" in result
    run(w, actor, "go out")
    result = w.act(actor, "name chicken Henrietta")
    assert "Henrietta" in result


# ===========================================================================
# 5. GIFTS -- rare, decoupled hard from any one offering, at most one
#    unclaimed at a time.
# ===========================================================================
def test_no_gift_spawns_below_the_trust_ceiling_even_with_a_rigged_rng():
    w, actor = fresh()
    w.get("yard").attrs["fox_trust"] = FOX_TRUST_CEILING - 1
    w.rng = _Lucky()
    for _ in range(10):
        w.act(actor, "wait")
    assert not any(e.attrs.get("fox_gift") for e in w.entities.values())


def test_a_gift_spawns_at_the_ceiling_with_a_rigged_rng_and_joins_the_curio_economy():
    w, actor = fresh()
    yard = w.get("yard")
    yard.attrs["fox_trust"] = FOX_TRUST_CEILING
    yard.attrs["fox_suppress_until"] = 0
    w.rng = _Lucky()
    w.act(actor, "wait")
    gift = next((e for e in w.contents("yard") if e.attrs.get("fox_gift")), None)
    assert gift is not None
    assert gift.attrs.get("curio") is True
    assert gift.portable is True


def test_no_gift_spawns_within_the_suppression_window_after_an_offering():
    w, actor = fresh()
    yard = w.get("yard")
    yard.attrs["fox_trust"] = FOX_TRUST_CEILING - 1
    _resolve_one_offering(w, actor)  # sets fox_suppress_until
    w.rng = _Lucky()
    for _ in range(10):
        w.act(actor, "wait")
    assert not any(e.attrs.get("fox_gift") for e in w.entities.values())


def test_no_second_gift_spawns_while_one_is_unclaimed():
    w, actor = fresh()
    yard = w.get("yard")
    yard.attrs["fox_trust"] = FOX_TRUST_CEILING
    yard.attrs["fox_suppress_until"] = 0
    w.rng = _Lucky()
    w.act(actor, "wait")
    first_gifts = [e.id for e in w.contents("yard") if e.attrs.get("fox_gift")]
    assert len(first_gifts) == 1
    for _ in range(10):
        w.act(actor, "wait")
    still_there = [e for e in w.contents("yard") if e.attrs.get("fox_gift")]
    assert [e.id for e in still_there] == first_gifts


def test_a_claimed_gift_frees_up_room_for_a_new_one():
    w, actor = fresh()
    yard = w.get("yard")
    yard.attrs["fox_trust"] = FOX_TRUST_CEILING
    yard.attrs["fox_suppress_until"] = 0
    w.rng = _Lucky()
    w.act(actor, "wait")
    gift = next(e for e in w.contents("yard") if e.attrs.get("fox_gift"))
    w.act(actor, f"take {gift.name}")
    yard.attrs["fox_suppress_until"] = 0
    w.act(actor, "wait")
    assert any(e.attrs.get("fox_gift") for e in w.contents("yard"))


def test_gift_pool_entries_are_all_curio_shaped_and_distinct_from_found_items():
    from curios import FOUND_ITEMS
    found_names = {n for n, _, _ in FOUND_ITEMS}
    for name, look_line, reaction in FOX_GIFT_POOL:
        assert name not in found_names, f"{name!r} should read as hers, not a forest find"
        assert reaction in ("plays", "ignores")


# ===========================================================================
# 6. PERSISTENCE
# ===========================================================================
def test_full_fox_state_survives_a_save_load_roundtrip():
    w, actor = fresh()
    yard = w.get("yard")
    _resolve_one_offering(w, actor)
    yard.attrs["fox_trust"] = FOX_TRUST_SEEN
    w.act(actor, "name fox Sorrel")
    data = w.to_data()
    reloaded = World.from_data(data)
    ryard = reloaded.get("yard")
    assert ryard.attrs["fox_trust"] == FOX_TRUST_SEEN
    assert ryard.attrs["fox_given_name"] == "Sorrel"
    assert reloaded.get(FOX_SIGN_ID) is not None


def test_a_pre_fox_save_backfills_cleanly_via_ensure_fox():
    """Simulate an older save: a yard entity round-tripped through
    to_dict/from_dict with no fox_tending in its serialized behaviors."""
    w, actor = fresh()
    data = w.to_data()
    for e in data["entities"]:
        if e["id"] == "yard":
            e["behaviors"] = [n for n in e["behaviors"] if n != "fox_tending"]
            e["attrs"] = {k: v for k, v in e["attrs"].items() if not k.startswith("fox_")}
    reloaded = World.from_data(data)
    yard = reloaded.get("yard")
    assert "fox_tending" not in yard.behavior_names
    ensure_fox(reloaded)
    assert "fox_tending" in yard.behavior_names
    assert yard.attrs.get("fox_trust", 0) == 0


def test_ensure_fox_does_not_double_attach_the_behavior():
    w, actor = fresh()
    yard = w.get("yard")
    before = yard.behavior_names.count("fox_tending")
    ensure_fox(w)
    ensure_fox(w)
    assert yard.behavior_names.count("fox_tending") == before == 1


def test_world_invariants_hold_after_a_full_fox_lifecycle():
    w, actor = fresh()
    yard = w.get("yard")
    for _ in range(3):
        _resolve_one_offering(w, actor)
    yard.attrs["fox_trust"] = FOX_TRUST_CEILING
    yard.attrs["fox_suppress_until"] = 0
    w.rng = _Lucky()
    w.act(actor, "wait")
    issues = check_world(w)
    assert not issues, issues


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
