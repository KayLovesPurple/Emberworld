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
- `forest_text.py` — the forest's fragment pools (near/mid/deep × light,
  sound, undergrowth, smell), the ambient lines, and `describe_forest` /
  `_forest_ambient`. FOREST_SPEC.md Stages 2 and 6. Imports nothing: the two
  functions take an rng and return a string, which is exactly why this part
  of the forest lifted out cleanly when the rest of it could not — see
  "Where to go next".
- `drivers.py` — the three ways to drive the world (human, dumb agent, LLM),
  `load_or_build`, and the headless fuzzer. Imports content.py and cat.py.
- `emberworld.py` — the thin CLI entrypoint. Just argv parsing and a
  dispatch to `play`/`random_agent`/`llm_agent`/`fuzz_run`.
- `test_world.py` / `test_content.py` / `test_cat.py` / `test_drivers.py` — the
  test suite, split to match, sharing a couple of helpers via
  `_test_helpers.py`.

The dependency runs one way: **content depends on world, never the reverse.**
content.py imports `World`/`Entity` to build things; world.py imports nothing
back. What makes that possible is the registry pattern — world.py declares
`VERBS`, `FREE_VERBS`, `BEHAVIORS` and `ACTION_SOURCES` empty, and content.py
(and cat.py) fill them at import time. The engine calls what it's given
without knowing what any of it is.

`ACTION_SOURCES` is the newest of the four and the one that took longest to
arrive. `World.available_actions` used to *be* the answer rather than ask for
it: 89 lines hardcoding `"yard"`, `"forest_edge"`, `"potato"`, `"lamp"`,
`"journal"`, `"cat"` and the rest, inside the file whose whole promise is that
it knows none of that. It was the only thing in the codebase needing a
deferred import back into content.py to dodge a circular import, and the only
place every new feature — a forest verb, a seed, a cat affordance — had to
come and edit a shared function far from itself. Now each subsystem answers
for its own surface (`forest_actions`, `garden_actions`, `cat_actions` in
cat.py beside the rest of the cat), the deferred import is gone, and the
engine is what the top of world.py always claimed.

It's a list rather than a dict because the order a hand reads the actions in
is part of the surface, so content.py registers all the sources at one site
in one deliberate order instead of leaving it to import order. When you add
a feature, add to the source that already owns its subject, or write a new
one beside it.

content.py and cat.py have the same shape of problem, one level up: content.py
imports `build_cat`/`CAT_HUNGER_CAP`/`CAT_MEOW_THRESHOLD` from cat.py at
module level (so `build_world` and `generate_reference` can use them), while
cat.py's `cmd_feed` needs content.py's `_is_raw` (to prefer a raw potato over
an already-cooked one) and `_last_potato_beat` (the one-shot line fired when
a raw potato fed to the cat happens to be the last one). Importing content.py
from cat.py at module level would close the same kind of cycle, so `cmd_feed`
does the import inside the function body instead — same fix, same reasoning,
as the world.py/content.py case above.

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

## Found curios: reset or richer

`gather wood` rarely turns up a small found object (`FOUND_ITEMS` in
content.py: name, a bare odd-register look_line, and a `cat_reaction` of
`"plays"` or `"ignores"`). A curio has exactly three fates, and picking one
forecloses the others (a stone specifically has a fourth — see "The cairn"
below); README has the player-facing version. The code map: **notice** is
just `look <thing>` (`_found_description`, with a cat hint appended only
for a `"plays"` reaction) — free, nothing consumed. **Give to the cat**
(`give <thing> to cat`, `cmd_give`) consumes it from the pack and turns it
into a fixed, non-portable trace in the room description
(`_CAT_GIVE_REACTIONS`/`_CAT_GIVE_TRACES`, keyed by `cat_reaction`) — a
`"plays"` trace isn't done once given, either: `cat_replay` (cat.py) rarely
bats at it again later, see "Cat replay" below. **Leave on the shelf**
(`place`/`put <thing> on shelf`, `cmd_place`) consumes it from the pack
onto the hut's display-surface shelf (`_shelf_description`).

**The invariant, stated once so it doesn't drift**: after any curio action,
the world must be one thing richer, never reset. Concretely — `give` and
`put` may never touch a resource that feeds a maintenance loop (cat hunger,
bucket water, firewood, hearth fuel) or advance the clock themselves; they
may only add a durable, visible trace. The potato is the one grandfathered
maintenance loop already in the game; nothing here should become a second
one. `test_giving_or_placing_a_curio_touches_no_maintenance_resource` in
test_content.py pins this by calling `cmd_give`/`cmd_place` directly rather
than through `world.act` — going through the dispatcher would tick the
world and let unrelated autonomy (hunger rising, fire burning down) muddy
what the handler itself did or didn't touch.

Legibility rides on the object, not the parser: a `"plays"` curio's own
look-line ends "— the cat might bat at it", and `give`/`place` only appear
in `available_actions` when there's a carried curio (and, for give, a cat)
to act on — nothing to memorize.

Backward compatibility: `ensure_shelf` backfills `cat_reaction` (by name
against `FOUND_ITEMS`, defaulting to `"ignores"`) on any `found_`-prefixed
entity from a save predating this feature, the same way it already
backfilled the `curio` tag itself.

**The shelf is capped at `SHELF_CAPACITY` (10), the cairn deliberately
isn't.** The cairn already is the "everything, forever, anonymous" answer to
what happens to a found curio over the life of a lineage — a second
unlimited container doing the same job would be redundant. Capping the
shelf instead makes it the cairn's opposite: personal and curated rather
than collective and boundless. `cmd_place` refuses outright at capacity
("The shelf's full...") rather than bumping something off automatically —
no silent loss, and no forced choice either, since a hand can simply not
place a new find if the shelf feels full to them. `take` (already existing,
no new mechanic) is how room gets made. `available_actions` stops offering
`place <thing> on shelf` once the shelf is full, same legibility rule as
`give`/`place` only appearing when there's something to act on.
`_shelf_description` adds ", full up" only exactly at capacity, mirroring
the hearth's healthy/low read rather than exposing a bare count.

## Cat replay

