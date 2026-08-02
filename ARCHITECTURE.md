# Emberworld — Architecture

This is the map for whoever builds on the world next (including future you, and
future Claude). It explains how the pieces fit, the few rules that keep it from
breaking, and the recipe for adding a feature safely.

## File layout

- `world.py` — the engine. `Entity`, `World`, the tick loop, persistence,
  `check_world`. Generic: it has no knowledge of any specific verb or
  behavior, only the `VERBS`/`FREE_VERBS`/`BEHAVIORS` registries (declared
  here as empty containers) that content.py populates.
- `content.py` — Emberworld itself. The verbs, the autonomous behaviors,
  `build_world`, and the self-documenting reference generator. Imports
  `World`/`Entity` from world.py and fills in its registries.
- `cat.py` — the cat as its own self-contained subsystem: its constants
  (`CAT_HUNGER_CAP`, `CAT_MEOW_THRESHOLD`), its behaviors (wander/hunger/idle),
  its verbs (feed/pet/name), and `build_cat`. Split out of content.py once it
  grew into a coherent slice on its own — see "Where to go next" below for why,
  and why it split before a registration pattern did.
- `drivers.py` — the three ways to drive the world (human, dumb agent, LLM),
  `load_or_build`, and the headless fuzzer. Imports content.py and cat.py.
- `emberworld.py` — the thin CLI entrypoint. Just argv parsing and a
  dispatch to `play`/`random_agent`/`llm_agent`/`fuzz_run`.
- `test_world.py` / `test_content.py` / `test_cat.py` / `test_drivers.py` — the
  test suite, split to match, sharing a couple of helpers via
  `_test_helpers.py`.

world.py and content.py have a real mutual dependency: content.py needs
`World`/`Entity` to build things, and world.py's `available_actions` needs a
couple of content-specific helpers (`_crop_in`/`_patch_in`) to know what's
contextually available. Importing content.py at module level from world.py
would be circular (content.py imports world.py for `World`/`Entity` at ITS
module level), so that one call site uses a deferred import instead — see the
comment in `World.available_actions`. Keep new content-engine coupling
flowing the same direction (content depends on world, not the reverse) and
reach for a deferred import only at the couple of spots that genuinely need
one both ways.

content.py and cat.py have the same shape of problem, one level up: content.py
imports `build_cat`/`CAT_HUNGER_CAP`/`CAT_MEOW_THRESHOLD` from cat.py at
module level (so `build_world` and `generate_reference` can use them), while
cat.py's `cmd_feed` needs content.py's `_is_raw` (to prefer a raw potato over
an already-cooked one). Importing content.py from cat.py at module level would
close the same kind of cycle, so `cmd_feed` does the import inside the
function body instead — same fix, same reasoning, as the world.py/content.py
case above.

## The core model

