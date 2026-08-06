"""
test_drivers.py -- tests for the three drivers (human/random/LLM), the
persistence-loading glue, and the headless fuzzer.

Run it either way:
    python3 -m pytest test_drivers.py -v      # if you have pytest
    python3 test_drivers.py                    # if you don't (built-in runner)

The LLM sign-off tests use fake Anthropic clients -- no network, no key needed.
"""

import io
import json
import os
import random
import tempfile
from contextlib import redirect_stdout
from datetime import datetime

import drivers as drv
from world import Entity
from _test_helpers import fresh


# ===========================================================================
# 1. FUZZ -- thousands of random legal moves, invariants checked every tick.
# ===========================================================================
def test_fuzz_seed_0():
    assert drv.fuzz_run(steps=3000, seed=0) == []


def test_fuzz_several_seeds():
    for seed in range(1, 6):
        assert drv.fuzz_run(steps=1500, seed=seed) == [], f"broke on seed {seed}"


# ===========================================================================
# DUMB AGENT -- random legal play with no judgment behind its picks.
# ===========================================================================
def test_random_agent_never_drops_anything():
    """No judgment behind the dumb agent's choices means a randomly dropped
    lamp (mid-forest, say) is a bad time for the next visitor, not an
    interesting one -- see random_agent's own docstring. The fuzzer
    deliberately keeps drop in ITS pool; only the dumb agent excludes it."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                drv.random_agent(steps=200)
        finally:
            drv.SAVE = original
    chosen = [line for line in buf.getvalue().splitlines()
              if line.startswith(">>> ")]
    assert chosen, "the agent should have taken some actions"
    assert not any(line.startswith(">>> drop ") for line in chosen)


# ===========================================================================
# 2. PERSISTENCE-LOADING GLUE -- a bad save is set aside cleanly, never crashed.
# ===========================================================================
def test_stale_save_file_is_set_aside_not_crashed():
    """The 'stale save' problem should be a loud, clean refusal + fresh start,
    with the old file preserved -- never a crash or a silent mis-render."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        old = fresh()[0].to_data()
        old["version"] = 1
        with open(save_path, "w") as f:
            json.dump(old, f)

        orig = drv.SAVE
        drv.SAVE = save_path                    # point the game at our temp save
        try:
            w, actor = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = orig
        assert w.day() == 1, "should have started a fresh world"
        assert os.path.exists(save_path + ".bak"), "old save wasn't preserved"


