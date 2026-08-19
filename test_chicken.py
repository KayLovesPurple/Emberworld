"""
test_chicken.py -- tests for the chicken as its own subsystem: the
producer-not-consumer guarantee, its one verb (name, shared with the cat
via content.py's cmd_name), its two autonomous behaviors (idle/lay), and
the egg economy (cook/eat) it feeds. See docs/CHICKEN_SPEC.md.

Run it either way:
    python3 -m pytest test_chicken.py -v      # if you have pytest
    python3 test_chicken.py                    # if you don't (built-in runner)
"""

import json

from world import World, Entity, check_world
from chicken import (CHICKEN_IDLE_CHANCE, CHICKEN_LAY_CHANCE, chicken_idle,
                     chicken_lay, ensure_chicken, build_chicken)
from content import COOKABLES, EGG_FOOD_VALUE, POTATO_FOOD_VALUE, cmd_cook, cmd_eat, cmd_name
from _test_helpers import fresh, run


class _Always:
    def random(self): return 0.0
    def choice(self, seq): return seq[0]


class _Never:
    def random(self): return 1.0
    def choice(self, seq): return seq[0]


# ===========================================================================
# THE CHICKEN -- a producer, never a second mouth. Must never have a
# hunger attr, ever, at any point in its lifecycle.
# ===========================================================================
def test_chicken_exists_in_a_fresh_world_in_the_yard():
    w, actor = fresh()
    chicken = w.get("chicken")
    assert chicken is not None
    assert chicken.location == "yard"


def test_chicken_never_has_a_hunger_attr_however_long_it_goes():
    """THE CONSTRAINT THAT MUST NEVER BREAK: no hunger attr, ever -- direct
    pin against the trap docs/CHICKEN_SPEC.md names, mirroring the cat's
    own gentle-guarantee test."""
    w, actor = fresh()
    chicken = w.get("chicken")
    for _ in range(300):
        w.act(actor, "wait")
        assert "hunger" not in chicken.attrs, "the chicken must never have a hunger attr"
        assert w.get("chicken") is not None, "the chicken vanished -- that must never happen"
    assert check_world(w) == []


def test_chicken_never_leaves_the_yard():
    """No wander behavior exists to attach -- regression guard against one
    accidentally getting added later. See CHICKEN_SPEC.md design goal #5."""
    w, actor = fresh()
    w.rng = _Always()
    for _ in range(200):
        w.act(actor, "wait")
        assert w.get("chicken").location == "yard"


def test_chicken_idle_only_announces_and_changes_no_state():
    w, actor = fresh()
    w.rng = _Always()
    chicken = w.get("chicken")
    before = dict(chicken.attrs)
    log_before = len(w.log)
    chicken_idle(w, chicken)
    assert chicken.attrs == before
    assert len(w.log) > log_before, "a forced idle roll should announce something"


def test_chicken_idle_never_fires_with_a_never_rng():
    w, actor = fresh()
    w.rng = _Never()
    chicken = w.get("chicken")
    log_before = len(w.log)
    chicken_idle(w, chicken)
    assert len(w.log) == log_before


def test_chicken_lay_forced_creates_exactly_one_egg_and_announces():
    w, actor = fresh()
    w.rng = _Always()
    chicken = w.get("chicken")
    before_ids = set(w.entities)
    log_before = len(w.log)
    chicken_lay(w, chicken)
    new = [e for e in w.entities.values() if e.id not in before_ids]
    assert len(new) == 1
    egg = new[0]
    assert egg.name == "an egg"
    assert egg.location == chicken.location
    assert egg.portable
    assert len(w.log) > log_before


def test_chicken_lay_never_fires_with_a_never_rng():
    w, actor = fresh()
    w.rng = _Never()
    chicken = w.get("chicken")
    before = len(w.entities)
    chicken_lay(w, chicken)
    assert len(w.entities) == before


def test_eggs_pile_up_with_no_cap_across_repeated_forced_lays():
    w, actor = fresh()
    w.rng = _Always()
    chicken = w.get("chicken")
    for _ in range(12):
        chicken_lay(w, chicken)
    eggs = [e for e in w.entities.values() if e.name == "an egg"]
    assert len(eggs) == 12, "eggs should pile up freely, same as unharvested potatoes"


def test_chicken_and_its_eggs_survive_a_save_load_roundtrip():
    w, actor = fresh()
    w.rng = _Always()
    chicken_lay(w, w.get("chicken"))
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.get("chicken") is not None
    assert any(e.name == "an egg" for e in w2.entities.values())


def test_ensure_chicken_backfills_a_world_missing_the_chicken():
    w, actor = fresh()
    del w.entities["chicken"]
    assert w.get("chicken") is None
    ensure_chicken(w)
    assert w.get("chicken") is not None
    assert w.get("chicken").location == "yard"


def test_ensure_chicken_is_idempotent():
    w, actor = fresh()
    original = w.get("chicken")
    ensure_chicken(w)
    assert w.get("chicken") is original, "must not replace an already-present chicken"


# ===========================================================================
# NAMING -- generalized cmd_name (content.py), shared by cat and chicken.
# "name <name>" with no prefix must keep defaulting to the cat, unchanged.
# ===========================================================================
def test_naming_the_chicken_sticks_and_persists():
    w, actor = fresh()
    run(w, actor, "go out")
    assert "Henrietta" in w.act(actor, "name chicken Henrietta")
    chicken = w.get("chicken")
    assert chicken.attrs["given_name"] == "Henrietta"
    assert chicken.name == "Henrietta"
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.get("chicken").attrs["given_name"] == "Henrietta"


