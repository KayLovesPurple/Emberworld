"""
test_emberworld.py -- the safety net.

Run it either way:
    python3 -m pytest test_emberworld.py -v      # if you have pytest
    python3 test_emberworld.py                    # if you don't (built-in runner)

The philosophy: this world's bugs live in the SEAMS between systems, not inside
any one function. So these tests exercise the world *running* -- through the same
act()/perceive() surface a human or an LLM uses -- and assert on outcomes.

The first two tests pin the two bugs we actually hit while building, so they can
never silently come back.
"""

import json
import os
import tempfile

import emberworld as ew


# --- tiny helpers ----------------------------------------------------------
def fresh():
    """A brand-new world plus its actor."""
    return ew.build_world()


def run(world, actor, *commands):
    """Apply a sequence of commands, returning the last result string."""
    out = ""
    for c in commands:
        out = world.act(actor, c)
    return out


def wait(world, actor, n):
    for _ in range(n):
        world.act(actor, "wait")


# ===========================================================================
# 1. SCENARIO TESTS -- including regressions for the two bugs we hit.
# ===========================================================================
def test_regression_candle_is_heard_while_carried():
    """BUG WE HIT: events were scoped to an entity's immediate container, so a
    carried candle (now 'inside you') fell silent. You must still hear it."""
    w, actor = fresh()
    run(w, actor, "take candle")
    heard_gutter = heard_out = False
    for _ in range(14):
        line = w.act(actor, "wait")
        if "burns low" in line:
            heard_gutter = True
        if "goes out" in line:
            heard_out = True
    assert heard_gutter, "never heard the carried candle gutter"
    assert heard_out, "never heard the carried candle go out"


def test_candle_burns_out_offscreen():
    """A living world changes when you're not watching. Leave the candle in the
    hut, go to the yard: you should NOT hear it, but it should still be spent
    when you return."""
    w, actor = fresh()
    run(w, actor, "go out")
    lines = [w.act(actor, "wait") for _ in range(14)]
    assert not any("goes out" in ln for ln in lines), \
        "heard the candle from another room -- scoping is too loose"
    run(w, actor, "go in")
    assert not w.get("candle").attrs["lit"], "candle should have burned out"


def test_regression_patch_reflects_its_crop_in_sync():
    """BUG WE HIT: the patch described itself one tick behind the plant, so it
    said 'not far off ripe' on the very turn the crop ripened. The patch text
    and the ripened state must agree on the same turn."""
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato")
    patch = w.get("patch")
    # freshly planted: the patch visibly shows *something* happened
    assert "mound" in patch.description, \
        f"planting didn't change the patch: {patch.description!r}"
    # wait until ripe; on the turn it ripens, the description must match
    ripened_turn_desc = None
    for _ in range(20):
        line = w.act(actor, "wait")
        if "ripened" in line:
            ripened_turn_desc = patch.description
            break
    assert ripened_turn_desc is not None, "crop never ripened"
    assert "ready to lift" in ripened_turn_desc, \
        f"patch lagged behind the ripen event: {ripened_turn_desc!r}"


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
    assert ew._crop_in(w, "yard") is None, "planted something out of nothing"


def test_time_only_passes_on_real_actions():
    w, actor = fresh()
    t0 = w.time
    run(w, actor, "look", "inventory", "read journal")   # all FREE verbs
    assert w.time == t0, "looking around advanced the clock"
    run(w, actor, "wait")
    assert w.time == t0 + 1, "waiting didn't advance the clock"


def _make_it_dark(w, actor):
    """Snuff every light and advance to night, so the actor's room is dark."""
    run(w, actor, "snuff candle")
    for _ in range(40):
        if w.is_dark(actor.location):
            return
        w.act(actor, "wait")
    raise AssertionError("couldn't make the room dark")


def test_regression_cannot_inspect_room_things_in_the_dark():
    """BUG WE HIT: room-level look respected darkness, but 'look <thing>' and
    'read' didn't -- you could examine the knife and read the journal in pitch
    black the world had just said you couldn't see through. Targeted look/read
    must respect darkness too."""
    w, actor = fresh()
    _make_it_dark(w, actor)
    assert "dark" in w.act(actor, "look knife").lower(), \
        "examined a room object in the dark"
    assert "dark" in w.act(actor, "read journal").lower(), \
        "read the journal in the dark"


