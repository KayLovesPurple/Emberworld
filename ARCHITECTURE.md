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
below):

- **Notice** — `look <thing>` shows the odd line, with a cat hint appended
  only for a `"plays"` reaction (`_found_description`). Free, pressure-free;
  a hand can just carry it and write about it.
- **Give to the cat** (`give <thing> to cat`, `cmd_give`) — consumes it from
  the pack, fires a reaction message, and turns the item into a fixed,
  non-portable trace in the room description (`_CAT_GIVE_REACTIONS` /
  `_CAT_GIVE_TRACES`, keyed by `cat_reaction`). A `"plays"` trace isn't done
  once it's given, either: `cat_replay` (cat.py) rarely bats at it again if
  it's still lying in the cat's current room — see "Cat replay" below.
- **Leave on the shelf** (`place`/`put <thing> on shelf`, `cmd_place`) —
  consumes it from the pack onto the hut's display-surface shelf, listed in
  `_shelf_description`; persists for whoever visits next.

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
- **`listen`, the forest's calm affordance.** A verb, gated to
  `forest_edge`, that costs a turn (it's not in `FREE_VERBS` — the
  turn-cost is what makes it a genuine choice, not a freebie) and returns
  one random line from `LISTEN_LINES`. **The constraint that must never
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

A follow-up to the pacing rebalance above, same shape as `listen`: a verb
(`watch`, cued in `available_actions` and room text as "watch clouds") that
costs a turn and returns one random line from `WATCH_CLOUD_LINES`, available
in the yard *and* at the forest's edge. Same never-break constraint —
grants nothing, ever — and the same direct-handler test pattern
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
than starting its own. On the third calm act at that spot, and only the
third, the returned line gains one quiet suffix: "You're getting to know
this stretch of quiet." Never before, never again after — not a running
status, not a buff, no confirmation of anything beyond that one line, same
discipline as the verbs it's attached to.

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

The shelf (above) is personal and reversible: a hand places a curio there,
and a later hand can `take` it right back. The cairn, at the forest's edge,
is the deliberate opposite — permanent and anonymous. `stack stone [on
cairn]` (`cmd_stack_stone`) consumes a carried stone-named curio outright
(`world.entities.pop`, not a location change) and adds `world.rng.choice(
CAIRN_GROWTH_CM)` (2-5, textured rather than fixed) centimeters to the
`cairn` entity's `height_cm` attr. Once stacked, a stone is nobody's again —
it's part of something the whole lineage is building, one stone at a time,
that no single hand owns or can undo. Only stone-named curios qualify (`"
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

The first thing in the whole game with a real, un-guaranteed outcome. Below
`SAFE_DEPTH_THRESHOLD` (3), `return` is exactly what it's always been —
`world.forest_depth -= 1`, no randomness, airtight. That floor matters: a
short, casual dip into the forest must never be punished, or the risk would
just be a tax on curiosity rather than a cost of going deep on purpose.

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

No penalty rides along with the mismatch — no damage, no dropped items, no
extra turn burned. The disorientation *is* the whole cost, per the calm-axis
invariant's own logic applied to risk instead of reward: the interesting
thing is the uncertainty itself, not a punishment bolted onto it.

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
shape, only the number it compares against. One easy misreading worth
heading off: marking depth 6 does **not** make a return *from* depth 7
exact — it raises the floor, it doesn't open a corridor for ground gained
since the last mark. Returning *from* the marked depth itself (6, in this
example) is exact, precisely because 6 is no longer greater than the
(now-raised) safe floor; one step further than your last mark is still
real risk, by design — the risk lives specifically in the gap between
where you last marked and how far you've pushed since, which is what
makes marking-as-you-go a meaningful habit rather than a one-time flag to
set and forget.

Never lowers an existing mark (marking shallower than a prior mark is a
harmless no-op, refused with a distinct message rather than silently
succeeding) — there's no way to mark yourself back into more danger.
Costs a turn like any real action, needs nothing consumable, and is gated
out of `available_actions` once redundant (depth 0, or already marked at
the current depth) — same legibility rule as everywhere else in the game.

## The full moon — the one exception to the night withdrawal

`watch clouds` at night has always been a clean withdrawal (`WATCH_CLOUDS_
NIGHT_MSG`), never a forced line — see the pacing-rebalance section above
for why that honesty mattered. The full moon is the single exception, and
it's built to still honor that reasoning rather than undercut it:
`_is_full_moon(world)` is `world.day() % MOON_CYCLE_DAYS == 0` (29) — a real
clock keyed to the day count, not a dice roll and not anything session-
scoped, so it's the one place a hand can actually *witness* the world
running on a schedule bigger than any single visit, rather than just being
told that's true. `available_actions` offers `"watch clouds"` at night only
on these nights (`world.py` imports `_is_full_moon` the same deferred way it
already imports `_crop_in`/`_patch_in`/`find_visible`, for the same
circular-import reason).

Deliberately inert beyond the text: the moon must never light the room (no
free lamp-substitute — `test_moon_line_touches_no_world_state` asserts
`w.is_dark("yard")` stays true right after the call) or touch state in any
other way. Same never-break constraint as `listen`/`watch_clouds` by day,
just gated by date instead of a probability roll.

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