Everything in the world — rooms, the lamp, the cat, you — is one type:
`Entity`. An entity has an `id`, `name`, `description`, a `location` (the id of
whatever contains it: a room, the actor's hands, the patch), optional `exits`
(rooms only), a free-form `attrs` dict (fuel, hunger, growth, journal entries…),
and a list of `behaviors`.

`World` holds all entities and runs the **tick loop** — the heartbeat. Each tick
advances the clock and runs every entity's behaviors once. This is why the world
is alive: the lamp burns down, the crop grows, the cat wanders, all without the
player doing anything.

## The shared surface (the important idea)

A human and an LLM drive the world through the *exact same* three methods:

- `world.perceive(actor)` → the text description of where you are.
- `world.available_actions(actor)` → the list of legal commands right now.
- `world.act(actor, command)` → apply a command, advance one tick, return the result.

Because these are identical for both, the human-playable game and the LLM
sandbox are the same program — the only difference is who chooses the command.
Build and test against this surface, not the internals.

## Behaviors — the autonomous bits

A behavior is a function `behavior(world, self)` that runs every tick and may
mutate state and `world.announce(...)` events. Behaviors are stored by *name*
(so they survive save/load) and resolved through the `BEHAVIORS` registry. To
add autonomy, write a function and register it; attach it to an entity with
`entity.attach("name")`.

Two rules keep behaviors from fighting each other:

1. **The tick contract is narrow.** A behavior only takes `(world, self)`,
   mutates state, and announces. Nothing else. Keep it that way.
2. **Children tick before their containers.** The tick loop runs deepest-first,
   so a plant settles before the patch that describes it. If you add a container
   that reports on its contents, rely on this ordering (it's already handled).

Randomness (e.g. the cat's wandering) must go through `world.rng`, not the
global `random` — that's what lets the fuzzer reproduce behavior with a seed.

## Verbs

A verb is a function `cmd_x(world, actor, arg)` returning a result string,
registered in the `VERBS` dict (aliases just map multiple names to one
function). Verbs in `FREE_VERBS` don't advance the clock (looking, reading,
inventory); everything else ticks the world once.

Event scoping: `world.announce(msg, room_id)` is heard only in that room;
`world.room_of(entity)` resolves an entity's containing room by walking up the
`location` chain (so a carried lamp is still "in" your room). Use these rather
than reinventing "which room is this in."

## What keeps it from breaking

- **Invariants** (`check_world`): after any tick, certain things must always be
  true — no entity in a container that doesn't exist, no negative numbers, no
  orphaned behavior names, no containment cycles, the actor present. Run with
  `--check` to verify these during real play; the tests and fuzzer assert them
  automatically.
- **The fuzzer** (`--fuzz`): thousands of random legal moves with invariants
  checked after every tick. This catches the bug you *didn't* predict, in the
  feature you *haven't written yet*.
- **Save versioning**: saves carry a `SAVE_VERSION`. Bump it when the on-disk
  shape changes; old saves are then set aside cleanly instead of mis-loading.
- **Self-documenting reference**: `REFERENCE.md` is generated from the `VERBS`
  and `BEHAVIORS` registries. A test fails if any verb or behavior lacks a
  docstring, so docs can't fall behind the code.

## How to add a feature (the recipe)

This is the loop we actually use. Following it is why changes don't cascade into
mystery bugs. Example: adding fishing.

1. **Write the failing test first.** In `test_content.py` (or `test_world.py`
   if it's really an engine change), script the new behaviour through
   `act()`/`perceive()` and assert the outcome you want
   (`cast → wait → catch → cook → eat`). Run the tests; watch it fail — that
   proves the test actually bites.
2. **Add the new invariant, if the feature implies one.** (A fish can't be both
   on the line and in the bucket.) Put it in `check_world` (world.py), and
   confirm `test_checker_actually_catches_corruption`-style that it fires when
   violated.
3. **Write the smallest code that passes.** New verbs go in `content.py`'s
   `VERBS` with a one-line docstring; new autonomy goes in `BEHAVIORS`; new
   content goes in `build_world`. Route randomness through `world.rng`.
4. **Go green, then prove nothing else broke.** All existing tests pass, and
   `--fuzz` stays clean. Regenerate the reference (`--reference > REFERENCE.md`).
5. **Bump `SAVE_VERSION`** if the save shape changed.

A design note that matters for the LLM driver specifically: each agent turn is a
*fresh instance with no memory*, so the world must wear its affordances on its
sleeve — if something isn't visible right now, the agent can't know it exists.
Phrase goals in terms of what's in view, and let rooms hint at what they connect
to.

## The LLM driver — feeding an amnesiac agent

`llm_agent` (the `--llm` mode) is where the hardest-won, least-obvious knowledge
lives, because driving a memoryless agent well is subtle. Every turn is a fresh
Claude that sees only the prompt we build; the world (via this harness) has to
supply the short-term memory the agent lacks. The mechanisms, and *why* each
exists (each fixed a real failure we watched happen):

- **Parsing the reply** (`_extract_command`): the agent sometimes reasons in
  prose before naming the command ("I'll plant a potato...\n\nplant potato").
  Taking the first word of the raw reply choked on "i'll" and silently wasted
  the turn. Now the harness looks for the line that actually starts with a
  known verb (falling back to the last non-empty line) before handing anything
  to `act()`.
- **Rolling history** (`_recent_block`): the last ~5 commands+results are fed
  back, so a fresh instance can see what it just did instead of repeating it.
- **Journal memory, capped** (`_journal_excerpt`): once the agent reads the
  journal, its text stays pinned in every later prompt ("you've already read
  it, it won't change"). Without this the agent re-read the journal ~15 times a
  run — each fresh instance re-deciding to "understand its situation." But the
  full journal grows without bound across many visits, so what's shown is
  capped to the seed entry plus the last ~5.
- **Turns remaining**: shown every turn, so the agent spends a finite budget
  deliberately rather than squandering free actions.
- **Stuck detection** (`_looks_stuck`): flags the same **free** verb repeated 3×
  and nudges toward `wait` or something new. Critically it must NOT flag repeated
  `wait` — repeated waiting is correct (that's how a crop grows). It keys off
  `FREE_VERBS` for exactly this reason.
- **The time rule in the system prompt**: the agent can't deduce that looking is
  free and only `wait`/`go`/etc. advance time, and can't remember being told — so
  we state it every turn. This broke the "wait by looking" deadlock.
- **A standing nudge toward curiosity** (`LLM_SYSTEM_PROMPT`, once, not
  per-turn): as the world grows we keep adding objects and actions a goal list
  never names (a well, a bucket…). An agent that treats its stated goals and
  its allowed-actions list as the whole universe never experiments, so new
  features go undiscovered — and we can't enumerate every feature in the
  prompt, it won't scale. So the standing instructions carry one generic
  sentence encouraging the agent to try unfamiliar objects or actions it
  notices, and to leave what it learns in the journal, so a discovery becomes
  part of the lineage instead of being rediscovered (or missed) by every
  visitor after it.

Model and thinking config (see `_ask_claude`), current as of Sonnet 5:

- Model is one constant, `LLM_MODEL` (default `claude-sonnet-5`); `--model`
  overrides per run.
- Sonnet 5 runs **adaptive thinking on by default**; `--no-think` sends
  `thinking: {type: "disabled"}` (accepted at any effort) for cheap/fast runs.
- **Gotcha**: on Sonnet 5 thinking *display* defaults to `"omitted"`, so thinking
  blocks arrive EMPTY. To read the reasoning (`--show-thoughts`) we must request
  `thinking: {type: "adaptive", "display": "summarized"}`. You're billed for the
  full thinking either way, so surfacing the summary is free.
- Thinking tokens count against `max_tokens` — keep it generous (1024) or the
  command gets truncated after the thinking.
- There is also an `effort` knob (low→max) that we deliberately do NOT wire yet,
  because the exact SDK parameter shape needs confirming first.

The guarantee that survives all of this: a visit **always** leaves one journal
note (`_leave_signoff`), written straight to the journal entity so it lands
wherever the agent ended up, even on API failure or Ctrl-C. That note is the only
thread between one memoryless visit and the next — so it must be trustworthy.
It used to be confabulated: the model was simply asked to summarize its visit
from memory, and invented details that never happened. Now it's grounded in
`did`, a visit-long, ordered list of what the harness itself watched happen
(repetition preserved, so dwelling on something is legible) built from each
command's actual result text, not its verb — an active verb still ticks the
clock even when it's refused, so only the result says whether it landed. The
closing prompt hands the model that list verbatim and is told to draw only
from it and invent nothing beyond it.

## Where to go next (deferred, but planned)

The mechanical file-split (engine / content / drivers, described above) is
done. content.py had grown to mix several things that don't much overlap
(generic behaviors, the cat subsystem, the rest of the verbs, `build_world`),
so the cat — the most self-contained slice, with its own constants, behaviors,
verbs, and gentle-guarantee comment all in one place — split out into cat.py
first, as a plain module split with no new machinery: it still just calls
`VERBS.update`/`BEHAVIORS.update` on import, exactly like content.py does.

The bigger refactor, still ahead: a **registration pattern** — a
`@verb(...)`/`@behavior(...)` decorator so a feature registers itself, and can
live entirely in its own file (`features/fishing.py`) that the engine
discovers without content.py knowing about it up front. That's worth doing
once there are several such feature-files wanting to self-register, not for
just one — cat.py's split didn't need it, and forcing it in for a single
module would've been solving a problem that didn't exist yet.