def test_can_inspect_carried_things_in_the_dark():
    """The sensible exception: you can always examine what's in your own hands,
    and read it by feel. This is also a learnable strategy -- pick it up."""
    w, actor = fresh()
    run(w, actor, "take journal", "take knife")
    _make_it_dark(w, actor)
    assert "iron knife" in w.act(actor, "look knife"), \
        "couldn't examine a carried item in the dark"
    assert "journal reads" in w.act(actor, "read journal"), \
        "couldn't read a carried item in the dark"


# ===========================================================================
# 2. INVARIANTS -- must hold no matter what features exist.
# ===========================================================================
def test_fresh_world_is_well_formed():
    w, _ = fresh()
    assert ew.check_world(w) == []


def test_invariants_survive_a_scripted_session():
    w, actor = fresh()
    script = ["go out", "take potato", "plant potato", "go in",
              "take candle", "snuff candle", "wait", "wait", "go out",
              "wait", "wait", "wait", "wait", "wait", "wait", "wait",
              "harvest", "go in", "light hearth", "cook potato"]
    for cmd in script:
        w.act(actor, cmd)
        assert ew.check_world(w) == [], f"invariant broke after '{cmd}'"


def test_checker_actually_catches_corruption():
    """A checker that never fires is worthless. Prove it screams when we break
    the world on purpose."""
    w, _ = fresh()
    w.get("candle").location = "nowhere-real"
    issues = ew.check_world(w)
    assert any("doesn't exist" in i for i in issues)

    w2, _ = fresh()
    w2.get("candle").attrs["fuel"] = -5
    assert any("negative" in i for i in ew.check_world(w2))

    w3, _ = fresh()
    del w3.entities["you"]
    assert any("actor" in i for i in ew.check_world(w3))


# ===========================================================================
# 3. FUZZ -- thousands of random legal moves, invariants checked every tick.
# ===========================================================================
def test_fuzz_seed_0():
    assert ew.fuzz_run(steps=3000, seed=0) == []


def test_fuzz_several_seeds():
    for seed in range(1, 6):
        assert ew.fuzz_run(steps=1500, seed=seed) == [], f"broke on seed {seed}"


# ===========================================================================
# 4. PERSISTENCE -- save/load round-trips exactly; bad saves are refused.
# ===========================================================================
def test_save_load_roundtrip_is_identical():
    w, actor = fresh()
    run(w, actor, "go out", "take potato", "plant potato", "wait", "wait")
    data1 = w.to_data()
    w2 = ew.World.from_data(json.loads(json.dumps(data1)))   # through real JSON
    data2 = w2.to_data()
    assert data1 == data2, "world changed shape across a save/load round-trip"


def test_incompatible_version_is_refused():
    w, _ = fresh()
    data = w.to_data()
    data["version"] = 1                       # pretend it's an old save
    try:
        ew.World.from_data(data)
        assert False, "loaded an incompatible save instead of refusing it"
    except ew.IncompatibleSaveError:
        pass


