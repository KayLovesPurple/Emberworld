"""
test_pots.py -- tests for clay storage pots (pots.py): a shaped clay object
named "...pot" that holds up to CONTAINER_CAPACITY of one locked-in kind,
reusing the shelf's "put/store" verbs and its display_surface/find_visible
mechanism rather than inventing a parallel one.

Run it either way:
    python3 -m pytest test_pots.py -v   # if you have pytest
    python3 test_pots.py                 # if you don't (built-in runner)
"""

from world import Entity
from pots import (
    CONTAINER_CAPACITY, _is_storage_pot, _item_kind, _pot_description,
)
from _test_helpers import fresh, run


def _shape(world, actor, given):
    """Build a hand-shaped clay item the way real play does -- gather at
    the riverbank, then shape -- mirroring test_curios.py's _shape_bead."""
    from content import cmd_gather, cmd_shape
    prev_location = actor.location
    actor.location = "riverbank"
    cmd_gather(world, actor, "")
    cmd_shape(world, actor, f"clay into {given}")
    actor.location = prev_location
    return next(e for e in world.contents(actor.id) if e.name.endswith(given))


def _shape_pot(world, actor, given="pot"):
    return _shape(world, actor, given)


def _give_egg(world, actor, location=None):
    return world.add(Entity(world.fresh_id("egg"), "an egg",
                             "a small brown egg, still warm",
                             location=location or actor.id, portable=True))


def _give_potato(world, actor, location=None):
    return world.add(Entity(world.fresh_id("potato"), "a potato",
                             "a plain, dirt-flecked potato",
                             location=location or actor.id, portable=True))


def test_is_storage_pot_matches_shaped_clay_pots_not_the_tin_pot_fixture():
    """The hut's own "tin pot" (cook flavor text, content.py) also ends in
    "pot" -- it must never be mistaken for a storage pot, since it isn't
    portable or backed by any of this module's mechanics."""
    for name in ("a clay pot", "a clay squat pot", "a clay round-bellied pot"):
        assert _is_storage_pot(name), f"{name!r} should be a storage pot"
    for name in ("tin pot", "a clay bead", "a clay bowl", "a pinecone"):
        assert not _is_storage_pot(name), f"{name!r} should NOT be a storage pot"


def test_item_kind_treats_raw_and_cooked_food_as_the_same_kind():
    assert _item_kind("an egg") == _item_kind("a boiled egg") == "egg"
    assert _item_kind("a potato") == _item_kind("a broiled potato") == "potato"
    assert _item_kind("a pebble of blue glass") == "a pebble of blue glass"


def test_storing_an_egg_in_a_shaped_pot_moves_it_off_the_room_and_into_the_pot():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    egg = _give_egg(w, actor)
    result = w.act(actor, "put egg in clay pot")
    assert egg.location == pot.id
    assert w.get(egg.id) is not None, "the egg must not be consumed, just moved"
    assert "egg" in result.lower()


def test_store_is_accepted_as_an_alias_for_put():
    w, actor = fresh()
    _shape_pot(w, actor)
    _give_egg(w, actor)
    result = w.act(actor, "store egg in clay pot")
    assert "clay pot" in result.lower()


def test_a_pot_locks_to_the_first_kind_stored_and_refuses_a_different_one():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    egg = _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    potato = _give_potato(w, actor)
    result = w.act(actor, "put potato in clay pot")
    assert potato.location == actor.id, "the potato must not have been stored"
    assert "one kind per pot" in result.lower() or "already holds" in result.lower()


def test_a_second_pot_can_hold_a_different_kind_than_the_first():
    w, actor = fresh()
    egg_pot = _shape_pot(w, actor, given="egg pot")
    potato_pot = _shape_pot(w, actor, given="potato pot")
    egg = _give_egg(w, actor)
    potato = _give_potato(w, actor)
    w.act(actor, "put egg in clay egg pot")
    w.act(actor, "put potato in clay potato pot")
    assert egg.location == egg_pot.id
    assert potato.location == potato_pot.id


def test_a_pot_refuses_once_at_capacity():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    for _ in range(CONTAINER_CAPACITY):
        egg = _give_egg(w, actor)
        w.act(actor, "put egg in clay pot")
    overflow = _give_egg(w, actor)
    result = w.act(actor, "put egg in clay pot")
    assert overflow.location == actor.id, "the pot is full, nothing more should fit"
    assert "full" in result.lower()


def test_pot_description_reflects_empty_then_held_count_and_kind():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    assert "empty" in pot.description.lower()
    _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    assert "1 egg" in pot.description.lower()
    _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    assert "2 eggs" in pot.description.lower()


def test_storing_an_egg_removes_it_from_the_rooms_own_loose_listing():
    """The whole point, alongside function: decluttering, the same way the
    shelf already keeps loose curios off the room's flat listing."""
    w, actor = fresh()
    _shape_pot(w, actor)
    _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    room_contents = w.contents(actor.location)
    assert not any(e.name == "an egg" for e in room_contents)


def test_take_pulls_an_item_back_out_of_a_pot_and_refreshes_its_description():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    egg = _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    result = w.act(actor, "take egg")
    assert egg.location == actor.id
    assert "empty" in pot.description.lower()
    assert "egg" in result.lower()


def test_cooking_an_egg_works_while_its_pot_sits_in_the_room_uncarried():
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")
    pot.location = actor.location   # the pot itself is set down, not carried
    result = run(w, actor, "light hearth", "cook egg")
    assert "boiled" in result.lower() or "hard-boiled" in result.lower()


def test_available_actions_offers_put_for_a_matching_kind_and_not_a_mismatched_one():
    w, actor = fresh()
    _shape_pot(w, actor)
    _give_egg(w, actor)
    acts = w.available_actions(actor)
    assert any(a.startswith("put an egg in a clay pot") for a in acts), acts
    w.act(actor, "put egg in clay pot")
    _give_potato(w, actor)
    acts = w.available_actions(actor)
    assert not any(a.startswith("put a potato in a clay pot") for a in acts), acts


def test_the_real_shelf_is_still_found_correctly_once_a_pot_shares_its_room():
    """BUG WE HIT (caught before it shipped): both the shelf and a pot set
    display_surface, so a naive "any display_surface entity here" lookup
    could grab the pot instead of the shelf. The shelf has a fixed id."""
    w, actor = fresh()
    pot = _shape_pot(w, actor)
    egg = _give_egg(w, actor)
    w.act(actor, "put egg in clay pot")   # pot now has display_surface too
    pot.location = actor.location
    pebble = w.add(Entity(w.fresh_id("found"), "a pebble of blue glass",
                           "sea-frosted, edges gone soft.",
                           location=actor.id, portable=True,
                           attrs={"curio": True, "cat_reaction": "ignores"}))
    result = w.act(actor, "place pebble of blue glass on shelf")
    assert pebble.location == "shelf"
    assert "shelf" in result.lower()


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