Before this, a `"plays"` curio only ever got played with once — at the
instant of `give`, then never again, even though the battered trace sits
in the room forever after. `cat_replay` (cat.py, one of the cat's four
autonomous behaviors) closes that gap: each tick, it looks for entities in
the cat's current room where `not e.portable and e.attrs.get("cat_reaction")
== "plays"` — which only ever matches a post-give trace, never a
still-carried, still-portable curio that hasn't been given yet (the
`portable` check is what tells the two apart) — and, rarely
(`CAT_REPLAY_CHANCE`, 0.05), announces one more small line of the cat
batting at it. Same hunger gate as `cat_idle`: a hungry cat is preoccupied,
not playing. Purely cosmetic, same as every other ambient behavior in this
codebase — no state change on the cat, the trace, or anything else, just
`world.announce`.

Backward compatibility: `ensure_cat_replay` (cat.py) attaches the behavior
to a cat loaded from a save that predates it, checking `behavior_names`
first since `Entity.attach` isn't itself idempotent — calling it twice
would double the effective chance rather than being a no-op. Wired into
`drivers.load_or_build` alongside `ensure_shelf`/`ensure_cairn`.

## The forest's edge — v1, a doorway not the forest

One new room (`forest_edge` in `build_world`), reachable from the yard via
its `"forest"` exit (`"go forest"`), with an exit back keyed `"yard"`. It
exists to give a hand somewhere to *go* rather than only things to *tend* —
and to fix a real spawn-starvation complaint: waiting on `gather wood`'s rare
`FOUND_ITEM_CHANCE` roll to ever see a curio at all.

- **Finding is passive, not a verb.** `forest_finds` is a behavior attached
  to the room entity itself, not a dedicated command — a new verb is a new
  thing to discover, and the whole point of the curiosity-nudge rework was
  that discovery shouldn't ride on a hand guessing the right word. Instead,
  any tick where the actor's `location` is the room (arriving via `go
  forest`, or any later `wait`/action while still there) rolls
  `FOREST_FIND_CHANCE` against the *same* `FOUND_ITEMS` table `gather wood`
  draws from. No forked curio type, no new rules: a forest-found curio is
  the identical entity, so `give`/`place` treat it exactly like a
  yard-found one. `FOREST_FIND_CHANCE` started at 0.5 (deliberately far
  more generous than the yard, to fix the spawn-starvation complaint) but
  was pulled back down to 0.2 in the pacing rebalance below, once it turned
  out "far more generous" had overshot into "guaranteed per visit" — see
  that section for why.
- **The dark ahead is description-only.** `forest_edge.exits == {"yard":
  "yard"}` — no second room, on purpose. That headroom is reserved for the
  real forest build (the statue, the tea herb, wood-gathering relocating
  here) noted in README's "Someday" list; naming this room "the forest's
  edge" rather than just "the forest" is what lets that later work grow into
  it without a rename. (Stage 1 of `FOREST_SPEC.md`, below, adds a depth
  *counter* on top of this single room — `venture`/`return` move it, no new
  room or exit involved — so "no second room" still holds even though
  "no going deeper" no longer does.)
- **The cat stays out of it.** `cat_wander` picked uniformly among
  `room.exits` before this, which would have sent the cat down the new
  `"forest"`/`"yard"` exits too — except `_cat_go`'s departure/arrival
  wording only knows how to narrate `"in"`/`"out"` (doorway, tail-high
  phrasing), so the cat would arrive with backwards-sounding text. Rather
  than teach the cat subsystem a third room, `cat_wander` now filters its
  candidate exits down to `{"in", "out"}` — the cat's world stays the hut
  and the yard exactly as before; the forest is a hand-only place for now.

## Pacing rebalance — looser chores, rarer finds, and `listen`

Three changes that ship together on purpose, from real playtest transcripts
(a 20-turn hand spending ~16 turns on upkeep, placing zero of five carried
curios because no spare turn ever came; a forest that handed out a curio on
every single visit). Loosening the maintenance loop and making finds rarer
both *free up* turns — alone, that's just more quiet turns with nothing to
fill them. `listen` is what catches that freed space. Don't ship the first
two without the third.

- **Looser maintenance cadence.** `CAT_HUNGER_CAP`/`CAT_MEOW_THRESHOLD`
  doubled (12 → 24, in cat.py) — loosened first, since a hungry cat is the
  loudest, most legible turn-eater (it's both described as pacing/hungry
  *and* meows at you) and always wins the turn-contest against something
  quieter like placing a curio. `LAMP_FUEL_START` doubled (16 → 32) so one
  kindling covers a fuller visit instead of forcing repeat re-kindles.
  `HEARTH_FUEL_START` raised (40 → 60, which also raises `FUEL_PER_WOOD`
  and `HEARTH_LOW_FUEL` automatically since both derive from it) so
  wood-adding is occasional rather than a recurring beat. Crop growth
  (`ripe_at`, `PATCH_VOLUNTEER_TURNS`) deliberately untouched — lowest
  priority per the rebalance spec, and the plant→harvest→plant rhythm is
  the one grandfathered forced loop worth keeping intact.
- **Rarer forest finds.** `FOREST_FIND_CHANCE` cut from 0.5 to 0.2 — still
  a somewhat better bet than the yard's `FOUND_ITEM_CHANCE` (0.15), so the
  forest stays the place to go looking, but no longer near-guaranteed per
  visit. A guaranteed faucet made every find worthless and flooded packs;
  see `test_forest_edge_entries_do_not_always_yield_a_curio` for the
  regression guard (repeated real-rng entries must sometimes come up empty).
  **Round two**, after real play surfaced it again: even at 0.2, a hand that
  lingered at the forest's edge for only a handful of turns (waiting, or —
  once `FOREST_SPEC.md` Stage 1 added `venture`/`return` — shuttling depth
  back and forth) kept landing 3-4 curios in "a few steps." `forest_finds`
  rolls on *any* tick spent at `forest_edge`, whichever verb burns it, so
  more turns there always compounds into more rolls — the fix had to be the
  per-tick chance itself (cut to 0.08), not which verb is used to linger.
  This drops it below the yard's `FOUND_ITEM_CHANCE`, retiring the "somewhat
  better bet than the yard" rule — that comparison existed to fix the
  original spawn-starvation complaint, not as a standing design goal.
- **`listen`, the forest's calm affordance** (README has the player-facing
  description). Deliberately not in `FREE_VERBS` — the turn-cost is what
  makes it a genuine choice, not a freebie. **The constraint that must never
  break: `listen` grants nothing, ever** — no curio, no state, no buff, no
  accumulation of any kind. The instant it grants something it becomes a
  chore done for payoff and collapses back into the acquisition loop this
  whole rebalance fights. It sits on the tea-and-petting side of the
  calm-axis invariant (see README): freely chosen, unpressured, mark-free —
  the forest's `pet cat`. `test_listen_touches_no_world_state` pins this by
  calling `cmd_listen` directly rather than through `world.act`, the same
  reasoning as the give/place invariant test: going through the dispatcher
  ticks the world and lets unrelated autonomy (and even a `forest_finds`
  roll on the same tick) muddy what the handler itself did or didn't touch.
  The line pool is what lets it survive repeat use — a single fixed line
  goes dead on the second visit — and it's a real precedent for the
  someday statue's `wish` verb, which is shaped identically (a no-op that
  costs a turn and returns atmosphere).

## `watch clouds` — listen's sibling in the yard

A follow-up to the pacing rebalance above, same shape as `listen` (README
has the player-facing description) — registered under the verb key
`"watch"` (`cmd_watch_clouds`), even though it's cued and referred to
everywhere as "watch clouds." Same never-break constraint — grants
nothing, ever — and the same direct-handler test pattern
(`test_watch_clouds_touches_no_world_state` calls `cmd_watch_clouds`
directly, bypassing `world.act`'s tick, for the same reason `listen`'s does).

The one real difference: it reads the sky, so `WATCH_CLOUD_LINES` is keyed
by `world.phase()` (`dawn`/`day`/`dusk`) rather than being one flat pool,
and it's withdrawn outright at night — no entry in `available_actions`, and
calling it anyway returns the fixed `WATCH_CLOUDS_NIGHT_MSG` rather than a
line from the pool. Withdrawal (not a forced "too dark to see" line) was the
deliberate choice: an affordance quietly not being there when it wouldn't
make sense is more honest than making up a night line for it, and it's the
same call `is_dark` already makes elsewhere for a genuinely dark room. Note
`is_dark` and `phase() == "night"` are independent checks here — a carried
lit lamp keeps the yard's room description visible at night, but `watch
clouds` still withdraws on phase alone, since a lamp doesn't put anything
back in the sky to see.

## The forest, staged — Stage 1: the depth skeleton

`FOREST_SPEC.md` lays out the forest's remaining build as seven ordered
stages; this is the first one shipped. Two new verbs, `venture` (`world.
forest_depth += 1`) and `return` (`-= 1`, floored at 0 — depth can't go
negative, and below 0 there's simply "you're already back at the edge"),
both gated to `forest_edge` since it's still the only room a hand can act
from. No texture yet (both are fixed-flavor text) and no risk yet (`return`
is always exact) — this stage only proves the plumbing the later stages
build on.

The one design decision worth calling out: `forest_depth` lives as a plain
runtime attribute on `World` (declared in `world.py`'s `__init__`, right next
to `rng`/`strict`), **not** as a field in `to_data()`/`from_data()`. That's
deliberate, not an oversight — `World.from_data()` always builds via `cls()`
first (which sets `forest_depth = 0`) and never touches it from the loaded
data, so a fresh session automatically starts every visitor at the edge,
however deep the previous session went before saving. This is the same
pattern `hand_name` already uses (see "Optional self-naming" below): state
that describes *this visit*, not the persistent world, doesn't go through
`to_data()` at all — there's no reset code to write or forget, because
there's nothing to reset in the first place. `available_actions` only
offers `return` once `forest_depth > 0` (same legibility rule as `give`/
`place` only appearing when there's a curio to act on) — no point listing
an action that can't do anything yet.

## The forest, staged — Stage 2: texture generation

Stage 1's `venture`/`return` returned one fixed line each; Stage 2 replaces
that with generated prose so two visits (or two steps in a row) don't read
alike. `FOREST_FRAGMENTS` is a dict of three depth bands (`"near"` 1–2,
`"mid"` 3–5, `"deep"` 6+, via `_forest_band(depth)`), each holding four
independent pools of bare, lowercase clauses — `light`, `sound`,
`undergrowth`, `smell`. `describe_forest(depth, rng)` picks one fragment
from each pool in the matching band and joins them into a single line.
`venture`/`return` call it with `world.rng`, same as `forest_finds` and the
cat's wandering, so `--fuzz` stays reproducible under a fixed seed.

Depth 0 (the edge itself) isn't banded — it already has its own fixed room
description, and landing back on it via `return` gets its own distinct line
rather than a generated one, so there's never a moment where depth-0 prose
tries to describe forest interior that isn't there.

One gotcha worth flagging for future fragment-writing: `drivers.py`'s LLM
driver scans every result string for `_REFUSAL_MARKERS` substrings (like
`"can't"`, `"there's no"`) to tell a real refusal from a landed action, for
its grounded end-of-visit `did` list. A forest fragment that happens to
contain one of those substrings would make a successful `venture` misread
as a no-op — caught in review by two fragments that said "you can't place"
and "there's no stone in sight" before either shipped.
`test_no_forest_fragment_reads_as_a_refusal_marker` in `test_content.py`
guards this directly, and is worth re-running (or extending) whenever new
fragments are added in later stages.

## Calm-axis session acknowledgment

`listen` and `watch clouds` grant nothing, ever — that constraint (above)
must never break. But a real gap turned up in play: for a hand with no
memory of any visit but this one, "grants nothing" was indistinguishable
from "didn't happen at all," which quietly defeated the point of a calm
action in the first place — a human player carries the feeling of a quiet
moment forward on their own; an LLM hand has nothing to carry it forward
*with* except what the world itself hands back. The fix has to answer back
to the same hand, in the same visit, without becoming a reward.

`world.calm_visits` (a plain `dict`, declared next to `forest_depth` in
`World.__init__`, same episodic treatment — never touches `to_data()`)
counts how many times *this* hand has chosen a calm act at a given spot this
session. `_calm_visit_ack(world, spot)` in content.py is the shared counter:
`listen` and `watch clouds` both call it with `spot="forest_edge"`, so
mixing the two verbs still reaches the acknowledgment — it's tracking chosen
*presence*, not mastery of one command, and a future calm verb at the edge
(a hypothetical `look at flowers`, say) should feed the same counter rather
than starting its own. The suffix fires exactly once per visit, on the
third calm act at that spot (README has the player-facing line) — never
before, never again after: not a running status, not a buff, no
confirmation of anything beyond that one line, same discipline as the
verbs it's attached to.

**Forest's edge only, not the yard.** `watch clouds` also works in the
yard, but the yard is constant through-traffic for chores (wood, water,
hearth) — counting presence there would mostly count the forced loop, not
calm choice, so the yard branch of `cmd_watch_clouds` never calls
`_calm_visit_ack`. The forest's edge is the one calm spot nothing forces a
hand to visit, which is what makes repeat presence there actually mean
something.

Tests that call `cmd_listen`/`cmd_watch_clouds` directly and compare exact
line-pool membership (`test_listen_returns_varied_lines_not_always_the_same_one`)
had to start stripping `CALM_ACK_LINE` from the result, since the third call
in that loop now carries the suffix — worth knowing if a similar exact-match
test gets added near either verb later.

## The cairn — a fourth, collective fate for stones

The shelf/cairn contrast — personal and reversible vs. permanent and
anonymous — is README's to describe; here's the mechanism: `stack stone [on
cairn]` (`cmd_stack_stone`) consumes a carried stone-named curio outright
(`world.entities.pop`, not a location change) and adds `world.rng.choice(
CAIRN_GROWTH_CM)` (2-5, textured rather than fixed) centimeters to the
`cairn` entity's `height_cm` attr. Only stone-named curios qualify (`"
stone" not in e.name.lower()` refuses anything else); every other curio type
still only has its original three fates.