def test_stale_save_file_is_set_aside_not_crashed():
    """The 'stale save' problem should be a loud, clean refusal + fresh start,
    with the old file preserved -- never a crash or a silent mis-render."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        old = ew.build_world()[0].to_data()
        old["version"] = 1
        with open(save_path, "w") as f:
            json.dump(old, f)

        orig = ew.SAVE
        ew.SAVE = save_path                    # point the game at our temp save
        try:
            w, actor = ew.load_or_build(quiet=True)
        finally:
            ew.SAVE = orig
        assert w.day() == 1, "should have started a fresh world"
        assert os.path.exists(save_path + ".bak"), "old save wasn't preserved"


# ===========================================================================
# 5. THE LLM SIGN-OFF -- a visit must always leave a trace, even if the API
#    call for the note fails. Uses fake clients; no network, no key needed.
# ===========================================================================
class _FakeMsg:
    def __init__(self, text):
        self.content = [type("Blk", (), {"type": "text", "text": text})()]


class _FakeClient:
    def __init__(self, reply):
        self.reply, self.messages = reply, self

    def create(self, **kw):
        return _FakeMsg(self.reply)


def test_signoff_always_leaves_a_note():
    w, actor = fresh()
    n0 = len(w.get("journal").attrs["entries"])
    ew._leave_signoff(_FakeClient("Cooked a potato, banked the fire. -- tester"),
                      w, actor)
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == n0 + 1, "sign-off didn't add a journal entry"
    assert "tester" in entries[-1]
    assert entries[-1].startswith("[Day "), "note wasn't day-stamped"


def test_signoff_falls_back_when_the_api_fails():
    class Boom:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("no network")

    w, actor = fresh()
    n0 = len(w.get("journal").attrs["entries"])
    ew._leave_signoff(Boom(), w, actor)
    assert len(w.get("journal").attrs["entries"]) == n0 + 1, \
        "a failed API call must still leave a fallback note"


class _RecordingClient:
    """Captures the kwargs of the last create() call, returns a fixed reply."""
    def __init__(self):
        self.last = None
        self.messages = self

    def create(self, **kw):
        self.last = kw
        return _FakeMsg("wait")


def test_thinking_display_modes_are_requested_correctly():
    c = _RecordingClient()
    ew._ask_claude(c, "sys", "usr", ew.LLM_MODEL, think=True)
    assert "thinking" not in c.last, "plain call: adaptive default, no override"
    ew._ask_claude(c, "sys", "usr", ew.LLM_MODEL, think=False)
    assert c.last.get("thinking") == {"type": "disabled"}, "--no-think: disabled"
    ew._ask_claude(c, "sys", "usr", ew.LLM_MODEL, think=True, return_thinking=True)
    assert c.last.get("thinking") == {"type": "adaptive", "display": "summarized"}, \
        "showing thoughts must request summarized display (Sonnet 5 omits it by default)"


def test_ask_claude_can_return_the_thinking():
    class Msg:
        def __init__(self):
            self.content = [
                type("T", (), {"type": "thinking", "thinking": "I should wait."})(),
                type("B", (), {"type": "text", "text": "wait"})(),
            ]

    class C:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            return Msg()

    thoughts, text = ew._ask_claude(C(), "s", "u", ew.LLM_MODEL, return_thinking=True)
    assert thoughts == "I should wait." and text == "wait"
    # default call still returns just the command string
    assert ew._ask_claude(C(), "s", "u", ew.LLM_MODEL) == "wait"


def test_paint_only_colors_when_enabled():
    assert ew._paint("hi", "90", False) == "hi", "must be plain when color is off"
    painted = ew._paint("hi", "90", True)
    assert painted != "hi" and "hi" in painted, "should wrap text in an ANSI code"


def test_stuck_detection_spots_repeated_no_op_looks_but_not_waiting():
    from collections import deque
    h = deque(maxlen=5)
    assert not ew._looks_stuck(h)                       # empty
    h.append(("read journal", "The journal reads:"))
    h.append(("read journal", "The journal reads:"))
    assert not ew._looks_stuck(h)                       # only twice
    h.append(("read journal", "The journal reads:"))
    assert ew._looks_stuck(h), "three identical free-verb commands should read as stuck"
    h.append(("wait", "time passes"))
    assert not ew._looks_stuck(h), "a different command should clear stuck"
    # repeated waiting is CORRECT (that's how a crop grows) -- never flag it
    w = deque([("wait", "x"), ("wait", "x"), ("wait", "x")])
    assert not ew._looks_stuck(w), "waiting is how time passes -- must not be flagged"


def test_recent_block_lists_history_for_a_memoryless_agent():
    from collections import deque
    assert "nothing yet" in ew._recent_block(deque())
    h = deque([("plant potato", "firm it down"), ("wait", "time passes")])
    block = ew._recent_block(h)
    assert "plant potato" in block and "wait" in block


# ===========================================================================
# 6. THE CAT -- must never come to harm, and behaves sensibly.
# ===========================================================================
def test_cat_is_never_harmed_however_long_it_goes_unfed():
    """The gentle guarantee, enforced: no matter how long nobody feeds it, the
    cat's hunger stays capped and it simply stays present. No harm state exists."""
    w, actor = fresh()
    cat = w.get("cat")
    for _ in range(300):
        w.act(actor, "wait")
        assert 0 <= cat.attrs["hunger"] <= ew.CAT_HUNGER_CAP, "cat hunger left safe bounds"
        assert w.get("cat") is not None, "the cat vanished -- that must never happen"
    assert ew.check_world(w) == []


