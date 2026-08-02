"""
test_drivers.py -- tests for the three drivers (human/random/LLM), the
persistence-loading glue, and the headless fuzzer.

Run it either way:
    python3 -m pytest test_drivers.py -v      # if you have pytest
    python3 test_drivers.py                    # if you don't (built-in runner)

The LLM sign-off tests use fake Anthropic clients -- no network, no key needed.
"""

import json
import os
import tempfile
from datetime import datetime

import drivers as drv
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


def test_llm_session_log_uses_descriptive_name_and_italic_thoughts():
    """A visit gets its own Markdown record; thoughts must be visually distinct."""
    with tempfile.TemporaryDirectory() as d:
        original = drv.SESSIONS_DIR
        drv.SESSIONS_DIR = d
        try:
            path, log = drv._start_session_log("Claude Sonnet 5", 10, 30,
                                               datetime(2026, 7, 31, 14, 30, 52))
            drv._log_turn(log, 1, "I should wait.", "wait", "Time passes.")
            log.close()
            duplicate, duplicate_log = drv._start_session_log(
                "Claude Sonnet 5", 10, 30, datetime(2026, 7, 31, 14, 30, 52))
            duplicate_log.close()
        finally:
            drv.SESSIONS_DIR = original
        assert os.path.basename(path) == "20260731-143052_claude-sonnet-5_day-10_30-turns.md"
        assert os.path.basename(duplicate) == "20260731-143052_claude-sonnet-5_day-10_30-turns-2.md"
        with open(path, encoding="utf-8") as f:
            transcript = f.read()
        assert "> *I should wait.*" in transcript
        assert "**Command:** `wait`" in transcript


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
    """Captures the kwargs of the last create() call, returns a fixed reply."""
    def __init__(self):
        self.last = None
        self.messages = self

    def create(self, **kw):
        self.last = kw
        return _FakeMsg("wait")


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