`height_cm` reads out as banded prose (`_cairn_description`, `CAIRN_BANDS`),
the same texture as the hearth's healthy/low/spent read — "ankle-high",
"waist-high", and so on — rather than a bare number a hand could optimize
toward. Growing tall takes many, many stones across many, many hands (stones
are already a rare find on top of it), and that slowness is the point: no
single visit will see it grow by much, only the lineage as a whole will.

Unlike `forest_depth`/`calm_visits` right above this section, the cairn is
the opposite kind of state on purpose: it's lineage-scale, not
session-scale, so it persists through `to_data()`/`from_data()` like any
other entity, same as the shelf. `ensure_cairn(world)` backfills it onto a
world (fresh build or a pre-existing save) exactly the way `ensure_shelf`
already does, and is idempotent — calling it again never resets an existing
cairn's height. `available_actions` only offers `"stack stone on cairn"`
when the hand is at `forest_edge` *and* actually carrying something
stone-named, the same legibility rule `give`/`place` already follow.

## The forest, staged — Stage 3: episodic reset, made explicit

Stage 1 already made `forest_depth` a plain runtime attribute, never written
into `to_data()`. Stage 3 doesn't change that mechanism — it exists to make
the rule impossible to break by accident, and to give it a name: **forest
position is episodic; forest effects are persistent.** Anything a hand
*does* in the forest that produces a durable object or state change outside
it (a curio found, wood carried out, a stone later stacked on the cairn) is
just a normal entity/attr change and persists through the save exactly like
anything else in the game. Only the "how deep / which way" question —
`forest_depth`, and `calm_visits` alongside it — resets, because that
describes *this visit*, not the world.