def test_naming_the_chicken_needs_the_chicken_present():
    w, actor = fresh()
    # actor stays in the hut; the chicken never leaves the yard
    assert "no chicken here" in w.act(actor, "name chicken Henrietta").lower()


def test_bare_name_with_no_prefix_still_defaults_to_the_cat():
    """Backward compatibility: cmd_name's generalization must not change
    what a bare "name <name>" (no "cat "/"chicken " prefix) does."""
    w, actor = fresh()
    result = w.act(actor, "name Shadow")
    assert "Shadow" in result
    assert w.get("cat").attrs.get("given_name") == "Shadow"
    assert w.get("chicken").attrs.get("given_name") is None


def test_naming_the_cat_and_chicken_independently_does_not_cross_wires():
    w, actor = fresh()
    run(w, actor, "go out")
    w.get("cat").location = "yard"    # cat wanders on its own schedule; pin it here
    w.act(actor, "name cat Shadow")
    w.act(actor, "name chicken Henrietta")
    assert w.get("cat").attrs["given_name"] == "Shadow"
    assert w.get("chicken").attrs["given_name"] == "Henrietta"


def test_name_chicken_action_offered_only_while_unnamed():
    w, actor = fresh()
    run(w, actor, "go out")
    assert "name chicken <name>" in w.available_actions(actor)
    w.act(actor, "name chicken Henrietta")
    assert "name chicken <name>" not in w.available_actions(actor)


# ===========================================================================
# EGGS -- cooked and eaten like a potato; not a curio.
# ===========================================================================
def _give_egg(world, actor):
    return world.add(Entity(world.fresh_id("egg"), "an egg",
                             "a small brown egg, still warm",
                             location=actor.id, portable=True))


def test_cook_egg_produces_a_boiled_egg_with_food_value():
    w, actor = fresh()
    run(w, actor, "go in", "light hearth")
    _give_egg(w, actor)
    result = w.act(actor, "cook egg")
    egg = next(e for e in w.contents(actor.id) if e.name == "boiled egg")
    assert egg.attrs["food"] == EGG_FOOD_VALUE
    assert "hard-boiled" in result.lower() or "hard-boiled" in egg.description.lower()


def test_hearth_cook_hint_generalizes_to_a_raw_egg_in_hand():
    """_cook_hint (content.py) was written potato-only, before the chicken
    generalized cmd_cook itself via COOKABLES -- generalized here to match,
    so an egg doesn't reopen the exact invisible-affordance gap the hint was
    built to close (see content.py's own BUG WE HIT on _cook_hint)."""
    w, actor = fresh()
    run(w, actor, "go in", "light hearth")
    hearth = w.get("hearth")
    assert "cook" not in hearth.description.lower()
    _give_egg(w, actor)
    w.act(actor, "wait")
    assert "you could cook that egg here" in hearth.description.lower()


def test_cook_egg_mentions_the_pot_a_real_session_asked_about():
    """A real session asked "what did it boil the egg in?!" -- there was no
    vessel grounding the "hot water" flavor text at all. Pins that the
    egg's own cook_line now names the pot."""
    w, actor = fresh()
    run(w, actor, "go in", "light hearth")
    _give_egg(w, actor)
    result = w.act(actor, "cook egg")
    assert "pot" in result.lower()


def test_cook_potato_is_unaffected_by_the_cookables_generalization():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "go in", "light hearth")
    result = w.act(actor, "cook potato")
    potato = next(e for e in w.contents(actor.id) if e.name == "broiled potato")
    assert potato.attrs["food"] == POTATO_FOOD_VALUE
    assert "blistered and steaming" in result


def test_cook_egg_refuses_without_a_lit_fire():
    w, actor = fresh()
    _give_egg(w, actor)
    result = w.act(actor, "cook egg")
    assert "lit cooking fire" in result.lower()


def test_cook_egg_refuses_if_already_cooked():
    w, actor = fresh()
    run(w, actor, "go in", "light hearth")
    _give_egg(w, actor)
    w.act(actor, "cook egg")
    result = w.act(actor, "cook egg")
    assert "already cooked" in result.lower()


def test_eating_a_cooked_egg_reduces_hunger_by_its_food_value():
    """Calls cmd_eat directly (not through world.act) so the tick that
    hungering causes on every real turn can't muddy the exact food-value
    arithmetic being pinned here -- same technique used for the
    maintenance-resource invariant tests elsewhere in this codebase."""
    w, actor = fresh()
    actor.attrs["hunger"] = 30
    egg = _give_egg(w, actor)
    egg.name, egg.attrs["food"] = "boiled egg", EGG_FOOD_VALUE
    cmd_eat(w, actor, "boiled egg")
    assert actor.attrs["hunger"] == max(0, 30 - EGG_FOOD_VALUE)


def test_raw_egg_is_not_a_curio_and_stays_off_the_cat_cairn_and_tuck_systems():
    """The shelf itself accepts any portable item regardless of curio=True
    (pre-existing, permissive behavior -- raw clay can be placed there too),
    so this only pins give-to-cat/cairn/tuck, which DO gate on curio=True."""
    w, actor = fresh()
    egg = _give_egg(w, actor)
    assert not egg.attrs.get("curio")
    actions = w.available_actions(actor)
    assert not any("egg" in a and ("give" in a or "cairn" in a or "tuck" in a)
                   for a in actions)


def test_cookables_table_has_no_overlapping_or_missing_expected_keys():
    assert set(COOKABLES) == {"potato", "egg"}
    for kind, recipe in COOKABLES.items():
        assert recipe["food_value"] > 0
        assert recipe["cooked_name"] and recipe["cooked_desc"] and recipe["cook_line"]


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
