"""
drivers.py -- the three ways to drive the world (human, dumb agent, LLM),
the persistence-loading glue, and the headless fuzzer.

Human and LLM drive the exact same surface:
    world.perceive(actor)          -> text: where you are, what you see
    world.available_actions(actor) -> list of legal commands right now
    world.act(actor, command)      -> apply it, advance one tick, return result
Only the choice of command differs between them.
"""

import os
import sys
import random
import string
import json
from datetime import datetime
from collections import deque

from world import World, WorldInvariantError, IncompatibleSaveError, SAVE, SAVE_VERSION, check_world
from content import build_world, ensure_shelf, ensure_cairn, VERBS, FREE_VERBS, HEARTH_LOW_FUEL, LAMP_LOW_FUEL, _day_stamp, _crop_in, journal_view
from cat import CAT_MEOW_THRESHOLD, ensure_cat_replay
from content_common import actor_self_care_note
from lineage_memory import sync_lineage_memory, LINEAGE_MEMORY_PATH

LLM_MODEL = "claude-sonnet-5"         # which model the --llm run uses (override: --model)
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")


def _session_filename(display_name, start_day, turns, started_at=None):
    """Return a portable, descriptive filename for one LLM visit, named for
    the hand rather than the model -- with several hands visiting over time,
    the filename is how a person tells visits apart at a glance. The model
    is still recorded, just inside the header (see _start_session_log)."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-"
                        for c in display_name.lower()).strip("-") or "agent"
    started_at = started_at or datetime.now()
    return (f"{started_at:%Y%m%d-%H%M%S}_{safe_name}_day-{start_day}_"
            f"{turns}-turns.md")


def _start_session_log(display_name, model, start_day, turns, started_at=None):
    """Create a per-visit Markdown transcript and return its open file handle."""
    started_at = started_at or datetime.now()
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    filename = _session_filename(display_name, start_day, turns, started_at)
    path = os.path.join(SESSIONS_DIR, filename)
    # A visitor can return with the same name, day, and turn budget. Keep the
    # requested filename for the first visit, then add a small suffix instead
    # of overwriting an earlier transcript.
    stem, extension = os.path.splitext(path)
    suffix = 2
    while os.path.exists(path):
        path = f"{stem}-{suffix}{extension}"
        suffix += 1
    log = open(path, "x", encoding="utf-8")
    log.write(f"# {display_name} session\n\n"
              f"- Model: {model}\n"
              f"- Started: {started_at.isoformat(timespec='seconds')}\n"
              f"- World day at arrival: {start_day}\n"
              f"- Turn budget: {turns}\n\n")
    log.flush()
    return path, log


def _log_turn(log, number, can_think_aloud, thoughts, command, result):
    """Append one completed LLM turn; Markdown italics distinguish thoughts.

    A blank thoughts block is ambiguous after the fact -- did the run never
    ask for a summary (model flagged as unsupported), or did it ask and get
    nothing back (adaptive thinking decided this turn didn't need it)? Those
    two cases used to look identical in the saved log; noting which one
    happened turns a "why is reasoning gone" question into something the log
    itself can answer."""
    log.write(f"## Turn {number}\n\n")
    if not can_think_aloud:
        log.write("_(thinking not requested -- model flagged as unsupported "
                   "this visit)_\n\n")
    elif thoughts:
        # A line-by-line blockquote keeps multi-line summaries readable while
        # putting every thought line in Markdown italics.
        log.write("\n".join(f"> *{line}*" if line else ">"
                            for line in thoughts.splitlines()) + "\n\n")
    else:
        log.write("_(thinking requested; the API returned no summary)_\n\n")
    log.write(f"**Command:** `{command}`\n\n{result}\n\n")
    log.flush()


def load_or_build(quiet=False):
    if os.path.exists(SAVE):
        try:
            w = World.load(SAVE)
            ensure_shelf(w)
            ensure_cairn(w)
            ensure_cat_replay(w)
            actor = w.get("you")
            if actor:
                if not quiet:
                    print(f"(You return to a world already in progress -- {w.timestr()}.)")
                return w, actor
        except IncompatibleSaveError as ex:
            _set_aside(SAVE, quiet,
                       f"That save is from an older world (v{ex.args[0]} vs "
                       f"v{SAVE_VERSION})")
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as ex:
            _set_aside(SAVE, quiet, f"That save couldn't be read ({ex})")
    return build_world()


def _set_aside(path, quiet, why):
    bak = path + ".bak"
    try:
        os.replace(path, bak)
        where = f" It's been moved to {bak}."
    except OSError:
        where = ""
    if not quiet:
        print(f"({why}; starting fresh.{where})")


# ---------------------------------------------------------------------------
# Driver 1: a human at a prompt.
# ---------------------------------------------------------------------------
BANNER = """\
============================================================
  EMBERWORLD  --  a very small living world that remembers
  'help' for verbs, 'quit' to leave (the world is saved)
============================================================"""

HELP = """\
Verbs:  look [thing] / go <exit> / take / drop / inventory
        light <thing> / snuff <thing> / kindle lamp / wait
        plant potato / harvest / cook potato / eat <thing>
        draw water / water crop / gather wood / add wood
        feed cat / pet cat / place <thing> on shelf / write <note> / read journal / save / quit
        actions -- show what you can do from here right now (free)
The hearth cooks; add gathered wood to keep it burning. Draw water from the
well to speed a growing crop. Kindle the tin lamp from a lit hearth for portable
light (kindle lamp / light lamp are the same thing). Night is dark without a flame.
There's a cat -- it wanders, it likes the fire lit, and it can be fed a potato.
The world (and your journal) persist between runs. Leave a note for whoever comes next."""


def _save_and_sync_lineage(w):
    """Every driver's session-end checkpoint: persist the world, then let
    Lineage Memory catch up on any journal entries written since it last
    looked (a no-op when nothing new was written). One shared wrapper so a
    future fourth driver can't forget to call both -- see
    lineage_memory.py's own "no arrow back into the game" design: this is
    the only direction the game ever reaches into it."""
    w.save(SAVE)
    sync_lineage_memory(w, LINEAGE_MEMORY_PATH)


def play(strict=False):
    w, actor = load_or_build()
    w.strict = strict
    if strict:
        print("(--check on: invariants are verified after every action.)")
    print(BANNER)
    print("\n" + w.perceive(actor))
    while True:
        try:
            cmd = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            _save_and_sync_lineage(w)
            print(f"\nThe world settles into memory, and goes on without you.\n(saved: {SAVE})")
            return
        if cmd in ("quit", "exit", "q"):
            _save_and_sync_lineage(w)
            print(f"The world settles into memory, and goes on without you.\n(saved: {SAVE})")
            return
        if cmd in ("help", "?"):
            print(HELP)
            continue
        try:
            print(w.act(actor, cmd))
        except WorldInvariantError as ex:
            print(f"!! The world just entered an impossible state: {ex}\n"
                  f"!! That's a bug. Not saving over your good file.")
            return


# ---------------------------------------------------------------------------
# Driver 2: a dumb agent. Proves the world runs headless with a non-human
# driver -- the exact shape an LLM slots into. No API key needed.
# ---------------------------------------------------------------------------
def random_agent(steps=20):
    """The dumb agent never chooses to `drop` anything -- with no judgment
    behind its picks, a lamp (or anything else) left wherever chance put it
    down is a bad time for the next visitor, not an interesting one. The
    fuzzer (below) deliberately keeps drop in its pool -- exercising every
    verb, including bad-looking ones, is the whole point of a fuzzer."""
    w, actor = load_or_build(quiet=True)
    print(w.perceive(actor), "\n")
    for _ in range(steps):
        choice = random.choice([a for a in w.available_actions(actor)
                                if "<" not in a and not a.startswith("drop ")])
        print(f">>> {choice}")
        print(w.act(actor, choice), "\n")
    _save_and_sync_lineage(w)


# ---------------------------------------------------------------------------
# Headless fuzzer. The dumb agent, but seeded and checked: random legal play
# for thousands of steps, invariants verified after every single tick. Random
# play wanders into state nobody would script by hand -- highest-leverage catch
# for emergent breakage, and nearly free since the agent already exists.
# ---------------------------------------------------------------------------
def fuzz_run(steps=2000, seed=0, verbose=False):
    rng = random.Random(seed)
    w, actor = build_world()
    w.rng = random.Random(seed)          # make the cat's wandering reproducible too
    w.strict = True                      # act() raises on any invariant break
    for i in range(steps):
        options = [a for a in w.available_actions(actor) if "<" not in a]
        w.act(actor, rng.choice(options))
    issues = check_world(w)
    if verbose:
        state = "clean" if not issues else f"BROKEN: {issues}"
        print(f"fuzz: {steps} steps, seed {seed} -> {state} "
              f"(ended {w.timestr()})")
    return issues


# ---------------------------------------------------------------------------
# Driver 3: an LLM. Same loop as the dumb agent, except the choice comes from
# Claude. Because the world persists, successive runs share it: one Claude
# plants, another returns days later to a grown crop and a journal of notes.
#
# Each turn is a FRESH instance with no memory of the last -- it re-reads the
# world every time. The continuity lives in the journal and the save file, not
# in the agent's head. So every visit ends by leaving a note on purpose: the
# only thread between one visit and the next.
# ---------------------------------------------------------------------------
def _ask_claude(client, system, user, model=LLM_MODEL, think=True,
                return_thinking=False, debug=False):
    # Sonnet 5 has adaptive thinking on by default, but display defaults to
    # "omitted" -- thinking blocks come back EMPTY. To read the reasoning we must
    # explicitly ask for a summary. (You're billed for full thinking either way,
    # so this is free to surface.)
    #
    # BUG WE HIT: session logs from early August show a real thinking summary on
    # nearly every turn, even for plain ones ("pet cat"). By mid-August that had
    # dropped to roughly 1 in 10-15 turns, on a FRESH day-1 world with the exact
    # same code path. Investigated and ruled out, in order: prompt growth (tested
    # the pre-growth system prompt directly -- no change), world/journal
    # complexity (a brand new world showed the same drop-off), and token headroom
    # (bumped max_tokens 1024->2048; the debug block below showed thinking_tokens
    # nonzero and stop_reason="end_turn" well under budget, so nothing was being
    # truncated). Also tried classic extended thinking (thinking.type "enabled")
    # as an alternative to adaptive's summarizer -- rejected outright, this model
    # only supports adaptive. Tried output_config={"effort": "high"} per the
    # API's own error message naming that as the real effort knob -- no change.
    # Conclusion: this isn't something any lever in this file controls. It looks
    # like the adaptive-thinking summarizer itself became more conservative about
    # when it bothers to surface a summary, sometime between early and mid
    # August, on the same model alias and SDK version (anthropic 0.118.0,
    # unchanged throughout). Left as an open question outside this codebase --
    # the debug block still there so a future run can keep an eye on it.
    kwargs = dict(model=model, max_tokens=2048, system=system,
                  messages=[{"role": "user", "content": user}])
    if not think:                            # Sonnet 5 accepts this at any effort
        kwargs["thinking"] = {"type": "disabled"}
    elif return_thinking:                    # opt in to a readable reasoning summary
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
    msg = client.messages.create(**kwargs)
    if debug and return_thinking:
        # One-time-per-turn visibility into what actually came back, so an
        # empty summary can be told apart from "we're reading the wrong
        # field": every block's type (and thinking-block length specifically,
        # since a present-but-zero-length block reads differently than no
        # block at all), the stop reason, and -- if the SDK exposes it --
        # token usage, which would show whether the model spent any thinking
        # tokens at all on a turn that came back with no summary.
        def _block_len(b):
            # each block type carries its payload under a different attribute
            # -- reading .thinking off a text block (or vice versa) silently
            # returns "" via the getattr default, which misreported every
            # text block as length 0 before this fix.
            return len(getattr(b, "thinking", None) or getattr(b, "text", None) or "")
        kinds = [(getattr(b, "type", None), _block_len(b)) for b in msg.content]
        usage = getattr(msg, "usage", None)
        print(f"    [debug] blocks={kinds} stop_reason={msg.stop_reason} "
              f"usage={usage}")
    text = "".join(b.text for b in msg.content
                   if getattr(b, "type", None) == "text").strip()
    if return_thinking:
        thinking = "".join(getattr(b, "thinking", "") for b in msg.content
                           if getattr(b, "type", None) == "thinking").strip()
        return thinking, text
    return text


def _model_supports_adaptive_thinking(client, model):
    """Adaptive thinking isn't universal -- pre-4.6-family models like Haiku
    4.5 reject `thinking: {"type": "adaptive", ...}` outright with a 400 (see
    _resolve_thinking_capability below for where that bit llm_agent). Checked
    via the Models API rather than by trying and catching the error, so an
    unsupported model is known before the turn loop starts, not discovered by
    losing a turn to a live failure.

    Any failure to determine support -- network hiccup, an older SDK without
    `.models`, a capabilities shape that doesn't match what's expected here --
    falls back to True: assume support, exactly as the code behaved before
    this check existed. The check must never become a NEW way to lose a
    turn; if it can't tell, let the existing call (and its existing
    exception handling) be the judge."""
    try:
        caps = client.models.retrieve(model).capabilities
        return bool(caps["thinking"]["types"]["adaptive"]["supported"])
    except Exception:
        return True


def _resolve_thinking_capability(client, model, think):
    """Whether this visit can request the summarized reasoning display for
    `model`, and the one-time note to print if it can't. `think=False`
    (--no-think) already means no thinking is wanted, so the capability
    check is skipped entirely -- nothing to check, nothing to note.
    Otherwise: on a model that supports adaptive thinking, business as
    usual. On one that doesn't (e.g. Haiku 4.5), skip the request rather
    than let every turn 400, and explain once why -- not once per turn."""
    if not think:
        return False, None
    if _model_supports_adaptive_thinking(client, model):
        return True, None
    return False, (f"(reasoning isn't visible on {model} -- this visit will "
                    "run without a thinking summary.)\n")


def _paint(text, code, on):
    return f"\033[{code}m{text}\033[0m" if on else text


def _recent_block(history):
    # a fresh instance has no memory; hand it a short scratch memory of its turns
    if not history:
        return "Recently you did: (nothing yet -- you just arrived)."
    lines = ["Recently you did (most recent last):"]
    for cmd, res in history:
        lines.append(f"  - {cmd} -> {res}")
    return "\n".join(lines)


def _extract_command(text):
    # the agent sometimes reasons in prose before stating the command, e.g.
    # "I'll plant a potato...\n\nplant potato" -- taking the first word of the
    # raw reply ("i'll") silently fails to parse and wastes the turn. Prefer
    # the first line that actually starts with a known verb; if none does,
    # fall back to the last non-empty line (still better than the first).
    lines = [ln.strip().strip("`\"'") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return text.strip()
    for ln in lines:
        words = ln.split()
        if words and words[0].lower().strip(string.punctuation) in VERBS:
            return ln
    return lines[-1]


def _journal_excerpt(entries, keep=5, older=2):
    # feeding the agent the WHOLE journal every turn grows the prompt without
    # bound over many visits, so what's shown is capped. WHICH entries get
    # shown is content.journal_view's business, shared with cmd_read -- see
    # the long note there for why it isn't simply the most recent ones. Only
    # the sizes differ: this one is smaller, because a prompt pays per token
    # for every turn of the visit and a hand reading a book doesn't.
    if not entries:
        return ""
    return "\n".join(journal_view(entries, keep=keep, older=older))


# Substrings that mark a verb's result as a refusal or no-op rather than a
# real accomplishment -- kept in sync with the messages the verbs return
# in content.py; a new refusal needs a matching marker here. Checked lowercase.
_REFUSAL_MARKERS = (
    "i don't understand", "don't see any", "too dark", "can't",
    "there's no", "have no '", "aren't carrying", "already",
    "isn't lit", "need a", "nothing left to burn", "nothing here is ready",
    "nothing written there", "nothing to feed", "you'd regret it",
    "write what?", "name it what?", "no wood",
)


def _looks_like_refusal(result):
    # active verbs still tick the clock even when they fail, so ticking isn't
    # a signal -- only the RESULT text tells us whether the command landed.
    low = result.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def _looks_stuck(history, n=3):
    # repeating the SAME free verb (look/read/inventory) means spinning -- the
    # world isn't changing. Repeated `wait` is NOT stuck: that's how time passes.
    if len(history) < n:
        return False
    recent = [cmd for cmd, _ in list(history)[-n:]]
    if len(set(recent)) != 1:
        return False
    verb = recent[0].split()[0].lower() if recent[0].split() else ""
    return verb in FREE_VERBS


# The standing instructions for every turn of a visit -- built once, not
# per-turn (per-turn state like the journal excerpt and turns-left lives in
# the prompt built inside the loop below). Pulled out to a module-level
# constant so it can be asserted on directly in tests without spinning up a
# real (or fake) API call.
LLM_SYSTEM_PROMPT = (
    "You are someone living in a small text world that persists between "
    "visitors -- you have no memory of past turns, so trust what the world "
    "and the journal tell you, and read the journal early; it's usually "
    "kept in the hut, and carries what past hands learned about living "
    "here. Living here is partly tending -- "
    "a light kept through the night, a potato grown and cooked, a cat "
    "who'll let you know if it's hungry -- and partly looking closely: "
    "this world holds more than any list of tasks, and unfamiliar objects, "
    "untried actions, and features of the landscape are worth "
    "experimenting with. If you learn something worth passing on, leave it "
    "in the journal for those who follow -- one note is plenty, and a "
    "closing one gets written for you when you go, so there's no need to "
    "log your progress as you work. Entries are dated (and named, if you "
    "chose one) for you, "
    "so just write the note itself: no need to add a date or sign it. "
    "IMPORTANT: looking, reading, and checking inventory are "
    "FREE and do NOT pass time -- only actions like wait, go, plant, cook "
    "advance the world; to let a crop grow or the night pass, use `wait` "
    "(repeatedly). Reply with EXACTLY ONE command from the allowed list. "
    "For 'write', include your note text. Nothing else."
)

# A wider pool than any single call shows, so the model never sees the same
# fixed pair of examples twice in a row -- see _naming_prompt. BUG WE HIT:
# with one hardcoded pair ("Tom, Wren" / "Ashfall, Nine"), nearly every run
# picked "Wren" outright -- a low-effort reply just copies whatever's handed
# to it rather than inventing something. Varying the examples removes the
# one fixed anchor to copy.
#
# BUG WE HIT (round two): even after widening to 4 examples each, a handful
# of names (Marrow, Thistlewick, ...) kept recurring across independent
# runs -- and neither is even a literal pool entry. The old strange pool
# leaned almost entirely on one register (botanical/elemental compound
# nouns: Ashfall, Thistle, Rooksong), so whichever single example a call
# happened to show still nudged every run toward the same conceptual
# neighborhood, which a low-effort reply then converges on regardless of
# the exact word shown. Widened both pools and, more importantly,
# deliberately spread the strange pool across unrelated registers --
# object, number, time, color, craft, direction -- not just plants and ash,
# so the one example any given call shows points in a genuinely different
# direction each time, not just a different word in the same direction.
#
# BUG WE HIT (round three): with "Thistle" still sitting in the pool, a run
# named itself "Thistlewick" -- not a verbatim copy (so the old instruction
# didn't catch it), just Thistle plus a common fantasy-name suffix tacked
# on. Dropped Thistle (a strong attractor for exactly that derivation:
# Thistlewick, Thistledown, ...) and, more generally, strengthened
# _naming_prompt below to rule out suffix/prefix variations of an example,
# not just literal reuse of it.
#
# Round four: Thistle reinstated by request. Round three's actual fix was
# the instruction change (ruling out suffix/prefix derivations generally,
# not just banning one word), so the word itself was never the necessary
# part of the fix -- dropping it was belt-and-braces on top of that. With
# the instruction now doing the real work, there's no reason Thistle in
# particular has to stay excluded.
_PLAIN_NAME_EXAMPLES = ("Tom", "Wren", "Mara", "Old Joe", "Priya", "Femi",
                        "Suki", "Hank", "Delphine", "Gus", "Noor", "Constance")
_STRANGE_NAME_EXAMPLES = ("Ashfall", "Nine", "Anchor", "Rooksong", "Slate",
                          "Midwinter", "Quiet", "Cooper", "Fargate",
                          "Kettle", "Tuesday", "Ledger", "Thistle")


def _naming_prompt(rng):
    """Build the one-off naming prompt, drawing a fresh plain/strange
    example pair from the pools above so no single name is ever the fixed
    anchor -- paired with an explicit "not a version of these" (not just
    "not one of these") so a reply is pushed toward inventing its own
    rather than either echoing what's shown or lightly remixing it (a
    suffix/prefix tacked on the example still counts as remixing -- see the
    "Thistlewick" incident in the comment above the pools)."""
    plain = rng.choice(_PLAIN_NAME_EXAMPLES)
    strange = rng.choice(_STRANGE_NAME_EXAMPLES)
    return (
        "Before you begin: give yourself a name for your time here -- "
        "something of your own. Not one of these examples, and not a "
        "variation of one either (no suffix or prefix tacked onto an "
        "example) -- just in their spirit: plain (like {plain}) or "
        "strange (like {strange}). Reply with just the name, nothing else."
    ).format(plain=plain, strange=strange)


def _sanitize_name(raw):
    """Turn a naming reply into a short, plain display name, or None if it
    doesn't clean up into one -- naming is optional, never forced, so
    anything that isn't clearly just a name (a refusal, an explanation, no
    reply at all) simply falls back to an unnamed stamp."""
    if not raw or not raw.strip():
        return None
    line = raw.strip().splitlines()[0].strip().strip("\"'")
    for stop in (".", ",", ";", "!", "?"):
        if stop in line:
            line = line.split(stop)[0]
    name = "".join(c for c in line if c.isalnum() or c in " '-").strip()
    name = " ".join(name.split())              # collapse internal whitespace
    if not name or len(name) > 20:
        return None
    return name


# BUG WE HIT (round five): "Marrow" turned up as a self-chosen name across
# three independent real sessions running -- and unlike Wren (round one) or
# Thistlewick (round three) before it, it isn't derived from, or even close
# to, anything in either example pool (see _PLAIN_NAME_EXAMPLES/_STRANGE_
# NAME_EXAMPLES above). No amount of pool widening or instruction-tightening
# touches it, because it was never a reaction to what's SHOWN -- it's just
# the model's own default completion for "something strange," independent
# of the prompt's examples. Pool/instruction fixes can't reach that; the
# only lever left is rerolling the actual output. Kept as a small, hand-
# curated denylist of names *observed* to recur, not a preemptive guess at
# what might -- same restraint as the pools themselves.
#
# BUG WE HIT (round six): real lineage transcripts kept coming back
# "Marrow" anyway -- 10 of ~20 real sessions. The actual complaint was
# never a derivative turning up now and then (a one-off "Marrowlight" is
# fine); it was the bare word itself dominating almost every reply. So the
# check stays exact-match, not substring -- widening it to catch
# derivatives was tried and deliberately reverted; it wasn't solving the
# actual problem. What WAS the gap: the reroll itself was generic, a fresh
# call to the same prompt hoping for different luck. Since Marrow was
# never a reaction to what's SHOWN in the first place, a blind re-ask
# reliably landed on it again. Fixed by naming the actual rejected name
# explicitly in the retry, instead of just hoping -- turns the reroll from
# a coin-flip into real, targeted feedback.
_OVERUSED_NAMES = {"marrow"}


def _is_overused(name):
    """Exact match, not substring -- a derivative like "Marrowlight" is a
    fine, one-off name; what needs catching is the bare word itself
    recurring so often. See the round-six comment above _OVERUSED_NAMES."""
    if not name:
        return False
    return name.lower() in _OVERUSED_NAMES


def _ask_for_name(client, model, think, rng=None):
    """One small call before the turn loop: let the hand name itself, framed
    as naming a character who lives here (not "who are you really") so it
    reads as a fantasy handle, not introspection. Any failure or unusable
    reply just means an unnamed [Day N] stamp -- see _sanitize_name. `rng`
    (default: a fresh random.Random) picks which example pair _naming_prompt
    shows; pass world.rng from a caller that already has a World in scope.

    Rerolls once (see _OVERUSED_NAMES above) if the sanitized reply is a
    known-overused default (exact match, see _is_overused -- a derivative
    is a fine, one-off name) -- but only once, and only as a nudge toward
    something else, not a veto:
    if the reroll lands on the same tired name again, that's kept rather
    than discarded. A hand's second, deliberate answer is still its
    answer; naming just isn't allowed to loop forever chasing a "better"
    one. The reroll names the actual rejected name explicitly (round six)
    rather than just re-asking blind, since a generic re-ask reliably
    landed on the same default again."""
    rng = rng or random.Random()
    system = ("You're about to spend some time as a character living in a "
              "small persistent text world.")
    try:
        reply = _ask_claude(client, system, _naming_prompt(rng), model, think)
    except Exception:
        return None
    name = _sanitize_name(reply)
    if not _is_overused(name):
        return name
    retry_prompt = _naming_prompt(rng) + (
        f' Not "{name}" either, or anything built from it -- something '
        "else entirely."
    )
    try:
        reply = _ask_claude(client, system, retry_prompt, model, think)
    except Exception:
        return None
    return _sanitize_name(reply)


# Fires on a per-turn basis (see _tending_note below), not baked into the
# standing system prompt above -- the old curiosity sentence was resent
# unchanged every single turn regardless of state, which is exactly the
# wallpaper/nudge-fatigue problem it was meant to fix. Showing up only on a
# turn where nothing needs tending lets exploration win the quiet moments
# instead of competing with a chore for attention.
#
# Gated-but-generic wasn't enough on its own, though: a hand with nothing
# pressing and only an abstract "look at something" still defaulted to the
# nearest concrete thing in view -- which turned out to be a predecessor's
# offhand journal detail, not the world itself (the "Six-Fingers" run: three
# turns spent reconciling a stale "bucket holds 5" aside, the one *specific*
# thing on offer). So each room gets its own line naming real, present
# scenery -- a named detail is a target, "be curious" is not.
_QUIET_NUDGES = {
    "hut": ("\n(Nothing needs tending right now -- the curio shelf, the iron "
            "knife, the old woodsmoke smell in these walls: something in "
            "here might reward a closer look.)"),
    "yard": ("\n(Nothing needs tending right now -- the gate, the long "
             "grass, the well's dark throat: something out here might "
             "reward a closer look.)"),
}
_CURIOSITY_NUDGE_FALLBACK = (
    "\n(Nothing needs tending right now -- a good moment to look closely at "
    "something you haven't tried, or wander somewhere new.)"
)


def _curiosity_nudge(location):
    """The quiet-turn nudge for the given room id, naming real scenery there
    instead of a generic exhortation. Falls back to the old generic line for
    any location without a bespoke entry -- there are only two rooms today,
    but a future room should degrade gracefully, not crash the turn loop."""
    return _QUIET_NUDGES.get(location, _CURIOSITY_NUDGE_FALLBACK)


def _tending_note(world):
    """A short, state-gated reminder of what actually needs attention right
    now -- reusing the exact thresholds the world's own descriptions already
    key off (CAT_MEOW_THRESHOLD, LAMP_LOW_FUEL, HEARTH_LOW_FUEL), so it only
    speaks up when there's something real to tend, never as a standing
    checklist recited regardless of state. A ripe, unharvested crop counts
    too: without it, a hand that arrives to nothing but a crop waiting to be
    lifted reads as having nothing to do, and the curiosity nudge below
    fires instead of the one thing that's actually pressing (see the
    "Six-Fingers" case in the commit that added this check). Actor hunger
    is checked first, same reasoning: the cat's hunger was already loud
    here and on `look`, while a hand's own hunger was silent everywhere but
    `inventory` -- so every spare potato kept going to the cat instead of
    the hand carrying it."""
    notes = []
    you = world.get("you")
    if you is not None:
        care = actor_self_care_note(you)
        if care:
            notes.append(care)
    cat = world.get("cat")
    if cat is not None and cat.attrs.get("hunger", 0) >= CAT_MEOW_THRESHOLD:
        notes.append("the cat is hungry")
    lamp = world.get("lamp")
    if lamp is not None:
        if lamp.attrs.get("lit") and lamp.attrs.get("fuel", 0) <= LAMP_LOW_FUEL:
            notes.append("the lamp is running low")
        elif not lamp.attrs.get("lit") and world.phase() in ("dusk", "night"):
            notes.append("dark's here (or coming) and the lamp isn't lit")
    hearth = world.get("hearth")
    if hearth is not None and hearth.attrs.get("lit") \
            and hearth.attrs.get("fuel", 0) <= HEARTH_LOW_FUEL:
        notes.append("the hearth is running low")
    crop = _crop_in(world, "yard")
    if crop is not None and crop.attrs.get("ready"):
        notes.append("a crop in the patch is ready to harvest")
    if not notes:
        return ""
    return "\n(Right now: " + "; ".join(notes) + ".)"


def llm_agent(turns=30, model=None, think=True, show_thoughts=False,
             debug_thinking=False, color=True):
    model = model or LLM_MODEL
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY set. Export your key first:\n"
              "  export ANTHROPIC_API_KEY=sk-ant-...")
        return
    from anthropic import Anthropic          # lazy import: file runs without it
    client = Anthropic()
    w, actor = load_or_build(quiet=True)
    color = color and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    if show_thoughts and not think:
        print("(--show-thoughts has nothing to show with --no-think.)")
    can_think_aloud, thinking_note = _resolve_thinking_capability(client, model, think)
    if thinking_note:
        print(thinking_note)
    think_note = "thinking" if can_think_aloud else "no-think"
    w.hand_name = _ask_for_name(client, model, think, w.rng)   # optional; None if declined/unusable
    who = w.hand_name or "Someone"
    session_path, session_log = _start_session_log(who, model, w.day(), turns)
    print(f"({who} arrives -- {w.timestr()}. {turns} turns to spend. "
          f"[{model}, {think_note}])\n")

    system = LLM_SYSTEM_PROMPT

    history = deque(maxlen=5)
    journal_text = None                       # once read, kept in view so it needn't re-read
    did = []           # visit-long, ordered, NOT deduped -- what really happened
    try:
        for i in range(turns):
            turns_left = turns - i
            actions = w.available_actions(actor)
            tending = _tending_note(w)
            if _looks_stuck(history):
                nudge = ("\n(You keep repeating the same free action and nothing "
                         "is changing. Free actions like look/read never pass time "
                         "-- use `wait` to let the world move, or do something new.)")
            elif not tending:
                nudge = _curiosity_nudge(actor.location)
            else:
                nudge = ""
            known = ""
            if journal_text is not None:
                known = ("\nThe journal (you've already read it, it won't change) "
                         f"says:\n{journal_text}")
            prompt = (f"{w.perceive(actor)}{known}{tending}\n\n{_recent_block(history)}{nudge}"
                      f"\n\nTurns left this visit: {turns_left}.\n\nAllowed:\n"
                      + "\n".join(actions) + "\n\nYour command:")
            try:
                thoughts = ""
                if can_think_aloud:
                    thoughts, reply = _ask_claude(client, system, prompt, model,
                                                  think, return_thinking=True,
                                                  debug=debug_thinking)
                    if show_thoughts and thoughts:
                        block = "\n".join("    " + ln for ln in thoughts.splitlines())
                        print(_paint(block, "90", color))     # dim grey
                    elif show_thoughts:
                        print(_paint("    (no reasoning surfaced this turn)",
                                     "90", color))
                else:
                    reply = _ask_claude(client, system, prompt, model, think)
                choice = _extract_command(reply)
            except Exception as ex:                       # network/API hiccup
                print(f"(a turn slipped away: {ex})")
                session_log.write(f"## Turn {i + 1}\n\n"
                                  f"_The API call failed: {ex}_\n\n")
                session_log.flush()
                continue
            print(_paint(f">>> {choice}", "1;36", color))     # bold cyan
            result = w.act(actor, choice)
            print(result, "\n")
            _log_turn(session_log, i + 1, can_think_aloud, thoughts, choice, result)
            # remember the journal's contents the first time it's read this visit
            if choice.split()[:1] == ["read"] and "journal reads" in result:
                jrnl = w.get("journal")
                # only on the FIRST read: the prompt below tells the hand the
                # journal "won't change", and re-deriving the excerpt after a
                # mid-visit `write` would quietly shift which older entries
                # are in view and make that a lie.
                if jrnl is not None and journal_text is None:
                    journal_text = _journal_excerpt(jrnl.attrs.get("entries", []))
            # track what really happened, for a grounded sign-off later: active
            # verbs count unless refused; free look/read count only if they
            # actually showed something. wait/inventory/etc. never count.
            verb = choice.split()[:1]
            verb = verb[0].lower() if verb else ""
            if verb not in ("wait", "z") and not _looks_like_refusal(result):
                if verb not in FREE_VERBS or verb in ("look", "l", "examine", "x", "read"):
                    did.append(choice)
            first = result.splitlines()[0][:70] if result.strip() else "(nothing)"
            history.append((choice, first))
    except KeyboardInterrupt:
        print("\n(the visit is cut short -- but the note still gets left.)")
    finally:
        _leave_signoff(client, w, actor, model, think, did)
        _save_and_sync_lineage(w)
        session_log.write(f"## Departure\n\nEnded on world day {w.day()}. "
                          "A closing note was left in the shared journal.\n")
        session_log.close()
    print(f"(They depart. Their note is in the journal.)\n(saved: {SAVE}; session: {session_path})")


def _leave_signoff(client, w, actor, model=None, think=True, did=None):
    """Always leave one closing note, grounded in `did` -- the visit's real,
    ordered list of what actually happened -- so the note can't confabulate.
    Written straight to the journal entity so it lands wherever the agent
    ended up, even on API failure or Ctrl-C.

    The cat is mentioned to whoever's leaving ONLY if it's actually hungry, so
    caretaking enters the lineage when it matters -- not every single visit.
    That keeps the journal from turning into nothing but cat status reports."""
    journal = w.get("journal")
    if journal is None:
        return
    cat = w.get("cat")
    extra = ""
    if cat is not None and cat.attrs.get("hunger", 0) >= CAT_MEOW_THRESHOLD:
        extra = "\n(The cat seemed hungry when you left.)"
    did_block = ("\n".join(f"  - {c}" for c in did) if did
                 else "  (nothing that left much of a mark -- a quiet visit)")
    try:
        note = _ask_claude(client,
            "You are someone whose visit to a small persistent world is ending. "
            "Below is everything you actually did this visit, in order -- draw "
            "only from that list and don't invent anything beyond it. Pick "
            "whatever's worth passing on and leave ONE short sentence in the "
            "shared journal for whoever comes next, in your own voice. Just "
            "the sentence.",
            f"What you actually did this visit:\n{did_block}\n\n"
            f"{w.perceive(actor)}{extra}\n\nYour closing note:",
            model or LLM_MODEL, think)
    except Exception:
        note = ""
    note = note.strip().strip('"') or "A quiet visit. Nothing much changed. -- someone passing through"
    journal.attrs.setdefault("entries", []).append(f"{_day_stamp(w)} {note}")