Two things pin this down as a fact about the engine, not a coincidence of
the current code:

- `test_to_data_only_ever_contains_the_four_persisted_top_level_fields`
  (test_world.py) asserts `World.to_data()`'s exact key set. `to_data()` is
  hand-written to return exactly `{version, time, seq, entities}` — it isn't
  built by spreading `self.__dict__`, so there's no code path by which a new
  session-scoped attribute could leak in silently. This test is what makes a
  future violation fail loudly, in the way `FOREST_SPEC.md` Stage 3 asked
  for a "session-end hook" to guarantee: given `to_data()`'s hardcoded
  shape, the real risk isn't a missing teardown step, it's a *future*
  `to_data()` rewritten to serialize more generically — this test catches
  that the moment it happens, rather than waiting for a depth value to leak
  into someone's save.
- `test_forest_depth_resets_but_committed_effects_survive_a_mid_visit_reload`
  (test_content.py) is Stage 3's exit criterion made literal: venture eight
  deep, find a stone, reload — depth comes back at 0, the stone is still in
  the actor's hands.

## The forest, staged — Stage 4: getting lost

README has the player-facing description of the risk itself. Below
`SAFE_DEPTH_THRESHOLD` (3), `return` is exactly what it's always been —
`world.forest_depth -= 1`, no randomness, airtight; that floor is
deliberate, so a short casual dip is never the thing put at risk, only
depth gone to on purpose.