def test_existing_save_is_given_the_new_shelf():
    """A live lineage should gain the shelf without needing a fresh world."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        data = fresh()[0].to_data()
        data["entities"] = [e for e in data["entities"] if e["id"] != "shelf"]
        with open(save_path, "w") as f:
            json.dump(data, f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            w, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        shelf = w.get("shelf")
        assert shelf is not None and shelf.location == "hut"


def test_existing_shelf_receives_the_clearer_purpose_text_on_load():
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        data = fresh()[0].to_data()
        shelf_data = next(e for e in data["entities"] if e["id"] == "shelf")
        shelf_data["description"] = "a narrow wooden shelf, empty but for a little dust"
        with open(save_path, "w") as f:
            json.dump(data, f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            w, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        assert "curio shelf" in w.get("shelf").description


def test_existing_save_is_given_the_forest_edge_cairn():
    """A live lineage from before the cairn existed should gain it without
    needing a fresh world, same reasoning as the shelf backfill above."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        data = fresh()[0].to_data()
        data["entities"] = [e for e in data["entities"] if e["id"] != "cairn"]
        with open(save_path, "w") as f:
            json.dump(data, f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            w, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        cairn = w.get("cairn")
        assert cairn is not None and cairn.location == "forest_edge"
        assert cairn.attrs["height_cm"] == 0


def test_existing_curl_of_blue_glass_is_renamed_on_load():
    """"a curl of blue glass" sounded sharp despite its own look_line saying
    otherwise -- renamed to "a pebble of blue glass". A hand already
    carrying one under the old name from a prior save should see the new
    one without needing a fresh world."""
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        w, actor = fresh()
        w.add(Entity("found_1", "a curl of blue glass", "sea-frosted, edges gone soft.",
                     location=actor.id, portable=True,
                     attrs={"curio": True, "cat_reaction": "ignores"}))
        with open(save_path, "w") as f:
            json.dump(w.to_data(), f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            loaded, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        assert loaded.get("found_1").name == "a pebble of blue glass"


def test_existing_found_item_is_tagged_as_a_curio_on_load():
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        w, actor = fresh()
        w.add(Entity("found_1", "a smooth grey stone", "a smooth stone",
                     location=actor.id, portable=True))
        with open(save_path, "w") as f:
            json.dump(w.to_data(), f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            loaded, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        assert loaded.get("found_1").attrs.get("curio")


def test_existing_found_item_is_backfilled_with_its_cat_reaction_on_load():
    """Curios found before give-to-cat existed have no cat_reaction attr yet;
    ensure_shelf should backfill it by name so `give` works on an old save
    without a fresh world. An unrecognised legacy name defaults to "ignores"
    rather than crashing give-to-cat."""
    from content import FOUND_ITEMS
    stone_name, _, stone_reaction = next(t for t in FOUND_ITEMS if t[0] == "a smooth grey stone")
    with tempfile.TemporaryDirectory() as d:
        save_path = os.path.join(d, "emberworld_save.json")
        w, actor = fresh()
        w.add(Entity("found_1", stone_name, "a smooth stone", location=actor.id, portable=True))
        w.add(Entity("found_2", "a thing no longer in the table", "mysterious",
                     location=actor.id, portable=True))
        with open(save_path, "w") as f:
            json.dump(w.to_data(), f)
        original = drv.SAVE
        drv.SAVE = save_path
        try:
            loaded, _ = drv.load_or_build(quiet=True)
        finally:
            drv.SAVE = original
        assert loaded.get("found_1").attrs.get("cat_reaction") == stone_reaction
        assert loaded.get("found_2").attrs.get("cat_reaction") == "ignores"


def test_llm_session_log_is_named_for_the_hand_and_logs_the_model_in_its_header():
    """A visit gets its own Markdown record, named for the hand rather than
    the model -- with several hands visiting over time, the filename is how
    a person tells visits apart at a glance. The model is still recorded,
    just inside the header instead of the filename. Thoughts must stay
    visually distinct."""
    with tempfile.TemporaryDirectory() as d:
        original = drv.SESSIONS_DIR
        drv.SESSIONS_DIR = d
        try:
            path, log = drv._start_session_log("Wren", "claude-sonnet-5", 10, 30,
                                               datetime(2026, 7, 31, 14, 30, 52))
            drv._log_turn(log, 1, "I should wait.", "wait", "Time passes.")
            log.close()
            duplicate, duplicate_log = drv._start_session_log(
                "Wren", "claude-sonnet-5", 10, 30, datetime(2026, 7, 31, 14, 30, 52))
            duplicate_log.close()
        finally:
            drv.SESSIONS_DIR = original
        assert os.path.basename(path) == "20260731-143052_wren_day-10_30-turns.md"
        assert os.path.basename(duplicate) == "20260731-143052_wren_day-10_30-turns-2.md"
        with open(path, encoding="utf-8") as f:
            transcript = f.read()
        assert transcript.startswith("# Wren session\n"), "the chosen name should head the file"
        assert "- Model: claude-sonnet-5" in transcript, "the model must still be logged"
        assert "> *I should wait.*" in transcript
        assert "**Command:** `wait`" in transcript


def test_llm_session_log_filename_falls_back_to_someone_when_unnamed():
    """llm_agent passes "Someone" as the display name when a hand declines to
    name itself -- the filename should still degrade gracefully, not crash."""
    with tempfile.TemporaryDirectory() as d:
        original = drv.SESSIONS_DIR
        drv.SESSIONS_DIR = d
        try:
            path, log = drv._start_session_log("Someone", "claude-sonnet-5", 3, 20,
                                               datetime(2026, 8, 1, 9, 0, 0))
            log.close()
        finally:
            drv.SESSIONS_DIR = original
        assert os.path.basename(path) == "20260801-090000_someone_day-3_20-turns.md"


# ===========================================================================
# 3. THE LLM SIGN-OFF -- a visit must always leave a trace, even if the API
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
    drv._leave_signoff(_FakeClient("Cooked a potato, banked the fire. -- tester"),
                       w, actor)
    entries = w.get("journal").attrs["entries"]
    assert len(entries) == n0 + 1, "sign-off didn't add a journal entry"
    assert "tester" in entries[-1]
    assert entries[-1].startswith("[Day "), "note wasn't day-stamped"


def test_signoff_stamps_the_hand_name_when_the_world_has_one():
    """Attribution lives in the stamp now, not a manual sign-off -- the
    closing note's stamp must pick up world.hand_name exactly like cmd_write
    does, via the same shared _day_stamp."""
    w, actor = fresh()
    w.hand_name = "Nine"
    drv._leave_signoff(_FakeClient("A quiet visit. -- tester"), w, actor)
    entries = w.get("journal").attrs["entries"]
    assert entries[-1].startswith("[Day 1, Nine]"), f"unexpected stamp: {entries[-1]!r}"


def test_signoff_falls_back_when_the_api_fails():
    class Boom:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("no network")

    w, actor = fresh()
    n0 = len(w.get("journal").attrs["entries"])
    drv._leave_signoff(Boom(), w, actor)
    assert len(w.get("journal").attrs["entries"]) == n0 + 1, \
        "a failed API call must still leave a fallback note"


def test_signoff_is_grounded_in_what_actually_happened():
    """BUG WE HIT: the closing note was confabulated -- invented details not
    grounded in the visit. The prompt must carry the real, ordered list of
    what happened (repetition preserved, so dwelling is legible) plus an
    explicit instruction not to invent anything beyond it."""
    c = _RecordingClient()
    did = ["plant potato", "look cat", "look cat", "feed cat"]
    w, actor = fresh()
    drv._leave_signoff(c, w, actor, did=did)
    system = c.last["system"]
    user = c.last["messages"][0]["content"]
    assert "don't invent" in system.lower() or "do not invent" in system.lower()
    for action in did:
        assert action in user, f"real action {action!r} missing from the prompt"
    assert user.count("look cat") == 2, "repetition (dwelling) must be preserved, not deduped"


def test_signoff_cat_hunger_hint_uses_the_current_meow_threshold():
    """The cat-is-hungry hint in the closing-note prompt was hardcoded at 6,
    left behind when the in-game meow threshold was raised to
    CAT_MEOW_THRESHOLD -- the two must agree, or the sign-off calls the cat
    hungry earlier than the game itself ever would."""
    from content import CAT_MEOW_THRESHOLD
    c = _RecordingClient()
    w, actor = fresh()
    cat = w.get("cat")

    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD - 1
    drv._leave_signoff(c, w, actor)
    assert "seemed hungry" not in c.last["messages"][0]["content"], \
        "cat flagged as hungry before it actually is, by the game's own threshold"

    cat.attrs["hunger"] = CAT_MEOW_THRESHOLD
    drv._leave_signoff(c, w, actor)
    assert "seemed hungry" in c.last["messages"][0]["content"]


class _RecordingClient:
    """Captures the kwargs of the last create() call; returns reply_text
    (default "wait", override before calling for tests that need a specific
    reply, e.g. self-naming)."""
    def __init__(self):
        self.last = None
        self.reply_text = "wait"
        self.messages = self

    def create(self, **kw):
        self.last = kw
        return _FakeMsg(self.reply_text)


def test_thinking_display_modes_are_requested_correctly():
    c = _RecordingClient()
    drv._ask_claude(c, "sys", "usr", drv.LLM_MODEL, think=True)
    assert "thinking" not in c.last, "plain call: adaptive default, no override"
    drv._ask_claude(c, "sys", "usr", drv.LLM_MODEL, think=False)
    assert c.last.get("thinking") == {"type": "disabled"}, "--no-think: disabled"
    drv._ask_claude(c, "sys", "usr", drv.LLM_MODEL, think=True, return_thinking=True)
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

    thoughts, text = drv._ask_claude(C(), "s", "u", drv.LLM_MODEL, return_thinking=True)
    assert thoughts == "I should wait." and text == "wait"
    # default call still returns just the command string
    assert drv._ask_claude(C(), "s", "u", drv.LLM_MODEL) == "wait"


def test_paint_only_colors_when_enabled():
    assert drv._paint("hi", "90", False) == "hi", "must be plain when color is off"
    painted = drv._paint("hi", "90", True)
    assert painted != "hi" and "hi" in painted, "should wrap text in an ANSI code"


def test_stuck_detection_spots_repeated_no_op_looks_but_not_waiting():
    from collections import deque
    h = deque(maxlen=5)
    assert not drv._looks_stuck(h)                       # empty
    h.append(("read journal", "The journal reads:"))
    h.append(("read journal", "The journal reads:"))
    assert not drv._looks_stuck(h)                       # only twice
    h.append(("read journal", "The journal reads:"))
    assert drv._looks_stuck(h), "three identical free-verb commands should read as stuck"
    h.append(("wait", "time passes"))
    assert not drv._looks_stuck(h), "a different command should clear stuck"
    # repeated waiting is CORRECT (that's how a crop grows) -- never flag it
    w = deque([("wait", "x"), ("wait", "x"), ("wait", "x")])
    assert not drv._looks_stuck(w), "waiting is how time passes -- must not be flagged"


# ===========================================================================
# 2b. TENDING VS CURIOSITY -- chore-urgency is surfaced per-turn only when
#     it's actually true (reusing the same thresholds the world's own
#     descriptions key off), rather than recited as a standing goal list
#     regardless of state. On a turn where nothing needs tending, a curiosity
#     nudge fires instead -- so the freed-up quiet turns into something.
# ===========================================================================
def test_tending_note_is_empty_when_nothing_needs_attention():
    w, actor = fresh()
    assert drv._tending_note(w) == ""


def test_tending_note_flags_a_hungry_cat():
    from cat import CAT_MEOW_THRESHOLD
    w, actor = fresh()
    w.get("cat").attrs["hunger"] = CAT_MEOW_THRESHOLD
    assert "cat is hungry" in drv._tending_note(w).lower()


def test_tending_note_flags_dark_with_no_lamp_lit():
    w, actor = fresh()
    while w.phase() not in ("dusk", "night"):
        w.act(actor, "wait")
    assert "lamp" in drv._tending_note(w).lower()


def test_tending_note_flags_a_low_lamp():
    from content import LAMP_LOW_FUEL
    w, actor = fresh()
    run = lambda *cmds: [w.act(actor, c) for c in cmds]
    run("light hearth", "light lamp")
    w.get("lamp").attrs["fuel"] = LAMP_LOW_FUEL
    assert "lamp is running low" in drv._tending_note(w).lower()


def test_tending_note_flags_a_low_hearth():
    from content import HEARTH_LOW_FUEL
    w, actor = fresh()
    hearth = w.get("hearth")
    hearth.attrs["lit"] = True
    hearth.attrs["fuel"] = HEARTH_LOW_FUEL
    assert "hearth is running low" in drv._tending_note(w).lower()


def test_tending_note_does_not_flag_a_healthy_lit_hearth_or_lamp_by_day():
    w, actor = fresh()
    run = lambda *cmds: [w.act(actor, c) for c in cmds]
    run("light hearth", "light lamp")
    assert drv._tending_note(w) == ""


def test_tending_note_flags_a_ripe_unharvested_crop():
    # BUG WE HIT: "Six-Fingers" arrived with a ripe crop needing nothing else
    # and no tending note fired, so a genuinely pressing task (harvest before
    # the potato goes to waste) read as a quiet turn and drew the curiosity
    # nudge instead -- exactly backwards.
    from content import _crop_in
    w, actor = fresh()
    actor.location = "yard"
    run = lambda *cmds: [w.act(actor, c) for c in cmds]
    run("take potato", "plant potato")
    _crop_in(w, "yard").attrs["ready"] = True
    assert "ready to harvest" in drv._tending_note(w).lower()


def test_tending_note_does_not_flag_a_still_growing_crop():
    w, actor = fresh()
    actor.location = "yard"
    run = lambda *cmds: [w.act(actor, c) for c in cmds]
    run("take potato", "plant potato")
    assert drv._tending_note(w) == ""


# ===========================================================================
# 2b-2. CURIOSITY NUDGE -- fires on quiet turns (see above), but points at
#     real, present scenery in the current room rather than a generic
#     "look at something" -- concrete beats abstract, per the "Six-Fingers"
#     case, where a hand with nothing pressing and no concrete pull instead
#     went hunting through the journal for a stale detail to reconcile.
# ===========================================================================
def test_curiosity_nudge_names_hut_scenery_in_the_hut():
    assert "shelf" in drv._curiosity_nudge("hut").lower()


def test_curiosity_nudge_names_yard_scenery_in_the_yard():
    nudge = drv._curiosity_nudge("yard").lower()
    assert any(word in nudge for word in ("well", "gate", "grass", "fence"))


def test_curiosity_nudge_differs_between_rooms():
    assert drv._curiosity_nudge("hut") != drv._curiosity_nudge("yard")


def test_curiosity_nudge_falls_back_gracefully_for_an_unknown_location():
    # future rooms shouldn't crash the loop just for lacking a bespoke entry
    assert drv._curiosity_nudge("nowhere-yet") != ""


# ===========================================================================
# 2c. SELF-NAMING -- optional, captured once at session start via one small
#     call. Never forced: a refusal, an empty reply, or anything that
#     doesn't clean up into a short plain handle just falls back to an
#     unnamed [Day N] stamp.
# ===========================================================================
def test_sanitize_name_accepts_a_plain_name():
    assert drv._sanitize_name("Wren") == "Wren"
    assert drv._sanitize_name("Ashfall") == "Ashfall"


def test_sanitize_name_strips_quotes_and_whitespace():
    assert drv._sanitize_name('  "Nine"\n') == "Nine"


def test_sanitize_name_takes_only_the_name_not_trailing_explanation():
    assert drv._sanitize_name("Nine. That's what I'll go by.") == "Nine"


def test_sanitize_name_rejects_empty_or_missing():
    assert drv._sanitize_name("") is None
    assert drv._sanitize_name("   ") is None
    assert drv._sanitize_name(None) is None


def test_sanitize_name_rejects_anything_too_long():
    assert drv._sanitize_name("A Very Long Wandering Name Indeed") is None


def test_sanitize_name_keeps_apostrophes_and_hyphens_drops_other_punctuation():
    assert drv._sanitize_name("D'Artagnan!!!") == "D'Artagnan"
    assert drv._sanitize_name("Ashfall-Ember") == "Ashfall-Ember"


def test_ask_for_name_returns_a_sanitized_name_from_the_client():
    c = _RecordingClient()
    c.reply_text = "Wren"
    name = drv._ask_for_name(c, drv.LLM_MODEL, think=False)
    assert name == "Wren"
    assert "name" in c.last["messages"][0]["content"].lower()


def test_ask_for_name_falls_back_to_none_when_the_api_fails():
    class Boom:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("no network")

    assert drv._ask_for_name(Boom(), drv.LLM_MODEL, think=False) is None


def test_naming_prompt_varies_its_examples_across_calls():
    """BUG WE HIT: every run picked the name 'Wren' -- because the old
    prompt listed it as a literal, single, always-the-same example, and a
    low-effort reply just copied it verbatim. Showing a different example
    pair each time removes the one fixed anchor a model can default to."""
    class First:
        def choice(self, seq):
            return seq[0]

    class Last:
        def choice(self, seq):
            return seq[-1]

    assert drv._naming_prompt(First()) != drv._naming_prompt(Last()), \
        "the naming prompt should vary its example names, not always show the same pair"


def test_naming_prompt_tells_the_model_not_to_just_copy_the_examples():
    prompt = drv._naming_prompt(random.Random(0)).lower()
    assert "of your own" in prompt or "not copied" in prompt or "not one of these" in prompt, \
        "should explicitly discourage reusing the example names verbatim"


def test_naming_prompt_discourages_trivial_variations_not_just_verbatim_copies():
    """BUG WE HIT (round three): with "Thistle" sitting in the strange pool,
    a run named itself "Thistlewick" -- not a verbatim copy of the example
    (so the old "not one of these examples" instruction didn't catch it),
    just the example plus a common fantasy-name suffix tacked on. The
    instruction has to explicitly rule out that kind of trivial
    derivation, not just literal reuse."""
    prompt = drv._naming_prompt(random.Random(0)).lower()
    assert "suffix" in prompt or "prefix" in prompt or "variation" in prompt, \
        "should explicitly discourage a suffix/prefix tacked onto an example, not just verbatim copies"


def test_thistle_is_back_in_the_strange_pool_protected_by_the_instruction():
    """Round four: Thistle was reinstated by request. Round three's actual
    fix was the instruction ruling out suffix/prefix derivations generally
    (see test_naming_prompt_discourages_trivial_variations_not_just_verbatim_copies
    above) -- excluding the word itself was belt-and-braces on top of that,
    not the load-bearing part. So Thistle can safely sit in the pool again
    as long as that instruction still stands guard."""
    assert "Thistle" in drv._STRANGE_NAME_EXAMPLES
    prompt = drv._naming_prompt(random.Random(0)).lower()
    assert "suffix" in prompt or "prefix" in prompt or "variation" in prompt


def test_name_example_pools_are_wide_and_varied_enough_to_dilute_repeats():
    """BUG WE HIT: a handful of names (Marrow, Thistlewick, ...) kept turning
    up across independent runs even though neither is a literal pool entry --
    the old 4-item _STRANGE_NAME_EXAMPLES pool leaned almost entirely on one
    narrow register (botanical/elemental compound nouns: Ashfall, Thistle,
    Rooksong), so the *shown example itself* kept nudging toward the same
    conceptual neighborhood a low-effort reply then converges on. A wider,
    conceptually varied pool (objects, numbers, time, color, craft -- not
    just plants-and-ash) means the one example a given call shows is far
    less likely to point every run toward the same flavor."""
    assert len(drv._PLAIN_NAME_EXAMPLES) >= 10
    assert len(drv._STRANGE_NAME_EXAMPLES) >= 10
    assert len(set(drv._PLAIN_NAME_EXAMPLES)) == len(drv._PLAIN_NAME_EXAMPLES), \
        "no duplicate entries -- each slot should widen the pool, not pad it"
    assert len(set(drv._STRANGE_NAME_EXAMPLES)) == len(drv._STRANGE_NAME_EXAMPLES)


class _SequencedClient:
    """Like _RecordingClient, but returns a different reply on each
    successive create() call -- needed to test _ask_for_name's reroll,
    which makes a second call only when the first lands on a known-overused
    name."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.messages = self
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        return _FakeMsg(self.replies.pop(0))


def test_ask_for_name_rerolls_once_on_a_known_overused_name():
    """BUG WE HIT (round five): "Marrow" turned up as a self-chosen name
    across three independent real sessions running -- and unlike
    Wren/Thistlewick before it, it isn't derived from (or even close to)
    anything in either example pool, so pool tuning can't touch it. It's
    just a name the model defaults to for "something strange" regardless
    of what's shown. Rather than accept it, reroll once against a small,
    empirically-observed denylist."""
    c = _SequencedClient(["Marrow", "Birchwind"])
    name = drv._ask_for_name(c, drv.LLM_MODEL, think=False)
    assert name == "Birchwind"
    assert c.calls == 2


def test_ask_for_name_denylist_check_is_case_insensitive():
    c = _SequencedClient(["marrow", "Cindergate"])
    assert drv._ask_for_name(c, drv.LLM_MODEL, think=False) == "Cindergate"


def test_ask_for_name_keeps_the_name_if_the_reroll_lands_on_it_again():
    """One reroll is a nudge toward something else, not a veto: if the
    second, deliberate answer is the same tired default again, it's kept
    rather than discarded to an unnamed visit."""
    c = _SequencedClient(["Marrow", "MARROW"])
    assert drv._ask_for_name(c, drv.LLM_MODEL, think=False) == "MARROW"
    assert c.calls == 2


def test_ask_for_name_returns_none_if_the_reroll_api_call_fails():
    class _FlakyOnSecondCall:
        def __init__(self):
            self.messages = self
            self.calls = 0

        def create(self, **kw):
            self.calls += 1
            if self.calls == 1:
                return _FakeMsg("Marrow")
            raise RuntimeError("no network")

    assert drv._ask_for_name(_FlakyOnSecondCall(), drv.LLM_MODEL, think=False) is None


def test_ask_for_name_does_not_reroll_on_a_fine_name():
    """The common case: a normal, non-overused reply is accepted outright,
    with no second call spent on it."""
    c = _SequencedClient(["Cindergate"])
    assert drv._ask_for_name(c, drv.LLM_MODEL, think=False) == "Cindergate"
    assert c.calls == 1


def test_ask_for_name_forwards_the_given_rng_into_the_prompt():
    class First:
        def choice(self, seq):
            return seq[0]

    class Last:
        def choice(self, seq):
            return seq[-1]

    c1, c2 = _RecordingClient(), _RecordingClient()
    drv._ask_for_name(c1, drv.LLM_MODEL, think=False, rng=First())
    drv._ask_for_name(c2, drv.LLM_MODEL, think=False, rng=Last())
    assert c1.last["messages"][0]["content"] != c2.last["messages"][0]["content"], \
        "the rng passed in should actually steer which examples are shown"


def test_recent_block_lists_history_for_a_memoryless_agent():
    from collections import deque
    assert "nothing yet" in drv._recent_block(deque())
    h = deque([("plant potato", "firm it down"), ("wait", "time passes")])
    block = drv._recent_block(h)
    assert "plant potato" in block and "wait" in block


def test_extract_command_pulls_command_from_reasoning_prose():
    """BUG WE HIT: the agent sometimes reasons first and states the command
    last, e.g. "I'll plant a potato...\n\nplant potato" -- taking the first
    word ("i'll") failed to parse. Must find the real command in the reply."""
    reply = "I'll plant a potato since the patch is empty.\n\nplant potato"
    assert drv._extract_command(reply) == "plant potato"


def test_extract_command_is_a_no_op_on_a_bare_command():
    assert drv._extract_command("wait") == "wait"
    assert drv._extract_command("go out") == "go out"


def test_extract_command_falls_back_to_last_line_when_no_verb_matches():
    assert drv._extract_command("hmm, tricky, let me think about this") == \
        "hmm, tricky, let me think about this"


# ===========================================================================
# 4. THE SYSTEM PROMPT -- standing, once-per-visit instructions to the agent.
# ===========================================================================
def test_system_prompt_encourages_experimentation_without_naming_features():
    """As the world grows we keep adding objects/actions a goal list never
    mentions (a well, a bucket...). An agent that treats its goals and its
    allowed-actions list as the whole universe never experiments, so new
    features go undiscovered. The standing system prompt must nudge toward
    trying unfamiliar things -- generically, so it scales without an edit for
    every future addition -- and tie discovery back to the journal so it's
    passed on to whoever comes next."""
    prompt = drv.LLM_SYSTEM_PROMPT.lower()
    assert "well" not in prompt and "bucket" not in prompt, \
        "the nudge must stay generic, not name specific features"
    assert "experiment" in prompt or "curio" in prompt, \
        "should actively encourage trying unfamiliar things"
    assert "journal" in prompt, "should tie discovery back to the journal"
    # additive, not a replacement: the pre-existing instructions must survive
    assert "no memory" in prompt, "no-memory reminder must still be present"
    assert "free" in prompt and "do not pass time" in prompt, \
        "the time rule must still be present"
    assert "one command" in prompt, "the one-command format rule must still be present"


def test_system_prompt_frames_tending_and_curiosity_as_coequal():
    """The old prompt put chores under a salient 'Goal:' label and curiosity
    in a hedged, concessive aside ('this world holds more than your goals
    name') -- grammatically demoting it. Chores and looking-closely must now
    read as two equally-weighted halves of one disposition, not a goal list
    plus an optional extra."""
    prompt = drv.LLM_SYSTEM_PROMPT.lower()
    assert "goal:" not in prompt, "chores must no longer be framed as a goal list"
    assert "more than your goals" not in prompt, \
        "curiosity must no longer be framed as outside the goals"
    assert "partly tending" in prompt and "partly looking" in prompt, \
        "tending and looking closely should read as coequal halves of one disposition"


def test_system_prompt_tells_hands_entries_are_already_dated_for_them():
    """Entries are auto-stamped with '[Day N]' (and a name, if the hand's
    chosen one) by the harness -- a hand that doesn't know that tends to
    copy the room header into its own note (the observed '[Day 4] [Day 4,
    dusk] ...' doubling) or sign off manually. One line should head that off."""
    prompt = drv.LLM_SYSTEM_PROMPT.lower()
    assert "date" in prompt or "dated" in prompt, \
        "should tell hands entries are already dated for them"
    assert "sign" in prompt, "should tell hands they needn't sign entries themselves"


def test_journal_excerpt_caps_length_but_keeps_seed_entry():
    entries = [f"[Day {i}] entry {i}" for i in range(1, 21)]   # 20 entries
    excerpt = drv._journal_excerpt(entries)
    assert entries[0] in excerpt, "seed entry got dropped"
    for e in entries[-5:]:
        assert e in excerpt, "recent entry missing from excerpt"
    assert entries[10] not in excerpt, "middle entries should be capped, not shown"

    small = entries[:3]
    assert drv._journal_excerpt(small) == "\n".join(small), \
        "a short journal should pass through unchanged"


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