def test_feeding_requires_the_cat_present_and_resets_hunger():
    class Stay:                              # rng that never moves the cat
        def random(self): return 1.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    w.rng = Stay()
    cat = w.get("cat")
    run(w, actor, "go out", "take potato", "go in")   # fetch a potato; cat stays
    cat.location = "hut"
    cat.attrs["hunger"] = 10
    result = w.act(actor, "feed cat")
    assert "purrs" in result, f"feeding didn't land: {result!r}"
    assert cat.attrs["hunger"] < 5, "feeding didn't satisfy the cat"   # 0, +1 for the tick

    cat.location = "yard"                     # cat elsewhere, you in hut
    cat.attrs["hunger"] = 10
    run(w, actor, "go out", "take potato", "go in")
    assert "no cat here" in w.act(actor, "feed cat").lower()


def test_petting_needs_the_cat_and_costs_nothing_useful():
    w, actor = fresh()
    w.get("cat").location = "hut"
    assert "purrs" in w.act(actor, "pet cat")


def test_cat_is_drawn_to_a_lit_hearth():
    """Lighting the fire should pull the cat toward you -- learnable, gentle
    agency. Tested deterministically with a controlled roll."""
    class Roll:                              # always 'move, first option'
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    w.rng = Roll()
    cat = w.get("cat")
    cat.location = "yard"                     # cat away from the (unlit) hut
    w.get("hearth").attrs["lit"] = True       # now the hut is warm
    ew.cat_wander(w, cat)
    assert cat.location == "hut", "cat ignored the warm room next door"


def test_cat_meow_is_heard_only_in_its_own_room():
    """Scoping stress test with a non-player mover: a hungry cat in the yard
    meows in the yard, never the hut."""
    class Meow:                              # force the meow to fire
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["hunger"] = 10
    cat.location = "yard"
    w.rng = Meow()
    w.log = []
    ew.cat_hunger(w, cat)                     # cat meows in the yard
    heard_in_hut = [m for (m, where) in w.log
                    if where is None or where == "hut"]
    heard_in_yard = [m for (m, where) in w.log
                     if where is None or where == "yard"]
    assert not any("meow" in m for m in heard_in_hut), "heard the cat through a wall"
    assert any("meow" in m for m in heard_in_yard), "cat didn't meow where it was"


def test_naming_the_cat_sticks_and_persists():
    w, actor = fresh()
    w.get("cat").location = "hut"
    assert "Shadow" in w.act(actor, "name cat Shadow")
    cat = w.get("cat")
    assert cat.attrs["given_name"] == "Shadow"
    assert cat.name == "Shadow"
    # the name survives a save/load round-trip -- Shadow is Shadow for every hand
    w2 = ew.World.from_data(json.loads(json.dumps(w.to_data())))
    assert w2.get("cat").attrs["given_name"] == "Shadow"


def test_naming_needs_the_cat_present():
    w, actor = fresh()
    w.get("cat").location = "yard"           # you in hut, cat away
    assert "no cat here" in w.act(actor, "name cat Shadow").lower()


def test_named_cat_uses_its_name_in_announcements():
    class Meow:
        def random(self): return 0.0
        def choice(self, seq): return seq[0]
    w, actor = fresh()
    cat = w.get("cat")
    cat.attrs["given_name"] = "Shadow"
    cat.attrs["hunger"] = 10
    w.rng = Meow()
    w.log = []
    ew.cat_hunger(w, cat)
    assert any("Shadow" in m for (m, _) in w.log), "meow didn't use the cat's name"


# ===========================================================================
# 7. DOCUMENTATION -- the reference generates from code, and nothing new can
#    slip in undocumented. If these fail, you added a verb/behavior without a
#    docstring: write one, and the reference picks it up for free.
# ===========================================================================
def test_every_verb_is_documented():
    undocumented = sorted({fn.__name__ for fn in ew.VERBS.values() if not fn.__doc__})
    assert not undocumented, f"verbs missing a docstring: {undocumented}"


def test_every_behavior_is_documented():
    undocumented = sorted(n for n, fn in ew.BEHAVIORS.items() if not fn.__doc__)
    assert not undocumented, f"behaviors missing a docstring: {undocumented}"


def test_reference_generates_and_mentions_key_things():
    ref = ew.generate_reference()
    assert "## Verbs" in ref and "## Autonomous behaviors" in ref
    # a few anchors so a totally broken generator is caught
    for anchor in ("plant potato", "feed cat", "burning", "cat_wander"):
        assert anchor in ref, f"reference missing '{anchor}'"
    assert str(ew.CAT_HUNGER_CAP) in ref, "numeric rules didn't render"


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