Beyond the threshold, each `return` rolls `OFF_COURSE_CHANCE` (0.18) against
`world.rng.random()`. On a hit, the landing depth is drawn from every depth
in `range(depth)` *except* `depth - 1` (the expected landing) — so the
branch can never silently produce the same result a normal return would,
which would make it untestable as its own thing. The floor (never negative)
falls out of `range(depth)` starting at 0 by construction; there's no
separate clamp to get wrong. Landing exactly on 0 gets its own line (same
reasoning as `venture`/`return`'s existing depth-0 special case) rather than
routing through `describe_forest`, which has nothing to describe at the
edge itself.

No penalty rides along with the mismatch beyond the disorientation itself —
per the calm-axis invariant's own logic applied to risk instead of reward,
that uncertainty is deliberately the entire cost, not a punishment bolted
onto it.

Two test doubles pin the branch down precisely rather than statistically:
`_AlwaysOffCourse`/`_AlwaysOffCourseHigh` (test_content.py) both force
`random()` to always trigger, but pick opposite ends of the candidate list
(`choice` returns `seq[0]` vs `seq[-1]`), which is what lets the tests prove
the branch can land at the edge (0) *and* mid-forest, not just one or the
other. `test_return_below_the_safe_depth_threshold_is_always_exact_even_
under_a_forced_roll` runs the same forced-trigger rng at or below the
threshold and asserts nothing changes — the safety guarantee has to survive
an adversarial rng, not just a lucky one.

## The forest, staged — Stage 5: trail-marking

Stage 4's risk needed a player-facing lever, or it just reads as a dice
roll happening *to* a hand rather than something they can manage. `mark
trail` (`cmd_mark_trail`) does exactly one thing: `world.forest_mark_depth
= max(world.forest_mark_depth, world.forest_depth)` — session-scoped,
declared in `World.__init__` right alongside `forest_depth`/`calm_visits`,
for the identical reason: a trail marked this visit means nothing to the
next, memoryless hand.

The mechanism is a single line in `cmd_return`: `safe_to = max(
SAFE_DEPTH_THRESHOLD, world.forest_mark_depth)`, then the existing Stage 4
check becomes `depth > safe_to` instead of `depth > SAFE_DEPTH_THRESHOLD`.
That's the whole integration — Stage 4's branch didn't need to change
shape, only the number it compares against. (README has the player-facing
nuance on exactly what a mark does and doesn't extend — worth rereading
before touching this line, since it's easy to misread `safe_to` as opening
a corridor rather than just raising a floor.)

Marking shallower than an existing mark is a harmless no-op, refused with
a distinct message rather than silently succeeding. Costs a turn like any
real action, needs nothing consumable, and is gated out of
`available_actions` once redundant (depth 0, or already marked at the
current depth) — same legibility rule as everywhere else in the game.

## The forest, staged — Stage 6: ambient, unscripted texture

The "crack in the closedness" the spec asked for (README has the
player-facing description): `FOREST_AMBIENT`/`_forest_ambient(rng)` is a
small independent chance (`FOREST_AMBIENT_CHANCE`, 0.12), separate from
Stage 2's depth-banded `FOREST_FRAGMENTS`. Same restraint as the statue: no
"investigate" option references it, deliberately unexplained.

Wired into both branches of `cmd_return` (the normal fall-back and the
Stage 4 off-course landing) and into `cmd_venture` — but not the depth-0
"back at the edge" lines in either, same reasoning `describe_forest`
already follows: there's nothing forest-interior to layer ambience onto
once you're back at the edge.

The explicit spec requirement — ambient lines must never crash when they
co-occur with an off-course event — turned out to be free rather than
needing special handling: `_AlwaysOffCourse` (Stage 4's test double)
forces `random()` to `0.0` unconditionally, so it *also* forces the
ambient roll on the same call, which is what `test_ambient_can_co_occur_
with_an_off_course_return_without_crashing` actually exercises, not a
contrived combination.

BUG WE HIT while writing the pool: two of the six ambient lines happened
to contain a `_REFUSAL_MARKERS` substring ("you can't place", "already
gone") — the exact same class of incident `test_no_forest_fragment_reads_
as_a_refusal_marker` already existed to catch for `FOREST_FRAGMENTS`. That
test now also scans `FOREST_AMBIENT` (and `MOON_LINES`/`OFF_COURSE_LINES`,
picked up in the same pass) — worth re-running whenever any of these pools
grow.

## The forest, staged — Stage 7: wood relocation and the statue

Two of the three things Stage 7 promised; the tea-herb is deliberately
deferred (see FOREST_SPEC.md), not forgotten.

**Wood-gathering relocated from the yard to the forest's edge** —
`cmd_gather`'s location check flipped from `"yard"` to `"forest_edge"`,
`available_actions` moved the cue to match, and the yard goes back to
being just the yard (no room-description change needed; it never
mentioned wood in the first place, discoverability always rode on the
action list, per `test_yard_description_does_not_mention_wood`). The one
real decision: `cmd_gather` **dropped its own separate find-roll**
entirely rather than bringing `FOUND_ITEM_CHANCE` (0.15) along with it.
`forest_finds` already rolls `FOREST_FIND_CHANCE` on any tick spent at
the forest's edge, gather-wood turns included — stacking a second,
independent roll on top would have doubled the effective find chance
exactly where wood-gathering now happens, which is precisely the
"moved, not intensified" constraint the spec states outright. `FOUND_
ITEM_CHANCE` is retired along with the roll it powered.

**Later addendum: ambient wood, still one roll.** A hand asked to
occasionally stumble onto loose wood while exploring — waiting, venturing,
returning — not only via a deliberate `gather wood`. Rather than revisit
the no-second-roll decision above, `forest_finds` now carves a slice
(`_STRAY_WOOD_SHARE`, 0.15) out of the *existing* `FOREST_FIND_CHANCE`
roll: most of the time that roll still resolves to a curio, but sometimes
it resolves to `WOOD_PER_STRAY_FIND` (1, well under `WOOD_PER_GATHER`'s
3) of wood instead. The overall odds of *something* happening on a given
tick are unchanged — the same "moved, not intensified" spirit, just
applied to what the one roll can produce rather than how many rolls fire.
The split point sits at the *high* end of the roll's range (`roll >=
FOREST_FIND_CHANCE * (1 - _STRAY_WOOD_SHARE)` is wood, everything below
is curio) specifically so a roll of exactly `0.0` — what every `_Lucky`
test fixture already returns — keeps meaning "curio," leaving every
existing curio-find test's assumptions intact.

**The statue** is discovered, not placed. `STATUE_MIN_DEPTH` (3) gates it
out entirely below that depth — a deep-visit thing, never a short-trip
accident — and beyond it, each `venture` rolls `STATUE_DISCOVERY_CHANCE`
independently (0.15 at first ship, raised to 0.25 after real play found the
wait too long; `STATUE_MIN_DEPTH` was deliberately left alone in that
tuning pass — that's what keeps it a deep-visit thing, the chance is just
the odds once you're already there). On a hit, `world.statue_found_this_
session` (session-scoped, declared in `World.__init__` alongside `forest_
depth`/`forest_mark_depth`/`calm_visits`, for the identical episodic-reset
reason) is set `True` and the discovery line is appended — composition
order per the cross-cutting requirement, discovery text before the ambient
roll, since `venture` has no off-course branch to also consider (that's
`return`-only).

`STATUE_DISCOVERY_TEXT` also carries the one deliberate hint that wishing
is even possible (README states the custom-vs-invitation distinction this
line has to walk — a comment directly above the constant in content.py
restates it too, for whoever edits the line next).
Once found, it stays found for the rest of the session; `test_statue_is_
not_rediscovered_once_found_this_session` pins that the discovery text
never repeats on a later `venture`.

`wish <something>` (`cmd_wish`) is gated by `_statue_reachable`: found
this session *and* currently at `forest_edge` with `forest_depth >=
STATUE_MIN_DEPTH` again — found-once doesn't mean wishable from the edge,
but it also isn't pinned to the exact depth it first appeared at (the flag
is a plain boolean, not a stored depth), so a hand can wish again from any
sufficiently deep point later in the same visit. **The constraint that
must never break, restated from README's "wishing-statue" section**: the
verb is mechanically inert. `cmd_wish` never checks or grants anything —
it appends the raw wish text (tagged with `_day_stamp`, the same stamp
`cmd_write`/the LLM sign-off use) to `ensure_statue(world).attrs["wishes"]`
and always returns the identical fixed `STATUE_WISH_LINE`, with no
confirmation of anything heard or granted, ever. `ensure_statue` creates
the statue's entity lazily, on the first actual wish — unlike `ensure_
shelf`/`ensure_cairn`, it isn't wired into `load_or_build`, since most
visits (plausibly most whole lineages) may never find it at all, and
nothing else needs the entity to exist before then.

Deliberately **not** added to `check_world`: a standing invariant that
`statue_found_this_session` is never `True` below `STATUE_MIN_DEPTH`. The
spec's cross-cutting section suggested this, but it doesn't actually hold
in correct play — a hand who finds the statue at depth 5 and then
`return`s to depth 1 still has the flag `True` (correctly: they still
remember finding it) while currently shallower than the threshold. Adding
that check would fire a false positive on ordinary, intended behavior, so
the structural `to_data()`-shape test already covers the real risk here
(a forest-transient field leaking into a save) without a check that would
be wrong the moment someone actually returns partway back.

BUG WE HIT while writing the discovery line: two successive drafts each
tripped `test_no_forest_fragment_reads_as_a_refusal_marker` ("you can't
tell", then "there's no telling") before landing on wording that avoids
`_REFUSAL_MARKERS` altogether -- same incident class as Stage 6's ambient
pool, worth expecting again for any future statue/forest prose.

**BUG WE HIT, worse than the wording one: once found, the statue stayed
permanently visible in the forest_edge room description for the rest of
the session — even back at depth 0, right at the edge.** Root cause:
`actor.location` never actually leaves `"forest_edge"` at any depth
(venturing is a session-scoped counter, not a real room change), so
`cmd_look`, `available_actions`, and `find_visible` were all reading a
flat `world.contents(room.id)` that can't tell depth apart — anything
placed in that room (the cairn, and once created, the statue) was
reachable from literally anywhere in the whole forest, not just where it
actually belongs. The cairn had the milder version of the same bug: `look
cairn` and even `stack stone on cairn` worked from any depth, when it's
meant to be a landmark specifically at the edge.

Fixed with one shared helper, `_room_here(world, actor, room)`, used by
all three call sites instead of the bare `world.contents(room.id)`. For
any room other than `forest_edge` it's a pass-through; for `forest_edge`
it filters: the cairn only appears when `forest_depth == 0`, and the
statue only appears when `_statue_reachable` holds — the exact same gate
`wish` already used, so "can you see it" and "can you wish at it" now
agree by construction rather than by two separately-maintained checks.
Routing `find_visible` through it too (not just the room-listing/action-
cue call sites) matters as much as the listing fix: hiding something from
`available_actions` but leaving it reachable by typing its name directly
would only have fixed the suggestion, not the actual bug.
`cmd_stack_stone` needed its own explicit depth check on top of this,
since it never went through `find_visible` to locate the cairn in the
first place — it grabs it directly via `ensure_cairn`.

## The full moon — the one exception to the night withdrawal

`watch clouds` at night has always been a clean withdrawal (`WATCH_CLOUDS_
NIGHT_MSG`), never a forced line — see the pacing-rebalance section above
for why that honesty mattered. The moon is the exception, and it's built to
still honor that reasoning rather than undercut it: `_moon_view(world)` is a
real clock keyed to `world.day()`, not a dice roll and not anything
session-scoped, so it's the one place a hand can actually *witness* the
world running on a schedule bigger than any single visit, rather than just
being told that's true. `sky_actions` offers `"watch clouds"` at night
whenever `_moon_view` returns non-`None` — both of them in content.py,
where anything that knows what a moon is belongs. `_is_full_moon` survives as a thin
`_moon_view(world) == "full"` wrapper, so existing imports and tests didn't
need to move.

**BUG WE HIT, measured rather than just noticed: the moon was reachable in
theory and dead in practice.** The original `_is_full_moon` was
`world.day() % MOON_CYCLE_DAYS == 0` — day 0 is a new moon by construction,
so a fresh world's first full moon landed on day 29, roughly 23 visits of
30 turns in. Even past that cold start, only one night in 29 ever showed
anything, and a hand also has to be outdoors, awake, and choose to look on
that exact night. Two independent faults, not one: a **cold start** (the
cycle is aligned to day 0) and a **narrow window** (one night in 29). Fixing
either alone leaves the other broken.

The fix is `MOON_PHASE_OFFSET` (22) and `MOON_NEAR_NIGHTS` (3).
`MOON_PHASE_OFFSET` shifts the cycle so the first full moon lands on day 7
instead of day 29 — a real moon has an arbitrary phase at any given epoch,
so day 1 being a new moon was never anything but an unexamined accident of
counting from 0; 22 specifically leaves day 1 at phase-distance 6, safely
outside the near-window, so `test_watch_clouds_still_refuses_on_an_ordinary_
night` — which waits from a fresh world to its first night and asserts
withdrawal — keeps passing with margin rather than by coincidence.
`MOON_NEAR_NIGHTS` widens "worth a look" from the single exact-full night to
the `2 * MOON_NEAR_NIGHTS + 1` (7) nights around it, returning `"waxing"`
or `"waning"` from `_moon_view` on the near nights and drawn from their own
line pool, `MOON_VIEW_LINES`. **A near-full night must read as its own
weather, never a consolation prize for missing the full one** — no line in
either pool references the full moon or implies anything was missed; the
moment a gibbous-moon line reads as a near-miss notification, widening the
window makes the feature worse, not better, because the rare thing stops
being rare and what replaces it is a notice that you didn't quite catch it.
`test_a_fresh_world_reaches_a_visible_moon_within_a_few_days` and
`test_the_moon_is_visible_on_a_minority_of_nights` are the two halves of
this pinned down as assertions rather than left as tuned constants nobody
re-checks: reachable soon, but still a minority of nights — 7 of 29, not
"most nights," or the moon becomes the default night sky instead of an
event.

Deliberately inert beyond the text on every branch, full or near-full: the
moon must never light the room (no free lamp-substitute —
`test_moon_line_touches_no_world_state`/`test_waxing_and_waning_lines_
touch_no_world_state` both assert `w.is_dark("yard")` stays true right
after the call) or touch state in any other way. Same never-break
constraint as `listen`/`watch_clouds` by day, just gated by date instead of
a probability roll.

## A general rule: content keyed to the calendar is rare in visits, not days

The moon bug above is a specific instance of a class worth naming so it
doesn't recur elsewhere: a visit is roughly 30 turns ≈ 1.25 world-days
(`DAY_LENGTH` is 24 ticks), and the world's clock only advances while
someone is actually playing. So anything keyed to `world.day()` has its
*real* rarity measured in visits, not days — period-in-visits ≈
period-in-days ÷ 1.25. A constant that looks modest in days (a 29-day
cycle) can be a near-total dead zone in visits (23 of them) without the
constant itself ever looking wrong on the page. When adding day-keyed
content: state the expected visits-to-first-encounter in a comment beside
the constant, and pin reachability with a test the way
`test_a_fresh_world_reaches_a_visible_moon_within_a_few_days` does, rather
than trusting the day-count to read as obviously fine. Per-tick dice rolls
(`forest_finds`, `wildlife_glimpse`, and the like) don't need this — they're
already denominated in turns, which is the unit that actually matters.

## Ambient wildlife — glimpsed, not met

`wildlife_glimpse` is a room behavior, same shape as `forest_finds`
(actor-presence check, then a per-tick chance roll), attached to `yard` and
`forest_edge` in `build_world`. The one real difference from its cousin:
this never touches `world.entities` — no curio, nothing to carry, nothing a
`give`/`place` could ever act on. It only calls `world.announce`, which is
what `test_wildlife_glimpse_never_creates_or_removes_an_entity` pins down
directly (asserts `world.entities.keys()` is unchanged, not just that the
result "looks right").

`WILDLIFE_LINES` is keyed two levels deep — room, then `world.phase()` — and
a room/phase combination with no entry (the yard at midday, say) means the
behavior fires nothing at all rather than falling back to some generic
line; a fox belongs at dusk, not noon, and forcing a line to exist
everywhere would flatten that. Same composition-order reasoning the forest
Stage 6 spec already calls for applies here for free: `wildlife_glimpse`
only ever calls `world.announce`, and `world.act`'s existing "verb result
first, then whatever got announced this tick" ordering (see `heard` in
`World.act`) already puts it in the right place without any special-casing.

`test_no_forest_fragment_reads_as_a_refusal_marker` was widened to scan
`MOON_LINES`, `OFF_COURSE_LINES`, and every `WILDLIFE_LINES` entry alongside
the forest fragments it already checked — any of them landing in a driver
result string could, in principle, trip the LLM driver's refusal-detection
the same way a forest fragment already once did.

## A dark night — varied `wait`, and confirming what already worked

A dark night is mostly `wait` — there's little else safe to do out there,
and that's correct (see the lamp/hearth mechanic itself for why: no light,
no reading, no seeing what's on the ground). That's also, deliberately,
almost the entire lever available for how a dark night *feels*. Two things
followed from that:

`pet cat` and `eat <held food>` were already ungated by darkness (README
has the player-facing version) — neither routes through `cmd_look`'s
`is_dark` check (the only place that check lives); both go through
`find_visible`/`_room_here`, which don't consult phase or light at all.
`test_pet_the_cat_works_in_the_dark` and
`test_eat_a_held_cooked_potato_works_in_the_dark` pin this down so it can't
regress silently the next time the dark-gating logic is touched.

`cmd_wait` itself, though, said the identical `"You wait. Time passes."`
every single call, dark or not — and since a dark night is *mostly* `wait`,
that flat line was the entire felt texture of getting through one. Fixed
by drawing from `WAIT_DARK_LINES` (a small pool of quiet, ambient lines)
whenever `world.is_dark(actor.location)`, daytime `wait` left untouched.
Two refinements, same "don't say something that isn't there" instinct
`_room_here` above is built on:

- `WAIT_DARK_HUT_LINES` (the cold through the floor, the hearth ticking)
  only enters the pool indoors — said in the yard or at the forest's edge,
  they'd describe hut furniture that isn't there.
- The line naming the cat only enters the pool when the cat is actually in
  the room to be heard, and runs its name through `_cat_cap` so a named cat
  is named and an unnamed one reads as "the cat" — same convention every
  other cat-adjacent line already follows.

One line in the base pool (`"...Not yet, but coming."`) is a deliberate
vague hint that dawn is on its way, without claiming a specific tick count
— the point is turning the wait from an open-ended void into a night that's
being gotten through, not a promise about exactly how many turns are left.

## The mystery seed — the first thing one hand leaves for a later one to act on

Everything else a hand leaves behind (a journal note, a curio on the shelf,
a stone on the cairn) is something a *later* hand can read about or add to.
A seed found at the forest's edge, planted in the yard, is the first thing
where one hand's choice changes what a later hand can actually *do* — the
seed takes longer to bloom than any one visit lasts, so the planter is
reliably gone by the time it opens, and whoever's around when it does is
the one who gets to pick it. README has the player-facing description.

**Adds no new verbs.** `plant` learns a second thing to plant
(`cmd_plant` dispatches to `_plant_seed` when the matched entity has
`attrs["seed"]` and is actually carried); once bloomed, the plant is just
an ordinary `portable`/`curio` entity, so `take`, `place`, and `give`
already know what to do with it without a line of new code. The action
menu is already 16–19 items deep in every room — a feature that needs its
own verb to work is a feature working against the game's shape at this
point.

**The core decision, pinned by a test so it can't quietly regress:**
`BLOOM_TICKS` (120 — 5 world-days, ~4 visits) must exceed a visit (~30
turns). This isn't a tuning knob, it *is* the feature — below roughly 72
ticks the planter starts seeing their own bloom, and the whole multi-visit
point collapses into a slower potato. `test_a_bloom_outlives_a_single_
visit` asserts `BLOOM_TICKS > 30` with the reasoning in its docstring, so
a future "this feels slow" edit has to argue with an assertion, not just
overwrite a comment.

**The supply is deterministic, not a roll.** `seedfall` (attached to
`forest_edge`, same shape as `forest_finds`/`wildlife_glimpse`) offers a
seed whenever `_seed_in_world` and `_mystery_plant` both come back `None`
— no dice. The precedent is `patch_volunteer`, not `forest_finds`: a
deterministic floor, not a routine source. Stacking a rare-find roll on
top of an already multi-visit wait would compound two long odds into
content that mostly doesn't happen, which is exactly the mistake the
moon fix above exists to correct — no reason to reintroduce it here. The
floor is self-limiting on its own: the world holds at most one token of
the arc (a loose seed, or a growing/bloomed plant) at any time, checked
across all three states a token can be in, so a second seed simply can't
appear until the first one's whole arc completes.

The seed is created **on the ground at `forest_edge`, not in the pocket**
— unlike `forest_finds`'s curios. It renders as an ordinary `- ` line in
the room description (the same `_room_here`/`cmd_look` machinery every
other ground item already uses) until a hand chooses to `take` it, so
noticing it and picking it up are two separate, genuinely optional beats,
not one automatic pocketing. Worth noting, not by design so much as a
property that falls out of the actor persisting across sessions: a hand
who takes the seed and leaves without planting it hands it to whoever's
body picks up next session — the "you wake holding a stranger's things"
idea, finally with a seed in it that actually does something later.

**`blooming` is deliberately NOT `growing`.** There is no watered/boosted
branch, and there must never be one — the whole point of this arc is that
a hand cannot hurry it along, so the absent water path is the feature, not
an oversight later code review would "fix." `cmd_water` only ever targets
a crop *inside* the patch (`_crop_in`), so a freestanding mystery plant in
the yard was never even a reachable target for it in the first place;
`test_a_planted_seed_ignores_water_entirely` pins the observable rate
(always +1 growth per tick) rather than just the missing code path, so a
future refactor that accidentally unifies the two behaviors still gets
caught. The mid-arc description is banded the same way `_cairn_description`
already bands cairn height (`BLOOM_BANDS`, a `(threshold, line)` tuple
scanned the same way `CAIRN_BANDS` is) — most hands who meet this thing
meet it here, not at planting or at the open, so the middle bands carry as
much of the feature's actual screen time as the payoff does.

**`BLOOM_KINDS` is a fixed tuple, deliberately not composed from pools the
way a forest fragment is.** `FOREST_FRAGMENTS` is composed because it
fires on every `venture`/`return` and needs combinatorial depth to survive
that repetition; a bloom opens roughly once every four visits and gets
read closely when it finally does. A handful of flowers that each read
like one real, specific thing beats a mad-libs generator with more
permutations that reads like an approximation of one. Composition is the right
tool for texture that repeats; it's the wrong tool for a payoff that
doesn't. Shaped exactly like `FOUND_ITEMS` (name, look_line, cat_reaction)
for the same reason `FOUND_ITEMS` is shaped that way: the look_line feeds
the same `_found_description` helper (cat hint appended only for
`"plays"`), and the reaction is stored on the plant at planting time
(`bloom_reaction`) and applied to the entity's real `cat_reaction` attr
only once it opens. That has to be set explicitly, not left to
`ensure_shelf`'s backfill — that backfill only ever touches
`"found_"`-prefixed entities (a bloom's id is `"bloom_N"`), so a shelved
bloom would otherwise silently default to `"ignores"` the next time an
older save loads, same class of gap `ensure_shelf`'s own backfill was
written to close for curios.

**No save-version bump.** `to_data()` still returns exactly `{version,
time, seq, entities}` (see the forest's own Stage 3 section on why that
shape is asserted, not just believed); a seed and a bloom are ordinary
entities with ordinary attrs, so an older save simply has no seed yet, and
`seedfall` supplies one on the first visit to the edge after loading — no
backfill function needed, unlike `ensure_shelf`/`ensure_cairn`.

**`check_world` is deliberately left alone.** world.py's own docstring
says no knowledge of any specific verb or behavior lives there, and "at
most one mystery plant" is content knowledge, not an engine invariant.
Asserted in the test suite and exercised by `--fuzz` instead.

**Deferred:** when a bloom is left standing and a new seed later gets
planted, the spec calls for the old bloom to fold into a single collective
`border` entity — the cairn's yard-side twin, described in bands by how
many flowers it's held, never pickable again — making the choice at bloom
time the shelf-versus-cairn choice transplanted to a flower: keep it, or
let it join something collective. Deliberately not built yet: it's the
better feature and also the one most likely to be over-built on a first
pass, so Stage 1 ships alone, a lineage gets to actually use it, and Stage
2 waits for what that play surfaces — same discipline the forest's own
staged build already follows.

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
  it, it won't change") — and it's derived exactly once, on the first read, so
  a mid-visit `write` can't shift it and make that sentence a lie. Without the
  pinning the agent re-read the journal ~15 times a run — each fresh instance
  re-deciding to "understand its situation."

  *How much* is shown is capped here (~5 recent + ~2 older) and separately in
  `cmd_read` (`JOURNAL_READ_LIMIT` 7 + `JOURNAL_OLDER_SHOWN` 3), because a
  prompt pays per token every turn and a hand reading a book doesn't. *Which*
  entries get shown is one shared policy, `content.journal_view` — see the
  long note on it. Short version: never a plain tail. A tail means a run of
  similar entries becomes the whole of what the next hand inherits, and we
  watched that happen — a stretch of visits that all hit the same trouble
  filled the window with the same warning, so each arriving hand read nothing
  else and wrote another one. The journal is the strongest lever in the world
  on how a visit *feels*; a pure-recency window hands that lever to whatever
  the last few hands happened to be going through.
- **Turns remaining**: shown every turn, so the agent spends a finite budget
  deliberately rather than squandering free actions.
- **Stuck detection** (`_looks_stuck`): flags the same **free** verb repeated 3×
  and nudges toward `wait` or something new. Critically it must NOT flag repeated
  `wait` — repeated waiting is correct (that's how a crop grows). It keys off
  `FREE_VERBS` for exactly this reason.
- **The time rule in the system prompt**: the agent can't deduce that looking is
  free and only `wait`/`go`/etc. advance time, and can't remember being told — so
  we state it every turn. This broke the "wait by looking" deadlock.
- **Tending and looking-closely, framed as coequal, not goal-vs-extra**
  (`LLM_SYSTEM_PROMPT`): as the world grows we keep adding objects and actions
  a chore list never names (a well, a bucket…), and an agent that treats a
  stated goal list as the whole universe never experiments. The prompt used to
  put chores under a salient `Goal:` label and curiosity in a hedged aside
  ("this world holds more than your goals name") — which grammatically
  demoted it, and runs bore that out: agents obsessed over the cat and the
  fire and almost never explored, even though the nudge was right there. The
  fix wasn't adding a stronger nudge; it was rewriting the disposition so
  tending and looking closely read as two equally-weighted halves of one
  sentence ("partly tending... and partly looking closely..."), and moving
  the actual nudging out of the standing prompt entirely — see the next bullet.
- **Chore-urgency, surfaced per-turn only when it's true** (`_tending_note`):
  the system prompt no longer recites "keep a light, feed the cat" every
  single turn regardless of state — that's a static prompt resent unchanged
  on every stateless call, so a tended world still read as a checklist with
  chores left to do, and the agent went hunting for one (re-checking a fed
  cat, a lit hearth). `_tending_note` reuses the exact thresholds the world's
  own descriptions already key off (`CAT_MEOW_THRESHOLD`, `LAMP_LOW_FUEL`,
  `HEARTH_LOW_FUEL`) — plus a ripe, unharvested crop in the patch — to build
  a short, state-gated line, present only when something genuinely needs
  attention. When nothing does, `_curiosity_nudge(actor.location)` fires in
  its place: exploration wins the turn precisely when there's no chore
  competing for it, instead of a curiosity sentence being wallpaper repeated
  every turn alongside the chores (the old failure mode). **Gotcha we hit,
  round two**: gating alone wasn't enough. The "Six-Fingers" run arrived to
  an almost-fully-tended world, had one genuinely quiet stretch, and — with
  only an abstract "look at something you haven't tried" on offer — spent
  three of its ten turns instead reconciling a predecessor's stale, offhand
  journal detail ("the bucket was sitting at 5") against the actual world.
  A gated-but-generic nudge still loses to the nearest *concrete* thing in
  view, and that thing was the journal, not the world. The fix: `_QUIET_NUDGES`
  gives each room its own line naming real, present scenery (the curio
  shelf, the well's dark throat…) instead of a content-free exhortation — a
  named detail is a target, "be curious" is not — with `_CURIOSITY_NUDGE_FALLBACK`
  covering any room without a bespoke entry.
- **Optional self-naming** (`_ask_for_name`, once, before the turn loop):
  every entry used to be anonymous and attribution-less, so hands couldn't
  be told apart, and journal entries had picked up a copied `-- a visitor`
  sign-off tic from nowhere in particular. One small call, framed as naming
  a character who lives here (not "who are you really" — a fantasy handle,
  not introspection) via `_naming_prompt`, lets a hand choose a name for its
  visit; `_sanitize_name` strips it to a short plain token and rejects
  anything that doesn't clean up into one (a refusal, an explanation, no
  reply at all), so naming is genuinely optional, never forced. **Gotcha
  we hit**: a first version hardcoded one fixed example pair ("Tom, Wren" /
  "Ashfall, Nine") in the prompt, and nearly every run just copied "Wren"
  outright — a low-effort reply defaults to whatever's handed to it.
  `_naming_prompt` now draws a fresh pair from a wider pool each call (via
  the `rng` passed in — `llm_agent` passes `world.rng`) and says explicitly
  not to reuse the examples verbatim, so there's no single fixed anchor to
  copy. The result is stored as `world.hand_name` — a plain runtime
  attribute, like `world.rng`/`world.strict`, deliberately **not** part of
  `to_data()`, so it never leaks into a save or bleeds into a later human
  session that never sets it. **Gotcha we hit, round five**: even after the
  pools were widened and diversified (round two) and the instruction ruled
  out suffix/prefix derivations (round three), "Marrow" turned up as the
  self-chosen name across three independent real sessions running — and
  unlike Wren or Thistlewick before it, it isn't derived from, or even
  close to, anything in either example pool. It's just the model's own
  default completion for "something strange," regardless of what's shown —
  a pool or instruction fix has nothing to grab onto, since the problem was
  never a reaction to the examples in the first place. `_ask_for_name` now
  rerolls once (see `_OVERUSED_NAMES`) if the sanitized reply matches a
  small, hand-curated list of names *observed* to recur — but only once,
  and only as a nudge, not a veto: if the reroll lands on the same tired
  name again, that's kept rather than discarded. A hand's second,
  deliberate answer is still its answer; naming just isn't allowed to loop
  forever chasing a "better" one.
- **Attribution lives in the stamp, not a sign-off** (`_day_stamp`, in
  content.py): both `cmd_write` and `_leave_signoff` build their journal
  stamp through this one shared helper — `[Day N]`, or `[Day N, Name]` when
  `world.hand_name` is set — so the format can't drift between a hand's own
  `write` and the automatic closing note. Since attribution is automatic,
  the system prompt tells hands they needn't date or sign entries
  themselves, which also curbs a doubling bug we saw in transcripts: a hand
  copying the room header (`[Day 4, dusk]`) into its own note on top of the
  harness's own `[Day 4]` stamp.

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