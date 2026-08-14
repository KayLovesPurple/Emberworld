"""
test_riverbank.py -- tests for the riverbank: a location structurally
parallel to the forest's edge, plus its calm verbs (listen/watch-clouds,
reusing the forest's own) and gather/shape for clay. Shaped clay is
deliberately excluded from the shelf/cairn/give-to-cat/tuck ecosystem --
see docs/CLAY_SPEC.md's "Why not a curio". Split out of test_content.py --
see docs/ARCHITECTURE.md's note on that split.

Run it either way:
    python3 -m pytest test_riverbank.py -v   # if you have pytest
    python3 test_riverbank.py                 # if you don't (built-in runner)
"""

import json

from world import World
from content import (
    WOOD_PER_GATHER, LISTEN_LINES, CALM_ACK_AT, CALM_ACK_LINE,
    RIVER_LISTEN_LINES, CLAY_NAME_CAP, cmd_shape, ensure_riverbank,
    RIVERBANK_DESCRIPTION,
)
from _test_helpers import fresh, run


# ===========================================================================
# 1. THE RIVERBANK AND CLAY -- a new location, structurally parallel to the
#     forest's edge, plus its two calm verbs (reusing listen/watch, which
#     already discard their arg) and gather/shape for clay itself. Shaped
#     clay is deliberately excluded from the shelf/cairn/give-to-cat/tuck
#     ecosystem -- see docs/CLAY_SPEC.md's "Why not a curio".
# ===========================================================================
def _go_riverbank(world, actor):
    run(world, actor, "go out", "go river")


def test_yard_has_a_river_exit_to_the_riverbank():
    w, actor = fresh()
    assert w.get("yard").exits.get("river") == "riverbank"


def test_riverbank_is_reachable_and_has_its_own_description():
    w, actor = fresh()
    _go_riverbank(w, actor)
    assert actor.location == "riverbank"
    assert w.get("riverbank").description == RIVERBANK_DESCRIPTION


def test_gather_at_the_riverbank_produces_exactly_one_raw_clay_lump():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    lumps = [e for e in w.contents(actor.id) if e.attrs.get("raw_clay")]
    assert len(lumps) == 1
    assert actor.attrs.get("wood", 0) == 0, "gathering clay must not touch wood"


def test_gather_at_the_forest_edge_is_unaffected_by_the_riverbank_addition():
    w, actor = fresh()
    run(w, actor, "go out", "go forest")
    result = w.act(actor, "gather wood")
    assert actor.attrs["wood"] == WOOD_PER_GATHER
    assert not any(e.attrs.get("raw_clay") for e in w.entities.values()), \
        f"gathering wood must never produce clay: {result!r}"


def test_gather_refuses_in_the_hut_and_yard():
    w, actor = fresh()
    assert "nothing to forage" in w.act(actor, "gather").lower()
    w.act(actor, "go out")
    assert "nothing to forage" in w.act(actor, "gather").lower()


def test_shaping_with_no_clay_carried_refuses_with_no_state_change():
    w, actor = fresh()
    _go_riverbank(w, actor)
    before = dict(w.get("riverbank").attrs)
    result = w.act(actor, "shape clay into a squat dish")
    assert "no clay" in result.lower()
    assert not any(e.name.startswith("a clay ") for e in w.entities.values())
    assert w.get("riverbank").attrs == before


def test_shaping_without_the_into_syntax_refuses_gracefully():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    result = w.act(actor, "shape a squat dish")
    assert "shape what into what" in result.lower()
    assert any(e.attrs.get("raw_clay") for e in w.contents(actor.id)), \
        "a malformed shape command must not consume the clay"


def test_shaping_clay_consumes_the_lump_and_creates_one_new_permanent_object():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    result = w.act(actor, "shape clay into a squat dish")
    assert "a clay squat dish" in result
    assert not any(e.attrs.get("raw_clay") for e in w.entities.values()), \
        "the raw lump must be gone once shaped"
    made = next(e for e in w.entities.values() if e.name == "a clay squat dish")
    assert made.location == "riverbank"
    assert made.portable is False
    assert made.description == "a clay squat dish, still faintly damp from the riverbank."


def test_shaping_strips_a_leading_article_so_it_never_doubles():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    w.act(actor, "shape clay into a squat dish")
    assert not any("a clay a " in e.name for e in w.entities.values()), \
        "typing its own article must not double up with the auto-prefix"

    w2, actor2 = fresh()
    _go_riverbank(w2, actor2)
    w2.act(actor2, "gather clay")
    w2.act(actor2, "shape clay into an urn")
    assert any(e.name == "a clay urn" for e in w2.entities.values())


def test_shaped_name_keeps_only_the_first_line_and_is_capped():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    long_name = "x" * (CLAY_NAME_CAP + 20)
    w.act(actor, f"shape clay into {long_name}\nsomething smuggled in")
    made = next(e for e in w.entities.values() if e.name.startswith("a clay x"))
    assert "smuggled" not in made.name and "smuggled" not in made.description
    assert len(made.name) <= len("a clay ") + CLAY_NAME_CAP


def test_shaped_clay_is_not_a_curio_and_stays_off_the_disposal_systems():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    w.act(actor, "shape clay into a squat dish")
    made = next(e for e in w.entities.values() if e.name == "a clay squat dish")
    assert not made.attrs.get("curio")
    actions = w.available_actions(actor)
    assert not any("clay squat dish" in a and ("give" in a or "cairn" in a or "tuck" in a)
                   for a in actions)


def test_shaped_clay_survives_a_save_load_roundtrip():
    w, actor = fresh()
    _go_riverbank(w, actor)
    w.act(actor, "gather clay")
    w.act(actor, "shape clay into a small pot")
    w2 = World.from_data(json.loads(json.dumps(w.to_data())))
    made = next((e for e in w2.entities.values() if e.name == "a clay small pot"), None)
    assert made is not None and made.location == "riverbank" and made.portable is False


def test_listen_at_the_riverbank_uses_its_own_line_pool():
    w, actor = fresh()
    _go_riverbank(w, actor)
    result = w.act(actor, "listen")
    stripped = result.split(CALM_ACK_LINE)[0] if CALM_ACK_LINE in result else result
    assert stripped in RIVER_LISTEN_LINES
    assert stripped not in LISTEN_LINES


def test_calm_visits_at_the_riverbank_are_tracked_independently_of_the_forest_edge():
    w, actor = fresh()
    _go_riverbank(w, actor)
    for _ in range(CALM_ACK_AT - 1):
        w.act(actor, "listen")
    result = w.act(actor, "listen")
    assert CALM_ACK_LINE in result, "the third calm act at a fresh spot should ack"
    assert w.calm_visits.get("forest_edge", 0) == 0, \
        "riverbank calm visits must not bleed into the forest edge's own count"


def test_watch_clouds_works_at_the_riverbank():
    w, actor = fresh()
    _go_riverbank(w, actor)
    result = w.act(actor, "watch clouds")
    assert result and "no open sky" not in result.lower()


def test_riverbank_actions_offer_gather_and_listen_but_shape_only_with_clay_in_hand():
    w, actor = fresh()
    _go_riverbank(w, actor)
    acts = w.available_actions(actor)
    assert "gather clay" in acts and "listen" in acts
    assert not any(a.startswith("shape ") for a in acts)
    w.act(actor, "gather clay")
    assert "shape clay into <name>" in w.available_actions(actor)


def test_ensure_riverbank_backfills_an_older_save_missing_the_room_and_exit():
    w, actor = fresh()
    del w.entities["riverbank"]
    del w.get("yard").exits["river"]
    assert w.get("riverbank") is None
    assert "river" not in w.get("yard").exits
    ensure_riverbank(w)
    assert w.get("riverbank") is not None
    assert w.get("yard").exits["river"] == "riverbank"


def test_ensure_riverbank_is_idempotent_and_never_clobbers_an_existing_exit():
    w, actor = fresh()
    w.get("yard").exits["river"] = "somewhere_else"
    ensure_riverbank(w)
    assert w.get("yard").exits["river"] == "somewhere_else", \
        "ensure_riverbank must never override an already-present exit"


def test_gathering_and_shaping_clay_touch_no_other_maintenance_resource():
    """Same invariant and same technique as
    test_giving_or_placing_a_curio_touches_no_maintenance_resource: call the
    handlers directly (not through world.act) so an unrelated tick -- fire
    burning down, hunger rising -- can't muddy what these two handlers
    themselves did or didn't touch."""
    from content import cmd_gather, cmd_shape
    w, actor = fresh()
    actor.location = "riverbank"
    cat = w.get("cat")
    cat.attrs["hunger"] = 5
    hearth = w.get("hearth")
    hearth.attrs["lit"], hearth.attrs["fuel"] = True, 10
    w.get("bucket").attrs["water"] = 2
    actor.attrs["wood"] = 4

    cmd_gather(w, actor, "")
    cmd_shape(w, actor, "clay into a squat dish")

    assert cat.attrs["hunger"] == 5, "gather/shape must not touch cat hunger"
    assert hearth.attrs["lit"] and hearth.attrs["fuel"] == 10, "must not touch fire-life"
    assert w.get("bucket").attrs["water"] == 2, "must not touch the bucket"
    assert actor.attrs["wood"] == 4, "must not touch firewood"


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
