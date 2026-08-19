# Emberworld — Architecture

This is the map for whoever builds on the world next (including future you, and
future Claude). It explains how the pieces fit, the few rules that keep it from
breaking, and the recipe for adding a feature safely.

## File layout

- `world.py` — the engine. `Entity`, `World`, the tick loop, persistence,
  `check_world`. Generic: it has no knowledge of any specific verb or
  behavior, only the `VERBS`/`FREE_VERBS`/`BEHAVIORS` registries (declared
  here as empty containers) that content.py populates. Session-scoped state
  (forest depth, calm-visit acks, the hand's chosen name, …) lives on
  `World.visit`, a `VisitState` dataclass — one place for a new session
  field to go, kept out of `to_data()` by construction rather than by
  remembering to exclude each new key by hand.
- `content.py` — Emberworld itself. The verbs, the autonomous behaviors,
  `build_world`, and the self-documenting reference generator. Imports
  `World`/`Entity` from world.py and fills in its registries.
- `content_common.py` — pure helpers shared by content.py, cat.py, and
  drivers.py without any of them importing each other: `_the`, `_is_raw`/
  `_is_cooked`, `_last_potato_beat`, `day_stamp`, and the actor's own
  hunger bands (`ACTOR_HUNGER_*`, `actor_hunger_line`,
  `actor_self_care_note`). Imports nothing — that's what lets three
  otherwise-cyclic modules all reach it at module level. See "Actor hunger"
  below and the cat.py paragraph further down for why it exists.
- `cat.py` — the cat as its own self-contained subsystem: its constants
  (`CAT_HUNGER_CAP`, `CAT_MEOW_THRESHOLD`), its behaviors (wander/hunger/idle),
  its verbs (feed/pet), and `build_cat`. Split out of content.py once it
  grew into a coherent slice on its own — see "Where to go next" below for why,
  and why it split before a registration pattern did. (Naming — `name cat
  <name>` — lives in content.py, not here; see "The chicken" below for why.)
- `chicken.py` — the chicken, `cat.py`'s sibling subsystem: a gentle
  producer (never a second hungry mouth), its two behaviors (idle/lay),
  and `build_chicken`/`ensure_chicken`. See "The chicken" below.
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
- `test_world.py` / `test_cat.py` / `test_chicken.py` / `test_drivers.py` /
  `test_lineage_memory.py` — the test suite for those modules. content.py's own tests are split
  further, by subject, into `test_hut_basics.py`, `test_curios.py`,
  `test_forest_edge.py`, `test_forest_venture.py`, `test_journal_and_seed.py`,
  and `test_riverbank.py` (see the split note lower in this doc for why and
  how). All of it shares a couple of helpers via `_test_helpers.py`.

**test_content.py's split.** It grew to 4,623 lines -- bigger than
content.py itself -- across 16 numbered sections that already grouped
cleanly by subject, so it split along those boundaries rather than into a
`tests/` subfolder: this project keeps everything flat at the repo root on
purpose, and nesting would have added import friction for no reduction in
any single file's size, which was the actual problem. Six files came out
of it, each independently runnable exactly like before
(`python3 test_curios.py`, etc.), each renumbering its own sections
sequentially from 1 rather than keeping the original global numbers, which
would otherwise read as gaps (a file with only sections 8 and 9 in it,
say). Two helper pairs turned out to be used by tests that landed in
different files -- `_add_curio`/`_curio_tuple` (curios, forest venture,
journal/seed) and `_Lucky`/`_Unlucky` (curios, forest edge, forest
venture) -- and moved into `_test_helpers.py`, the one place already
shared across every test file; everything else stayed local, defined right
next to the tests that use it, since that was already true of nearly every
helper once grouped by section.

BUG WE HIT while doing this by hand with `sed`/text surgery rather than a
proper refactoring tool: a line-removal script keyed on `startswith("class
_Lucky")` (meant to delete the `_Lucky`/`_Unlucky` pair once they'd moved)
also matched `class _LuckyWood:`, a third, unrelated test double defined
much further down the same section -- silently deleting its whole
definition while leaving its call sites intact, which only surfaced as a
`NameError` once the split files were actually run. Caught by running
every new file and comparing pass counts against the original, not by
inspection -- worth remembering next time a mechanical split feels safe
enough to skip that check: diffing the full set of `test_` function names
between old and new (`344` in, `344` out) is what actually confirmed
nothing else had gone missing the same way.

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

`PRESENCE_RULES` (content.py) is the fifth, and the same move one layer down:
`_room_here` — the helper `find_visible` and every verb that resolves a name
reach through — used to name the statue and the cairn by id, so the forest's
rules lived inside the game's most basic visibility check. Now a conditional
entity registers `fn(world, actor) -> bool` from wherever it belongs, and the
helper just asks. `PRESENCE_LAST` sits beside it for the one entity whose
*position* is also deliberate: the statue lands at the end of a listing
rather than in insertion order, which the old implementation got by
filtering it out and re-appending it. That was undocumented and untested,
and rewriting the function as a plain filter silently changed it — see
`test_the_statue_stays_last_in_the_room_listing_after_later_arrivals`, which
exists because the test suite did not catch that and a differential run did.

content.py and cat.py had the same shape of problem, one level up: content.py
imports `build_cat`/`CAT_HUNGER_CAP`/`CAT_MEOW_THRESHOLD` from cat.py at
module level (so `build_world` and `generate_reference` can use them), while
cat.py's `cmd_feed`/`cat_replay` needed content.py's `_is_raw` (to prefer a
raw potato over an already-cooked one), `_last_potato_beat` (the one-shot
line fired when a raw potato fed to the cat happens to be the last one), and
`_the`. Importing content.py from cat.py at module level would close the
same kind of cycle, so those two spots used to do the import inside the
function body instead — same fix, same reasoning, as the world.py/content.py
case above.

That deferred-import fix worked, but it meant the shared logic still *lived*
in content.py, owned by neither side — cat.py was borrowing content.py's
internals just to avoid a cycle, not because the helpers were conceptually
content's. `content_common.py` is the real fix: `_the`, `_is_raw`/
`_is_cooked`, `_last_potato_beat`, and `day_stamp` moved out into a module
that imports nothing, so content.py, cat.py, and drivers.py can all import
it directly at module level. cat.py's only remaining deferred import is
`cmd_add_wood` (inside `cmd_feed`, for the `feed hearth` alias) — a real verb
handler, which has to stay in content.py rather than move to a helpers-only
module. One fewer deferred import is a small win on its own; the larger one
is that the next feature needing something both cat.py and content.py agree
on (tea, more curios, whatever) now has an obvious home instead of a choice
between growing the cycle or duplicating the helper.

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
test_curios.py pins this by calling `cmd_give`/`cmd_place` directly rather
than through `world.act` — going through the dispatcher would tick the
world and let unrelated autonomy (hunger rising, fire burning down) muddy
what the handler itself did or didn't touch.

Legibility rides on the object, not the parser: a `"plays"` curio's own
look-line ends "— the cat might bat at it", and `give`/`place` only appear
in `available_actions` when there's a carried curio (and, for give, a cat)
to act on — nothing to memorize.

**`take`ing a cat-given trace back gets its own refusal, not the generic
one.** `cmd_take`'s fallback for anything non-portable is "The {thing}
won't budge" — true of a real fixture (the cairn, the charm-string, shaped
clay), but not really true of a curio the cat's already had: it isn't
heavy, it's just not yours anymore. `attrs["curio"]` still `True` on a
non-portable entity is a safe, unambiguous signal that it's specifically a
cat's trace — every other permanent fate (the cairn, the charm-string, the
journal-tuck) consumes the entity outright rather than leaving a claimed
one behind, and the mystery seed's bloom flips `curio`/`portable` together
in the same tick (`blooming`), never separately — so `cmd_take` checks for
it first and answers "It's the cat's now, you can't have it." before
falling through to the generic fixture message. Deliberately not fixed by
making cat-given items portable again, which would reopen a rescue path
into the cairn/charm-string this design rules out on purpose — give-to-cat
stays a one-shot, irreversible gesture, the same permanence as those two.

**BUG WE HIT: a cat-given trace could shadow a real, takeable copy of the
same curio.** `cmd_take`'s own top-of-function note already covers the
"already carrying" version of this — `find_visible`'s match order is here
+ carried + displayed, so a match found earlier in that order shadows a
better one found later. A cat's trace sits directly in the room (`cmd_give`
sets `e.location = actor.location`), which comes *before* "displayed" (the
shelf) — so a pinecone already given to the cat shadowed a completely
different, still-live pinecone sitting on the shelf: `take pinecone`
answered "It's the cat's now" even though a real copy was one shelf-slot
away, discovered live by an LLM hand that had correctly reasoned its way to
"take a pinecone from the shelf" and then got refused for a reason that had
nothing to do with the shelf at all. `prefer=lambda x: x.location !=
actor.id` wasn't enough on its own — it rules out the copy already in
hand, but says nothing about a copy that can never end up in hand. Fixed by
also requiring `x.portable`, so the preference now means what `take` is
actually for: end up holding the thing, not just "some copy that isn't
already carried."

**BUG WE HIT: the hint-backfill guard stopped new corruption but never
healed old corruption.** The `entity.portable` guard on the
`STONE_CAIRN_HINT`/`CHARM_STRING_HINT` backfills (above, in `ensure_shelf`)
only stops the hint from being *added* to a cat trace going forward — a
world saved before that guard shipped already had the wrong text baked
directly into the trace's own `.description` ("given to the cat and
roundly ignored — it could be threaded onto the charm-string in the
hut."), and the guard alone never touches text that's already there. Found
in this project's own live save file: five buttons/pebbles given to the
cat before the fix, still carrying the stale hint after it. `ensure_shelf`
now also actively strips either hint from any non-portable curio's
description on every load (`entity.description.replace(f" — {hint}.",
".")`), not just refuses to add a new one — the same "resync on every
load, not only on the next relevant action" pattern `ensure_cairn` already
uses for `CAIRN_BANDS` drift.

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
`test_no_forest_fragment_reads_as_a_refusal_marker` in `test_forest_venture.py`
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

**Stone → cairn legibility fix.** `stack stone on cairn` worked from Stage
7 on, but for a long stretch the cairn was only ever *named* in the
forest-edge room text — a cue a hand loses the moment they carry a stone
anywhere else. Observed in play: the shelf filled with duplicate stones
(10/10, several of them stones) while the cairn barely grew, and across a
long lineage only one hand had ever used it. Same family as `name cat`'s
fix and the shelf's own `_shelf_description`: an affordance that already
works but wasn't legible at the moment a hand could act on it. The cue now
rides on the stone itself rather than the room — `_found_description`
takes an optional `name` and appends `STONE_CAIRN_HINT` ("it could go on
the cairn at the forest's edge") whenever `"stone" in name.lower()`, the
same substring check `cmd_stack_stone` already uses. It fires every time
the description is shown — no fatigue, no first-sighting-only gating,
consistent with the shelf always stating its own capacity regardless of
who's asking or how many times. `ensure_shelf` backfills the hint onto any
already-found stone from an older save, the same move as its existing
`cat_reaction` backfill just above. Scope stayed narrow on purpose: found
stones are the only curio with a cairn-shaped second fate, so this doesn't
touch the room description, `cmd_stack_stone`'s own behavior, or nudge the
shelf itself — worth watching whether the stone's own description is
enough before adding a second nudge elsewhere.

## Tuck in journal — a physically honest fate for flat curios

The shelf's "displayed object" logic doesn't fit everything a curio could
be. A feather (and, once it exists, the mystery seed's bloom — see
`_is_tuckable` below) has an obvious real-world home the shelf never quite
captures: pressed flat into a book. `tuck <thing> in journal` (`cmd_tuck`)
gives it exactly that, in the same family as the cairn (a distinct,
physically appropriate fate, not folded into the generic curio system) but
distinct from it too: the cairn is collective and anonymous, the shelf is
personal and reversible, and this is personal *and* permanent — the
one-way half of the shelf/cairn contrast, applied to a hand's own visit
rather than the whole lineage.

**Scope, deliberately narrow.** `_is_tuckable(e)` returns true for
anything with `"feather"` in its name, or with a `blooms_at` attr — the
bloom is matched by that attr rather than by name because `BLOOM_KINDS`
includes entries like `"a single black bloom"` that don't contain the
word "flower" at all. Everything else (a pinecone, a stone, a button) gets
`TUCK_REFUSAL`, an in-world "that won't press flat between the pages," not
an error. No catch-all "tuck any curio" verb — round/dimensional curios
don't have a fate here, on purpose; see the tuck-in-journal spec's
"Explicitly NOT in scope."

**Which entry it attaches to.** A tucked item joins `journal.attrs["tucked"]`,
a `{str(entry_index): [item_name, ...]}` map (string keys because
`to_data()` round-trips through JSON, which stringifies int dict keys
anyway — keying by `str()` from the start avoids a same-value,
different-type bug appearing only after a save/load). The entry it joins
is *the one active this visit* — `world.journal_entry_index`, a new
`VisitState` field alongside `forest_depth`/`calm_visits`/`hand_name`, so
it's session-scoped and never persists. `cmd_write` sets it to the entry
it just appended; `_journal_entry_index` (used only by `cmd_tuck`) reuses
that same index if one's already active this visit, or creates a
placeholder entry ("— nothing written this visit.") and activates that
instead. This is why a visit that only tucks
and never writes still works, and why two tucks in one visit with no write
land on the *same* placeholder rather than each minting their own.

**BUG WE HIT, spotted from a session transcript: tuck-then-write split the
feather's note away from the entry it belonged with.** The paragraph above
covers write-then-tuck (the tuck reuses the write's entry) and tuck-then-
nothing (the placeholder stands alone). It didn't cover tuck-then-write: a
real session tucked a feather, then wrote a real entry a couple of turns
later, and `cmd_write` — which always appended a fresh entry and pointed
`journal_entry_index` at it, with no awareness of what was already active —
left the feather's note stranded on the throwaway placeholder ("— nothing
written this visit.") while the actual entry sat right next to it,
feather-less. A new `VisitState` field,
`journal_entry_is_placeholder`, marks whether the currently active entry is
still a bare tuck placeholder; `cmd_write` now checks it and, if so,
overwrites that placeholder's text in place instead of appending a second
entry, then clears the flag. Net effect: tuck-then-write and write-then-
tuck now land on the *same* entry either way, which is the behavior a
reader would assume without knowing the ordering mattered internally.

**A wording redundancy caught right after, from the same real transcript.**
The placeholder's original text ("— nothing written, just left something
pressed here.") described the tuck itself, but `_tucked_line`'s own
parenthetical *always* follows a placeholder entry — this function is only
ever called from `cmd_tuck`, immediately before it records the tuck — so
the two sentences said "pressed" twice in one short line: "...pressed
here. (a small brown feather is pressed into this page.)" Reworded to
"— nothing written this visit.", which says only what the parenthetical
doesn't already cover.

**No duplication, by construction, not by a check.** `cmd_tuck` calls
`world.entities.pop(e.id, None)` — same move as `cmd_stack_stone` — so a
tucked item stops existing as an entity at all the instant it's tucked.
There's no separate invariant to maintain: it cannot simultaneously sit in
a room, a pack, the shelf, or the cairn, because there's nothing left
anywhere to sit. `take` has nothing left to find, either.

**Reading it back.** `cmd_read` needs to know not just *what's* shown on a
spread read but *which entry index* each shown line came from, so it can
look up `journal.attrs["tucked"]` per line. `journal_view` itself only
ever returned entry text, and changing that would break every existing
caller and test, so its selection logic was pulled out into
`_journal_view_indices` (indices and `None`-for-gap, instead of text and
`JOURNAL_GAP`) — `journal_view` now just maps that over `entries`, byte-
identical output to before. `cmd_read` calls `_journal_view_indices`
itself to get the same picks as indices, then appends `_tucked_line` per
shown entry. `read journal all` does the same over every index via
`enumerate`. Availability follows the usual rule: `journal_actions` only
offers `tuck <item> in journal` once a tuckable item is actually in hand.

## The riverbank and clay — cosmetic-only, per `docs/CLAY_SPEC.md`

A new room, `"riverbank"`, structurally parallel to the forest's edge: its
own branch off the yard (`yard.exits["river"]`), not nested inside or
gated behind forest depth. `ensure_riverbank(world)` backfills both the
room and the yard's exit onto an older save, same role as
`ensure_shelf`/`ensure_cairn` — called from `build_world()` and from
`drivers.load_or_build`'s reload path. The exit backfill uses
`yard.exits.setdefault("river", ...)`, so it's idempotent and never
clobbers a hand-edited or already-backfilled exit.

**The two calm verbs needed no new syntax.** `cmd_listen` and
`cmd_watch_clouds` already discard their `arg` entirely — `watch clouds`
and bare `watch` have always behaved identically. So `listen` gained a
second location branch (`RIVER_LISTEN_LINES` at `"riverbank"`, alongside
`LISTEN_LINES` at `"forest_edge"`) and `cmd_watch_clouds`/`sky_actions`
simply added `"riverbank"` to their location tuples — reusing the existing
`WATCH_CLOUD_LINES`/moon logic outright, since the riverbank reads as open
sky. `_calm_visit_ack` was already keyed by spot rather than verb, so
`"riverbank"` just became a new key beside `"forest_edge"`, tracked and
acknowledged (`CALM_ACK_AT`) completely independently.

**`gather` is now a second location-branching verb**, the same shape
`cmd_add_wood`/`cmd_listen`/`cmd_watch_clouds` already are: at
`forest_edge` it's untouched (the abstract `actor.attrs["wood"]` counter);
at `"riverbank"` it creates a discrete carried entity instead — `"a lump
of raw clay"`, `attrs={"raw_clay": True}` — because shaping needs
something specific to consume, the same shape as a raw potato existing
before `cook`. Deliberately one lump per gather, not a
`WOOD_PER_GATHER`-style multi-unit yield: shaping is an occasional,
deliberate act, not a nightly consumable, so a bigger yield would only
clutter a pack with unused lumps.

**`shape clay into <name>` (`cmd_shape`) is deliberately strict** — only
that one phrasing parses, via a plain prefix check on `arg`
(`"clay into "`). The name is sanitized exactly like `cmd_name` (the cat's
own naming verb): strip whitespace, drop a leading quote, keep only the
first line (blocks multi-line injection into world prose), cap the length
(`CLAY_NAME_CAP = 40`, more room than the cat's 24 — this names a short
object phrase, not a proper name). One extra step beyond `cmd_name`: a
leading article (`"a "`/`"an "`) is stripped *before* the cap, the same
double-article guard `_the()` already applies to found curios — a hand
naturally types `shape clay into a squat dish`, and the verb always
auto-prefixes `"a clay "` itself, so without this guard every shaped
object would read `"a clay a squat dish"`.

The result is a plain, permanent `Entity`, added directly into the
actor's own hands (`location=actor.id`) rather than the room. It is
**not** tagged `curio=True`, and deliberately so: it's authored by the
hand's own chosen name rather than drawn from a found pool, so it doesn't
want a place in the shelf/cairn/give-to-cat/tuck-in-journal system at all
— that quartet is already carrying real weight (see "Curio visual
compression" below). `riverbank_actions` follows the usual "only offer
what can do something" rule: `shape clay into <name>` only appears once a
raw lump is actually carried.

**BUG WE HIT, caught in real play: `portable=False` (v1's choice) meant a
hand couldn't take away the thing it had just made.** A real session
shaped a clay cup at the riverbank, looked at it, then tried to carry it
back and found no `take` offered at all — because v1 placed the object in
`actor.location` and marked it non-portable on purpose, reading "made and
left, part of the room" the same way a cairn stone or an unopened bloom
is. The difference the original design missed: those are *collective or
timed* — the cairn belongs to the whole lineage, a bloom is deliberately
not yours to rush — while a clay object is a hand's own, freely-named,
private thing, closer in spirit to a found curio than to either. Fixed by
flipping `portable=True` and placing it straight in the actor's hands
instead of the room, so shaping something no longer requires a separate
`take` step to actually keep it. Still not `curio=True`, so still outside
the shelf/cairn/give-to-cat/tuck disposal system on purpose — but since
`cmd_place` (the shelf) was never curio-gated in the first place (the
lamp and knife could already be shelved), a shaped object can now sit on
the shelf too, for free, with no new code. Still not usable for anything
beyond that: no functional making, per the open question `README.md`'s
"Someday" section still leaves deliberately unresolved.

## The chicken — a producer, per `docs/CHICKEN_SPEC.md`

A new subsystem file, `chicken.py`, structurally the sibling of `cat.py`:
its own constants, its own two autonomous behaviors, `build_chicken`, and
`ensure_chicken` (backfill, same role as `ensure_riverbank`/`ensure_shelf`
— called from both `build_world()` and `drivers.load_or_build`). Built
into every fresh world in the yard, the same way `build_cat` adds the cat
to the hut.

**THE CONSTRAINT THAT MUST NEVER BREAK**, stated at the top of
`chicken.py` itself the same register as the cat's own GENTLE GUARANTEE:
no `hunger` attr, ever, at any point in the chicken's lifecycle. The
chicken is the deliberate *opposite* of the cat — pure source, never
cost — and a hunger attr is exactly the trap `docs/CHICKEN_SPEC.md`'s "A
trap explicitly not being built" names. `chicken_idle` (ambient flavor,
mirrors `cat_idle`) has no hunger gate to check, unlike the cat's own —
there's nothing to gate on. `chicken_lay` is a second, independent
per-tick roll (`CHICKEN_LAY_CHANCE`) that creates one `"an egg"` entity in
the chicken's room and announces it — deliberately **not** a found-roll
riding on another action the way `forest_finds` rides on `gather wood`;
an egg is discoverable by being in the room, not by a chance on a
deliberate forage action. No `chicken_wander` exists — the chicken stays
in the yard, permanently, by the simple absence of any behavior that
would move it (mirrors how the cat's own wander is confined to the
in/out exit pair `_cat_go` knows how to narrate — an unwritten behavior
is the actual mechanism keeping the chicken in place, not a location
check anywhere).

**Eggs are not curios.** Same reasoning as raw/shaped clay: an egg is
produced by the world on its own schedule, not found-and-disposed-of, so
it stays off the shelf/cairn/give-to-cat/tuck-in-journal system entirely
— no `curio=True`, not offered by `give`/`stack`/`tuck`. (The shelf
itself is permissive of any portable item regardless of the `curio` flag
— pre-existing behavior, not something eggs or clay changed — so `place
egg on shelf` still works exactly as `place knife on shelf` always has;
what's excluded is specifically give-to-cat/cairn/tuck, which DO gate on
`curio=True`.) Eggs pile up with no cap, the same shape unharvested
potatoes already have — no new capacity mechanic needed.

**`cmd_cook` generalized from a potato-only hardcode into a small table**
(`COOKABLES`, keyed by the substring `find_visible` matches in a carried
item's name — the same substring convention `find_visible` itself
already uses) rather than writing a parallel `cmd_cook_egg`. Each entry
carries its own `cooked_name`/`cooked_desc`/`food_value`/`cook_line`, so
`cook potato` is byte-identical to before (same table entry, same
strings) and `cook egg` follows the identical path with its own. The
lit-hearth requirement stays a single shared check, not duplicated per
recipe. `_last_potato_beat` (the one-shot "last raw potato" pang) is
gated to fire only for the `"potato"` key — an egg was never seed, so it
never owes that beat, the same reasoning the pang's own docstring already
states for cooked food generally. `cmd_eat` needed **no changes at all**:
it already works on anything with `attrs["food"] > 0` regardless of name.

**Naming moved out of `cat.py` into `content.py`.** `cmd_name` used to be
cat-only, hardcoded to `world.get("cat")`, living in `cat.py` alongside
`cmd_feed`/`cmd_pet`. Now that a second nameable animal exists,
duplicating it into a parallel `chicken.py` copy would let the two drift
apart for no reason — instead `cmd_name` generalized and moved to
`content.py`, the one place already allowed to know about both
subsystems at once (the same placement `cmd_give` — cat-specific but
content.py-resident — already established). `_NAMEABLE_ANIMALS` is a
small dict (`{"cat": ..., "chicken": ...}`) whose **iteration order is
load-bearing**: cat is checked first, so a bare `name <name>` with no
prefix keeps defaulting to the cat exactly as it always has — only
`name chicken <name>` needs its explicit prefix, since there was no
bare-name precedent to preserve for the chicken. `_animal_description`
dispatches to `_cat_description`/`_chicken_description` (both still
species-owned, imported into `content.py`) to refresh the right entity's
standing description after naming.

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
  (test_forest_edge.py) is Stage 3's exit criterion made literal: venture eight
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
`_AlwaysOffCourse`/`_AlwaysOffCourseHigh` (test_forest_venture.py) both force
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

**BUG WE HIT, found in real play: ambient lines read as run-on sentences.**
`FOREST_AMBIENT` was originally written like `FOREST_FRAGMENTS` — bare,
lowercase clauses with no trailing period — but the two pools are composed
completely differently. `describe_forest` joins several `FOREST_FRAGMENTS`
picks with `"; "` and capitalizes/punctuates the *whole* joined line once,
at the end. `_forest_ambient`, though, just space-prefixes its one pick and
appends it directly onto an already-complete, period-ended sentence
(`describe_forest`'s own line, or — worse — the statue's `STATUE_DISCOVERY_
TEXT`, which also ends in a period). Style borrowed from the wrong sibling:
a hit read as "...the way you'd toss a coin in a fountain. something
rustles low in the undergrowth, gone by the time you look" — no capital,
no closing period. Fixed by writing `FOREST_AMBIENT` as complete sentences,
same convention as `LISTEN_LINES`/`WILDLIFE_LINES`/`MOON_LINES`, all of
which really are appended standalone rather than joined into one line.
`_forest_ambient` itself didn't need to change. See
`test_forest_ambient_lines_are_well_formed_sentences` and
`test_venture_composes_discovery_and_ambient_as_proper_sentences`, the
latter pinned to this exact discovery-plus-ambient combination.

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
the statue's entity lazily, on discovery — unlike `ensure_shelf`/`ensure_
cairn`, it isn't wired into `load_or_build`, since most visits (plausibly
most whole lineages) may never find it at all, and nothing else needs the
entity to exist before then.

**BUG WE HIT, found in real play, requested as a small follow-up: `look
statue` was unreachable for a lineage's very first discovery.**
`ensure_statue` used to run only from `cmd_wish`, so `cmd_venture`'s
discovery branch set `statue_found_this_session` and returned the one-time
discovery paragraph, but never actually created the entity — `find_visible`
had nothing to find, so `look statue` failed with "you don't see any
'statue' here" until *after* a hand had already wished on it. Backwards,
since the description's whole job (see below) is nudging a hand toward
wishing in the first place. It went unnoticed because it self-heals
permanently the first time anyone in the lineage ever wishes — the entity
persists in the save from then on, so every later hand's discovery already
finds it lookable. Fixed by having the discovery branch call `ensure_
statue(world)` itself, same idempotent function `cmd_wish` already used, so
creation now happens exactly once, at the moment it's first needed, however
a hand gets there. `test_wish_touches_no_state_besides_the_statues_own_
wish_log` had baked in the old "wish creates the entity" timing as an
assertion; updated to assert wish adds/removes nothing (the entity already
exists by then) while still pinning that only the wish log itself changes.

While fixing that, also gave the base description its own quiet nudge:
`"...the kind of thing a hand leaves a wish with, the way you would a coin
in a fountain"` — the same register `STATUE_DISCOVERY_TEXT` already uses,
folded into the permanent `look statue` text too, not just the one-time
discovery paragraph. README's "wishing-statue" section already claimed
"the statue's own description hints that wishing here is a thing people
do"; this makes that literally true of `entity.description`, not just of
the discovery text. Same restraint applies here as everywhere else about
the statue: never a word implying it hears, listens, grants, knows, or is
aware — `test_look_statue_vaguely_hints_at_wishing` checks for both the
hint and the absence of those words.

**Two more real-play follow-ups landed with the hint, both about it not
actually reaching anyone yet.** First: `STATUE_DISCOVERY_TEXT` used to be
appended straight onto `describe_forest`'s line with a single leading
space ("...turning to something else. Between two trunks..."), so a real
find read as just one more clause of ambient forest texture instead of an
actual discovery. `cmd_venture` now leads it with a blank line
(`"\n\n" + STATUE_DISCOVERY_TEXT`) instead — `_forest_ambient`'s own
leading space is untouched, since that one really is meant to read as
part of the same breath, not a separate beat. Second, and the more load-
bearing one: the hint text only ever reaches a *newly created* statue —
any lineage where a wish had already been made before this fix keeps that
statue's old-style description forever otherwise, since `ensure_statue`'s
`if statue is None` branch never runs again once the entity exists. Exact
same shape as the stone→cairn legibility bug's own backfill requirement.
Fixed with the same pattern `ensure_shelf` already uses for
`STONE_CAIRN_HINT`: `STATUE_WISH_HINT` pulled out as its own constant so
`ensure_statue` can check for it by substring on an *existing* statue too,
appending it in place when missing — guarded by the substring check
itself, so a second pass, or a statue that already carries it, is a
no-op. See `test_statue_discovery_starts_on_its_own_paragraph` and
`test_ensure_statue_backfills_the_wish_hint_onto_a_legacy_statue`.

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

**BUG WE HIT, a real recurrence of the one above, found in actual play:**
`_room_here`'s gate is only half the fix — it stops the statue being
*shown* once `forest_depth` drops back below `STATUE_MIN_DEPTH`, but
nothing was actually decrementing `forest_depth` on the way out. `return`
does, one step at a time (with its off-course risk), but forest_edge's
plain `"yard"` exit is *also* a valid way to leave at any depth, and
`cmd_go` just relocated the actor without touching it. Leave via `go
yard` while still deep and `forest_depth` stayed stuck there across the
trip to the yard; a later `go forest` shows the fixed, shallow arrival
text (the same text every entry gets, regardless of depth), but the
statue's presence rule was still reading the stale deep value and passed,
surfacing the statue at what reads as a first arrival. Fixed in `cmd_go`:
leaving `forest_edge` for anywhere else resets `world.forest_depth` to
`0`, so the exit is as final as walking all the way back with `return`.
See `test_leaving_the_forest_without_returning_resets_depth_on_next_entry`.

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

## Actor hunger — legible everywhere the cat's already is

**The problem, observed across LLM session transcripts:** the cat's hunger
is loud — `look` lists it, `_tending_note` flags it once it crosses
`CAT_MEOW_THRESHOLD` — while a hand's own hunger was silent everywhere
except `cmd_inventory`, a view nothing prompts a hand to check. A hungry
cat competes for attention every turn; a hungry hand doesn't even know to
ask. The predictable result: every spare potato went to the cat, because
the cat was the only one visibly asking for it.

**The fix is one helper, read in three places.** `content_common.py` holds
the bands (`ACTOR_HUNGER_STUFFED`/`_FINE`/`_HUNGRY`, `ACTOR_HUNGER_CAP`) and
two functions: `actor_hunger_line` (`"You feel hungry."`, `cmd_inventory`'s
exact wording) and `actor_self_care_note` (`"you're getting hungry"` /
`"you're ravenous"`, phrased for a sentence rather than standing alone).
`cmd_inventory` and `content.py`'s `_carried_line` — the one function both
branches of `cmd_look` (lit and dark) already funnel through — both call
`actor_hunger_line`, so `look` and `inventory` cannot read different moods
for the same hunger value; `drivers.py`'s `_tending_note` calls
`actor_self_care_note` first, ahead of the cat/lamp/hearth/crop checks, so
a hand's own hunger competes on equal footing with the world's asks instead
of losing to them by default.

**Deliberately not done, in this first pass:** no new verb, no buff — the
legibility fix itself never touched `hungering`/`cmd_eat`, just made an
existing value visible in more places. The three call sites are checked
against each other directly
(`test_inventory_and_look_report_the_same_hunger_mood`) rather than each
pinned to a hardcoded string, so the bands can move without three separate
edits falling out of sync. (The numbers themselves *did* move shortly
after, once legibility exposed a problem with them — see immediately
below.)

**The retune, one real session later.** Making hunger visible surfaced a
second problem it didn't create: [Thistle's transcript](sessions/20260808-113503_thistle_day-25_20-turns.md)
shows a hand arriving near the cap, eating once, and being told
"you're getting hungry" a turn later anyway — the old numbers (cap 20, nag
at 10, one meal worth 8, i.e. 40% of the cap) meant a single meal from the
cap only ever reached 12, still above the nag threshold. The hand chased
the note across three more cook-and-eat cycles in one 20-turn visit,
burning potatoes and turns on a signal one meal should have resolved. This
had always been true of the numbers; it just took the note actually
firing somewhere a hand would see it (`look`, the tending note) for the
mismatch to matter.

The fix is a ratio fix, not just a bump: doubling `ACTOR_HUNGER_CAP` (20 →
40) and its bands in step (same proportions — nag at 50% of cap, ravenous
at 80%) would have reproduced the identical problem at a new scale, since
what actually matters is food-value-as-a-fraction-of-cap, not any
constant in isolation. `cmd_cook`'s `POTATO_FOOD_VALUE` went from 40% of
the old cap to 75% of the new one, so one meal now clears the nag with
real margin from anywhere, including straight off the cap.
`test_one_meal_from_the_hunger_cap_clears_the_getting_hungry_note` pins
the relationship itself (post-meal hunger must land below the nag
threshold), not any single number, so a future edit to the cap or the
food value in isolation fails loudly instead of quietly reintroducing the
chase.

### Player-hunger pacing — the second retune, and a discoverability fix alongside it

[A real 35-turn session](sessions/20260817-213212_thistlewick_day-56_35-turns.md)
surfaced two more problems in the same area, found together but fixed for
different reasons.

**The pacing problem: even the retuned numbers above escalated too fast
for a real visit, and "ravenous" itself was the sharper issue.** The
session went fine → hungry by turn 3 and hungry → ravenous by turn 18 —
nearly half a 35-turn budget spent escalating before the hand even reached
a ripe potato, let alone cooked and ate one. The fix repeats the same
ratio-preserving move as the first retune: `ACTOR_HUNGER_CAP` doubles
again (40 → 80), `ACTOR_HUNGER_STUFFED`/`_FINE` and `POTATO_FOOD_VALUE`
move in step so "one meal clears the nag with real margin" still holds
exactly. But timing wasn't the only problem: "ravenous" is a strong word,
and a hand narrating its *own body* that way tended to treat it as
something to resolve above nearly everything else — unlike the cat's
hunger, which describes an external creature's need, not the hand's own
stated condition, so the same escalating language doesn't carry the same
pull. Rather than just delay the top tier, it's removed outright:
`actor_hunger_mood` now has exactly three bands (stuffed/fine/hungry), and
"hungry" persists all the way to the cap instead of building toward a
stronger word, so the language stops overstating stakes the mechanic never
had. `ACTOR_HUNGER_HUNGRY` is gone along with it —
`test_hunger_never_escalates_past_hungry_even_at_the_cap` pins the
new ceiling directly, and `test_hunger_at_any_level_never_blocks_other_
actions_or_causes_harm` re-confirms the pre-existing "descriptive only,
never mechanical" guarantee still holds through the retune.

**The discoverability problem: nothing said what "ready to cook" actually
required.** The same session spent something like ten turns wandering
yard/hut/forest, re-checking `actions` over and over, unable to tell *why*
`cook`/`eat` weren't listed — because nothing on screen ever named the
missing piece: stand at a lit hearth, holding a raw potato. This is the
same invisible-affordance shape as the charm-string's missing-twine hint
above (`CHARM_MISSING_TWINE_HINT`) — a half-satisfied recipe with no verb
listed and no text explaining what the other half is. `_cook_hint`
(content.py) appends `" -- you could cook that potato here"` to the
hearth's own description, via `hearth_state`, exactly when it's lit and
the actor standing there is carrying a raw potato — checked directly
against `cmd_cook`'s own precondition, not derived from it, so the hint
can never silently drift from what actually works. `cmd_cook`'s own output
also picked up a small, unforced improvement from the same pass: the
broiled potato's description now says "ready to eat" explicitly rather
than leaving it implied by "steaming" — belt-and-braces, not a fix for a
demonstrated failure, since the observed transcript actually handled
cook-then-eat fine on its own.

### The tin pot — a decorative fixture, grounding "boiled" in something real

**BUG WE HIT, spotted from a session transcript: the egg's own cook_line
described boiling in water that didn't exist anywhere in the model.** The
potato's cook_line ("You bury the potato in the embers") is grounded — the
hearth and its fuel are real, tracked state. The egg's original line
("You lower the egg into the hot water") wasn't: there was no vessel, no
water, nothing a hand could `look` at that the sentence was describing. A
real reader noticed and asked outright — *"what did it boil the egg in?!"*

Fixed with `POT_ID`/`ensure_pot`, a plain, permanent, non-portable `Entity`
in the hut (`"a battered tin pot, sitting empty by the hearth"`),
present from world creation the same way the hearth and shelf are.
**Deliberately given no state of its own** — no water level, no filling
verb, nothing to maintain — the calm-axis invariant rules out a second
thing to tend, and this fixture exists purely so the egg's cook_line
("You fill the tin pot and set it over the embers, then lower the egg
in...") has something real to point at. `ensure_pot` backfills it onto
any world/save that predates this pass, called alongside
`ensure_shelf`/`ensure_charm_string` in both `build_world` and
`drivers.load_or_build` — no resync step needed, unlike `ensure_cairn`'s
or `ensure_charm_string`'s own, since a flat description with no dynamic
state can never drift.

Also lays groundwork for tea (README's "Someday" list), which will need
this exact same "boiled in something real" grounding once it's built —
one fixture serving both, rather than reopening the same gap later.

## Curio visual compression — a presentation pass, not a mechanic

Curios are deliberately persistent: nothing decays, nothing auto-clears.
That's the point (the shelf and cairn are both "everything, forever"
records), but it has a cost — a well-visited hut accumulates loose
pinecones and feathers without bound, and the room listing was printing
one bullet per entity regardless. See `docs/CURIO_VISUAL_COMPRESSION.md`
for the original proposal; this is the v1 slice of it, kept to the doc's
own "start with the simplest grouping implementation" instruction.

**The core invariant, and why it shaped everything else.** Compression must
never destroy, merge, or transform a curio, and must never change what an
action resolves to — it only changes what the room LISTING prints. That's
what makes it safe to build as a pure presentation pass with zero changes
to `find_visible`, `cmd_take`, `cmd_give`, `cmd_place`, or any entity's own
data: `_room_lines` (content.py) computes a list of display strings from
the same entities `_room_here` already returns, and every verb keeps
resolving to one real entity exactly as it did before this feature existed.

**Grouping key is (name, description), not name alone.** This is the
spec's other non-negotiable: "compress repetition, not character." Two
curios only ever share a group when their name AND their exact
description match — so a curio holding distinct, persistent state (the
doc's example: a battered pinecone among ordinary ones) always keeps its
own line, however small. Nothing in the game actually diverges a loose
portable curio's description yet (`cat_replay` only touches curios
already given away, which are non-portable and excluded from grouping
entirely — see below), so this is forward-looking: the invariant is real
and tested (`test_compression_never_merges_curios_with_different_
descriptions`, by hand-setting one entity's `.description`) even though
no current mechanic exercises it in normal play.

**Traces group too — the first version got this wrong.** `_room_listing_
line` already had to tell apart a curio still sitting loose (portable=True)
from one that's been given to the cat and become a permanent, self-naming
trace (portable=False) — see that function's own comment. The first build
of `_curio_groups` mirrored that same check and excluded traces from
grouping entirely, reasoning a trace reads as room scenery, not
accumulating clutter. Real output disproved that within the first
playtest: two pinecones given to the cat separately produced two
identical "a pinecone, well-battered after a game with the cat" bullets —
exactly the noise this feature exists to remove, just in a field
(cat-given traces) that accumulates over a lineage the same way loose
finds do. Traces are eligible now, on the same (name, description) key as
everything else. The one place this needed real care rather than just
dropping the portable check: an ordinary find's description is disposable
flavor text (dropping it in "three pinecones" is the whole point), but a
trace's description IS the point — `give`'s own invariant is that the
gesture always leaves its mark, and erasing "well-battered..." to show a
bare "two pinecones" would erase exactly that mark. `_group_count_line`
handles this by checking whether the description is self-naming (starts
with `"{name}, "`, the exact shape `_CAT_GIVE_TRACES` always produces) —
if so, the group keeps that suffix attached ("two pinecones,
well-battered after a game with the cat"); if not (an ordinary find), it
renders the terser count-only line as before.

**BUG WE HIT, a second real one, same review cycle:** `_group_count_line`
stripped the self-naming prefix before splicing a trace's text onto a
count; `_group_look_summary` (the `look <name>` detail view, a separate
function) didn't get the same treatment, so `look pinecone` on a
compressed trace group read "There are two pinecones here. **a
pinecone**, well-battered after a game with the cat" — the name spoken
twice. Both call sites now share one helper, `_drop_self_naming_prefix`,
so there's exactly one place that knows what a trace's description looks
like and exactly one place that strips it.

**Thresholds** (`CURIO_GROUP_EXACT_MAX=4`, `CURIO_GROUP_SEVERAL_AT=5`):
group size 1 renders exactly as `_room_listing_line` always did (zero
behavioral change for the common case); 2 through 4 spells the count out
in words ("three pinecones" reads as prose, "3 pinecones" reads as a stat
line); 5+ reads as "several X". The doc calls this "a presentation
choice, not a world rule," free to retune once real play says otherwise.

**Plurals are hand-authored, not derived.** `_plural_of` (content.py, next
to `FOUND_ITEMS`) looks up a `_CURIO_PLURALS` table rather than guessing —
"a pebble of blue glass" needs the FIRST word inflected ("pebbles of blue
glass"), which no naive "add an s to the last word" rule gets right, and
guessing wrong reads far worse than the noise compression is meant to
fix. Same discipline as `FOUND_ITEMS` itself: a small, fixed table over
cleverness. A naive fallback exists so a future curio added without a
plural entry degrades to something readable instead of crashing, but
`test_every_found_item_has_a_hand_authored_plural` pins that no real
entry is actually relying on it.

**`look <name>` on a group always reveals the exact count.** The
approximate "several" rendering is for the passive, standing room
description; a hand that deliberately asks gets the real number
(`_group_look_summary`) — "the exact underlying count is never lost" is
the doc's own words for this. When the matched curios don't all share one
description, the summary names the largest sub-group "ordinary" and each
other sub-group "different," rather than folding a distinctive one in
silently.

**Deliberately deferred, per the doc's own instructions.** The doc's
"better presentation" example merges same-name groups into one combined
sentence ("two pinecones and a battered pinecone"); this build instead
renders each (name, description) group as its own separate bullet
("two pinecones" / "a battered pinecone" on two lines). Both satisfy the
real invariant — the distinctive one is never silently absorbed into the
count — and the doc explicitly permits starting simple and introducing
"more sophisticated representative descriptions only when actual play
demonstrates that they are needed." Combining them into one flowing
sentence would also require deriving a short adjective from arbitrary
description text ("well-battered after a game with the cat" → "battered")
with no live data to design that against yet. Also not built: the tiered
"little scatter of..." environmental-texture rendering at higher counts,
curio-specific compression opt-outs, and applying any of this to the
shelf or inventory (both explicitly out of scope — the shelf stays
individually legible on purpose, being a curated collection rather than
clutter, and inventory already has its own older "(2)" summarisation via
`_carried_names`, untouched by this feature).

## Lineage Memory — a one-way microscope on the journal

`lineage_memory.py` is a completely separate module, not a feature of the
game itself: it reads the journal, records patterns, and is read by a
developer via `--lineage-report`. Nothing it produces is ever fed back
into a prompt, a description, or any world state — see
`docs/LINEAGE_MEMORY_OBSERVATORY.md`'s own "no arrow back into the game"
diagram, which the module's docstring restates as its own constraint.

**History, briefly, because the design only makes sense in light of it.**
The first version was rule-based: hand-authored entity/concept word
tables, matched incrementally after every session and synced
automatically alongside `w.save(SAVE)`. That version went through two
real, observed bugs before being replaced outright — worth keeping as
institutional memory even though the code is gone: (1) matching
cross-producted every entity and concept mentioned anywhere in a whole
entry, so one real entry about the hearth, the cat, and (in a separate
sentence) "the forest is dangerous after dark" tagged FIVE entities with
"danger," not just the forest — fixed at the time by scoping matches to
one sentence; (2) a keyword table fundamentally can't tell an observation
from an interpretation ("the well was dry" vs. "the well was watching
me") without actually understanding the sentence, which is exactly what
sank the rule-based approach for good once real reports started asking
for that distinction, plus richer categories (`good_omen`, not in any
hand-authored list) and behaviour tracking. Rather than keep bolting
heuristics onto keyword-matching, extraction was replaced wholesale with
an LLM call. The other real decision made at the same time: keep this
**one file, manually rebuilt**, not an automatic sync running a second,
parallel LLM-backed lineage alongside — cost and latency landing on
ordinary play (a plain human `quit` making API calls it never used to)
and the risk of two lineages drifting out of sync with each other were
both reasons to say no to that shape, even though it was the initially
proposed design.

**Extraction (`llm_rebuild`) takes a plain list of journal entry
strings** — not a `World`, not a journal entity — so this module still
imports nothing from `world.py`/`content.py`/`drivers.py`. The CLI layer
(`lineage_rebuild()` in drivers.py) owns loading the world and handing
over `journal.attrs["entries"]`; `anthropic` itself is lazily imported
inside `llm_rebuild` only when no test double is injected, so the rest of
this module — and the whole test suite — needs neither the package nor a
key installed.

**A closed entity list, an open concept vocabulary.** `KNOWN_ENTITIES` is
still a small, fixed, hand-authored tuple (well, cairn, forest, hearth,
lamp, shelf, statue, cat, patch) passed into the prompt as an enum constraint —
docs/LINEAGE_MEMORY_OBSERVATORY.md section 13's own caution against
letting arbitrary nouns become thousands of tracked entities still
applies, and an LLM is exactly the kind of extractor that would happily
invent a new one every batch if allowed to. `concept`, by contrast, is
free text the model chooses (normalized to short, lowercase, snake_case
labels) — the entire reason to bring an LLM in was to stop being limited
to a hand-authored word list, so constraining concepts the same way as
entities would have defeated the point.

**BUG WE HIT, found in real use, right after `patch` was added: bare
entity names aren't enough disambiguation.** A stone left "on the flat
ground at the forest's edge" — the cairn — got tagged to `patch` instead.
The enum constraint only forces a *valid* choice, not the *right* one, and
the entities used to reach the model as bare names with nothing else:
`well, cairn, forest, hearth, ... patch`. `patch` is ordinary English for
any patch of ground, and nothing marked it as specifically the yard's
vegetable patch — a passage about ground elsewhere read as a plausible
match with nothing to rule it out. Fixed with `ENTITY_HINTS`, a short
gloss per entity (`"specifically the vegetable patch in the yard... —
not the forest floor, ground elsewhere, or a metaphorical patch"` for this
one), always sent alongside the name in `_SYSTEM_PROMPT` rather than
trusting the bare word to carry its own meaning. `test_every_known_
entity_has_exactly_one_disambiguating_hint` keeps `ENTITY_HINTS` and
`KNOWN_ENTITIES` in lockstep, so a future entity added to one without the
other fails loudly instead of quietly reaching the model unglossed the
same way `patch` did. No backfill needed for already-mis-tagged data —
`llm_rebuild` is a full rebuild from scratch every time (see below), so
the next `--lineage-rebuild` simply produces the correct tagging.

**BUG WE HIT, immediately after fixing the one above, same real use:
disambiguation over-corrected into suppression.** Once `patch` couldn't
be confused with other ground, most journal entries about planting
potatoes still weren't showing up — because most of them just say
something like "planted a potato," with no mention of "the patch" at
all, and `_SYSTEM_PROMPT`'s original closing line told the model to "not
extract anything about potatoes ... unless it specifically characterizes
one of the known entities." A bare "planted a potato" reads as exactly
the routine chore that instruction exists to filter out, unless something
tells the model that this specific chore *is* patch behaviour by
construction. It is: `cmd_plant`/`_patch_in` in content.py only ever let
a potato go into the one patch entity, so there's no other place in the
game the action could refer to — the verb+object pair identifies the
entity on its own, no location word required. Fixed two ways together:
the patch's own `ENTITY_HINTS` entry now says so explicitly ("even if the
entry just says 'planted a potato' without the word 'patch'"), and the
closing instruction now names potatoes as a partial exception instead of
a blanket one — eating/cooking/carrying stays excluded as routine, but
planting/watering/harvesting is called out as always-extract. Two
correctness directions, same underlying question (what does "patch"
actually refer to), so worth reading as one lesson: pin down what should
be *excluded* AND what should still get *included* explicitly, since
fixing one without checking the other silently pushed the wrong way each
time. `test_patch_hint_covers_bare_planting_entries_without_the_word_
patch` checks both halves stayed in the prompt.

**The same fix, requested again for `statue`, real use once more.** A
journal line came back that never says "statue": *"Plant your potatoes
before you venture, and give Ember something blue when you come back —
the wishing works better that way."* Wishing only ever happens at the
statue (`cmd_wish`, gated by `_statue_reachable`) — no other verb, no
other entity — so the same "action alone identifies the entity" rule
from the patch applies just as cleanly. `ENTITY_HINTS["statue"]` now says
so directly ("Wishing, or a wish, always refers to this statue, even if
the entry never says 'statue' at all"). No `_SYSTEM_PROMPT` exclusion
line needed changing this time — nothing was telling the model to skip
wishing mentions, unlike potatoes' routine-chores carve-out — so this one
was a pure disambiguation addition, not a two-sided fix. The comment
above `ENTITY_HINTS` now names this as a recurring shape rather than two
unrelated incidents: any entity with exactly one action mechanically tied
to it and nothing else in the game is worth this treatment up front,
rather than waiting for a real journal line to expose the gap.

**Third instance, applied proactively this time.** `riverbank` (the
clay-gathering location the riverbank/clay feature added — see
docs/CLAY_SPEC.md) got the same treatment from the moment it was added to
`KNOWN_ENTITIES`, rather than waiting for a real journal line to expose
the same gap a third time: gathering, digging, or working clay only ever
happens at the riverbank (`cmd_gather`'s riverbank branch; `cmd_shape`
has no location check of its own, but its raw material only ever comes
from there), so `ENTITY_HINTS["riverbank"]` says so up front. The one
difference from the patch/statue cases worth noting: `cmd_shape` lets a
hand carry clay away and shape it anywhere, so "shaping clay" isn't
strictly a riverbank-*location* action the way planting or wishing are —
the hint leans on "clay" itself being the identifying word (it's the
game's only source of it) rather than on a single verb tied to one place.

**Four evidence types, exactly the split
`docs/LINEAGE_MEMORY_OBSERVATORY.md`'s "V1.5" addendum asked for**:
`observation` / `interpretation` / `behaviour` / `association`, with the
model itself doing the classification (its prompt spells out the
distinction the rule-based version could never make: interpretation is
"especially anything that treats an inanimate object as if it perceives,
remembers, or intends"). `behaviour` no longer needs the fragile
phrase-matching the rule-based version used (`CANDIDATE_BEHAVIOURS`,
"stacked" / "added a stone" tied to one fixed entity) — the model just
judges whether the entry describes an actual action, the same way it
judges everything else.

**Confidence is real now, not a TODO.** Every evidence item carries a
`confidence` (0–1) the model assigns; `format_report` pulls anything
below `CONFIDENCE_WEAK_BELOW` (0.5) out of its normal evidence-type
section and into its own `WEAK / DERIVED` heading instead, so a
developer reading the report isn't handed a shaky inference with the same
visual weight as a confident one. Never silently dropped, though — "prefer
false negatives over confidently inventing meaning" cuts the other way
too: don't manufacture false *certainty* by hiding a real but weak signal
entirely.

**Batching, not one call per entry.** `BATCH_SIZE` (12) entries go into
one API call; a full rebuild over a real lineage's journal costs a
handful of round trips, not one per entry. A batch that raises (network
error, bad response) is skipped rather than aborting the whole rebuild —
`llm_rebuild` is meant to hand back a partial, inspectable result a
developer can look at and re-run, not lose everything to one bad batch.
`entry_index` values outside the batch's real range (a hallucinated
index) are dropped the same way — silently, rather than corrupting
`memory` or crashing.

**Progress, for a rebuild that takes a while.** A real lineage's journal
already runs to a handful of round trips, and it only grows — a silent
multi-batch rebuild reads as hung rather than working (found in real use:
"it took a while and it looked like it was stuck"). `llm_rebuild` takes an
optional `on_batch(batch_num, total_batches)`, fired right *before* each
batch's API call rather than after, so a slow or genuinely stuck request
still shows up as progress instead of silence. Kept as a plain callback,
not baked-in printing, so this module stays decoupled from stdout the same
way it stays decoupled from `world.py`; `drivers.py`'s `lineage_rebuild`
supplies the actual `print(f"  batch {n}/{total}...", flush=True)`. The
explicit `flush=True` matters here specifically — without it, output can
sit in a buffer for the same reason a stuck call would, defeating the
whole point.

**No incremental state.** The old `processed_through`/resume bookkeeping
is gone along with the automatic sync it existed for: `llm_rebuild`
always processes every entry from scratch (`{"entry_count": N,
"entities": {...}}` is the whole envelope now), and two rebuilds of the
same journal are fully independent — there's nothing left to accidentally
carry over between them.

**Cheap and fast is enough** (`claude-haiku-4-5-20251001`): this is
structured extraction against a tool schema, not creative writing, and
Lineage Memory is a bolt-on developer tool, not the game itself — no
reason to spend a bigger model's budget on it.

**Tested with a fake client, same pattern as the LLM sign-off tests**
(`test_drivers.py`'s `_FakeClient`/`_leave_signoff`): `_FakeExtractionClient`
returns one queued response per expected batch call and records every
`kwargs` dict it was asked to send, so a test can assert not just the
resulting `memory` shape but which entries actually went into which
batch. No network, no key, fully deterministic — the one thing genuinely
*not* covered by the automated suite is the real, non-injected
`Anthropic()` path, the same gap `llm_agent`'s actual network calls
already have.

**CLI**: `--lineage-rebuild` (needs `ANTHROPIC_API_KEY`, same check
`llm_agent` already does) rebuilds `lineage_memory.json` from the whole
journal and prints the report in one step; `--lineage-report` just reads
and formats whatever's already there, unchanged regardless of how it was
built. `lineage_memory.json` itself stays a gitignored sibling of
`emberworld_save.json` — derived, regenerable, specific to one local
lineage's play history, never something a fresh clone should inherit.

**Deliberately not built**: naming and symbolic-act detection get no
special handling beyond whatever the model naturally captures under
`association`; there's no tone-distribution reporting or temporal banding
(days 1–10 vs. 11–20 vs. 21–32) the original doc's later sections
describe; and the report's own prose stays literal (`concept` labels and
raw excerpts) rather than attempting the "little scatter of..."-style
prose-merging the doc explicitly frames as a later refinement, if ever.

## The charm-string — a fourth fate for round, dimensional curios

The cairn (above) gave stones a collective, permanent second door beyond
give-to-cat. Round/dimensional curios that aren't stones — a button, a
glass pebble — never got one: `FOUND_ITEMS` hardcodes both as `"ignores"`,
so before this they had *no* positive fate at all, only a cat's shrug and a
lifetime on the floor. The charm-string is that door: a wall-mounted,
collective object in the hut (`CHARM_STRING_ID`) that any hand can thread a
button or pebble onto, permanently, using up one carried twine to do it —
`thread <item> on charm-string` (`cmd_thread`).

Structurally it's the cairn's twin: `world.entities.pop` consumes the
threaded item *and* the twine outright (not a location change — there is
nothing left to `take` back, by construction, the same one-way permanence
as the cairn), and increments a plain `count` attr on the `charm_string`
entity rather than tracking the items themselves. `CHARM_ELIGIBLE_ITEMS`
(`"a bone button"`, `"a pebble of blue glass"`, `"a pinecone"`) is
deliberately narrow — things with an inherent hole or a gap a knot can
catch in, not every round curio. A pinecone qualifies on that same
physical logic: its own `FOUND_ITEMS` look_line ("one scale broken") is
exactly that kind of gap, not just "round like a button." A feather still
doesn't qualify; it already has its own fate, the journal-tuck. Extend
further only once the forest generates more qualifying finds.

Where it differs from the cairn on purpose: the cairn only ever gets
taller, same texture every stone. The charm-string is meant to read as
*decorative variety*, not monument height, so `CHARM_BANDS` ties its
description to a **count**, not a height, in four tiers (empty / a single
thing / a small scatter / crowded) — deliberately not item-specific
(naming which items are visible is a stretch goal, not this pass, the same
"don't track every possible mix" discipline the forest's depth bands and
the cairn's height bands already follow). `CHARM_CAPACITY` (100) exists so
nothing grows *truly* infinite, but reads as effectively unbounded in
normal play — a curio is already a rare find, and threading one spends a
second rare find (twine) right alongside it, so no ordinary lineage will
ever feel the ceiling.

Present-but-empty from world creation (`ensure_charm_string`, called
alongside `ensure_shelf`/`ensure_cairn`/`ensure_riverbank` in both
`build_world` and `load_or_build`) rather than lazily created like the
statue — a bare length of twine on the wall is visible before anyone's
threaded anything, the same way the cairn's flat stone is visible before
any stone's been stacked. `ensure_charm_string` re-syncs a stale
description to the current `CHARM_BANDS` on every load, the identical fix
`ensure_cairn` already needed (see its own note above) for the same
underlying reason: a description computed once and stored doesn't
retroactively follow a later change to the bands.

**Same legibility fix as `STONE_CAIRN_HINT`, for the same reason.**
`_found_description` appends `CHARM_STRING_HINT` ("it could be threaded
onto the charm-string in the hut") whenever the curio's name is in
`CHARM_ELIGIBLE_ITEMS` — the cue rides on the item itself, not just the
room it's usable in, so a hand doesn't lose it the moment a button leaves
the hut. `ensure_shelf` backfills the hint onto an already-found button or
pebble from an older save, right alongside its existing `STONE_CAIRN_HINT`
backfill.

**BUG WE HIT: both backfills ran against any matching curio, whether or
not it was still reachable.** A stone or button already given to the cat
is non-portable and its description already rewritten to a cat-trace by
`cmd_give` — but the backfill loop still appended its hint on top, reading
as *"given to the cat and roundly ignored — it could be threaded onto the
charm-string in the hut"*, which is false: that curio is stuck in the room
forever, it can never reach the charm-string or the cairn again. Fixed by
guarding both backfills on `entity.portable` — the one flag `cmd_give`
flips to `False` and never flips back, so it's the correct discriminator
between a live, reachable curio and a permanent trace. Deliberately *not*
fixed by making cat-given items portable again, which would reopen a
rescue path from cat-given items into the charm-string or cairn — ruled
out on purpose (see the charm-string's own scope notes above): give-to-cat
stays a one-shot, irreversible gesture, the same permanence as the cairn
and the journal-tuck.

`available_actions` (`carrying_actions`) only offers `"thread <item> on
charm-string"` when all three are true: the hand is in the hut, is
carrying at least one eligible item, and is carrying twine — the same
"only offer what can do something" rule the shelf and cairn already
follow, with twine specifically required since threading genuinely can't
do anything without it (unlike `add wood`'s deliberate exception).

**BUG WE HIT: that same "only offer what can do something" rule made the
twine requirement itself invisible.** A hand carrying an eligible curio
but no twine sees no `thread` action at all — indistinguishable from "the
charm-string has nothing to do with me right now," when actually it's one
specific, nameable ingredient short. A real session (Tallow, day 55) hit
this directly: looked at the charm-string twice with a bone button in
hand, found nothing pointing at twine, never tried `thread` blind to
discover `cmd_thread`'s own clear refusal ("You need a knot of twine in
hand..."), and on running out of better ideas gave the button to the cat
instead, guessing (wrongly) that it might help. Fixed by
`_charm_string_missing_twine_hint`, checked from `cmd_look`'s
charm-string branch: when the hand carries an eligible item, is under
capacity, and has no twine, `look charm-string` appends
`CHARM_MISSING_TWINE_HINT` to the count-based description, reusing
`cmd_thread`'s own wording so the sentence is authored in one place. The
hint only fires on that half-satisfied state — carrying nothing eligible,
already carrying twine too, or the string being full all suppress it, so
it never turns into noise on top of an affordance that's either not
relevant yet or already fully offered.

**Twine is exempt from `give ... to cat`, protecting the other half of the
recipe.** The Tallow-day-55 fix above covers a hand holding an eligible
curio with no twine. A later session (Marrow, day 59) hit the state that
fix can't reach: by day 59, *every* eligible curio and *both* knots of
twine already in the world had been given to the cat by earlier hands,
leaving nothing to thread and nothing pointing anywhere — `look
charm-string` just returned the bare ASCII rendering, turn after turn.
Twine was never special-cased before; it rolled off the same `FOUND_ITEMS`
table as every other curio and was just as giveable. Rather than try to
hint a hand out of a state with literally nothing to work with (no other
system in the game proactively points back at the forest to restock), the
fix removes the cause: `cmd_give` now refuses twine outright
(`GIVE_TWINE_REFUSAL`, checked by name right alongside the existing
non-curio redirect to `feed cat`), so a knot can only ever be spent on
`thread`, never given away. Twine isn't decorative the way a button or
pebble is — it's the means, not the find — so keeping it out of the give
economy is a difference in kind, not an arbitrary restriction. Both ends
guarded the same way the map-discoverability bug (below) was: `cat_actions`
(`cat.py`) excludes twine from the `give <item> to cat` actions it offers,
so the refusal in `cmd_give` is a backstop, never something a hand can
actually trigger through a listed action.

`look charm` (not just `look charm-string`) already resolves correctly
with no extra code — `find_visible`'s existing substring match (`name in
e.name.lower()`) matches `"charm"` against the entity's own name,
`"charm-string"`, the same way `look pinecone` already matches `"a
pinecone"`.

**BUG WE HIT, the one that actually explained the wood-hoarding session:
`add <anything>` silently misfired as a wood check.** `world.act` only
ever splits a command on its first word (`verb, _, arg =
command.partition(" ")`), so `"add"` is a single dispatch key regardless
of what follows it — `cmd_add_wood` used to ignore `arg` entirely, no
matter what it was. A hand (Wick, day 60) tried `add moss`, `add
feather`, `add pinecone` — reasonable guesses at decorating the
charm-string, since it never had twine and never saw `thread` offered —
and got "You've no wood. It comes from the forest's edge." every time.
That's not a missing affordance, which reads as silence; it's a specific,
confident-sounding response that happens to be about the wrong thing
entirely, and it reads exactly like a real rule. Wick wrote it up as one
("the charm-string only wants wood from beyond the yard"), and the *next*
hand (Wrenlow, day 60) spent a chunk of a 50-turn visit gathering wood
into the double digits chasing a mechanic that never existed. `cmd_place`
already had the right shape for this — it only redirects to
`cmd_add_wood` when the arg matches `_PUT_WOOD_IN_HEARTH`'s hand-authored
set, falling through to its own (correct) "you aren't carrying that"
otherwise — `cmd_add_wood` just never got the same treatment for its own
verb. Fixed the same way: `_ADD_WOOD_ARGS` is the hand-authored set of
phrasings that actually mean "add wood" (`""`, `"wood"`, `"the wood"`,
`"fire"`, `"the fire"`, `"hearth"`, `"the hearth"`, plus their close
variants) or "stoke" bare; anything else gets `_add_not_wood_refusal(arg)`,
which names what was actually typed and points at `thread` if a curio's
what's meant, instead of asserting a false wood requirement. Both
`cmd_place`'s wood-alias (`cmd_add_wood(world, actor, "")`) and cat.py's
`feed hearth` alias pass `""`, which is in the accepted set, so neither
alias path was affected.

**Phase 2, built as its own fast-follow: a dedicated `look charm`/`look
charm-string` ASCII rendering**, distinct from the room's own standing
description above (which stays count-based prose only, unchanged).
`_charm_string_ascii` renders one glyph per threaded item, in strict
insertion order, wrapped `CHARM_ASCII_ROW_WIDTH` (5) per row and
separated/framed by `CHARM_ASCII_SEP` (`"~~~"`) — two buttons and a
pebble: `"~~~o~~~o~~~•~~~"`. `CHARM_ITEM_GLYPHS` maps each eligible item
to its glyph (`o` button, `•` pebble, `*` pinecone — the pinecone's own
glyph is new here, since it joined `CHARM_ELIGIBLE_ITEMS` after the
original spec was written, button/pebble only). At zero items there's
nothing to render, so it falls back to the exact same empty-prose-tier
line the room's own description already uses — no empty ASCII block, the
same "don't render a block for nothing" rule the shelf and cairn already
follow at their own empty states.

**BUG WE HIT, caught before it shipped: rendering by insertion order needs
an actual insertion order, and Phase 1 never tracked one.** `cmd_thread`
only ever incremented a plain `count` — nothing recorded *which* items had
been threaded or in what sequence, since the count-based prose tier never
needed to know. Phase 2 added `charm.attrs["items"]`, appended to
(`e.name`) alongside `count` in `cmd_thread`, but that leaves every
charm-string that predates this pass — including this project's own live
`emberworld_save.json`, discovered mid-implementation — with a real count
and zero item history. `ensure_charm_string` backfills the gap: pad the
**front** of `items` with `None` (rendered as `CHARM_UNKNOWN_GLYPH`,
`"?"`) up to `count`, never the back, since anything newly threaded always
lands at the *end* — so any untracked entries must be the oldest ones, by
construction. Idempotent: once padded, `len(items) == count`, so a later
load pads nothing further. Chosen over the alternatives — guessing a type
(silently wrong), or leaving the count and glyph total mismatched (looks
like a bug rather than a known gap) — because `?` says plainly "this one
predates tracking," which is the actual, honest situation.

**This project's own live save's one `?` turned out to be recoverable, so
it isn't one anymore.** `emberworld_save.json` is gitignored (never part
of a commit), but checking it directly turned up exactly one gap: count 1,
no item history. Rather than leave it as a guess, the real answer was
findable — `grep -n "Command:\*\* \`thread" sessions/*.md` turns up
exactly one `thread` command ever issued, across every session transcript
this lineage has: *"thread a pinecone on charm-string"*
(`sessions/20260814-225640_thistle_day-52_40-turns.md`, turn 17, result
"You knot the pinecone onto the charm-string"), corroborated by the
journal's own Day 53 entry ("threaded a pinecone on the charm-string").
Patched by hand (`charm.attrs["items"] = ["a pinecone"]`, then
`world.save()`) as a one-time, evidence-backed repair of this specific
save — not a change to `ensure_charm_string` itself, which still must
fall back to `CHARM_UNKNOWN_GLYPH` for any *other* legacy save, since most
won't have a session-log trail this complete to recover from.

## The outer-world map — `map.py`, a hand-drawn ASCII layout

`map` (`cmd_map`, a free verb) prints an ASCII diagram of the outer world —
hut, yard, forest's edge, riverbank. Prompted by a real LLM session
(`sessions/20260814-234841_tallow_day-55_10-turns.md`) that never lost its
way exactly, but had no single-glance sense of the world's shape beyond
what `look`'s own "Exits:" line names one room at a time.

**BUG WE HIT: registering `map` in `VERBS`/`FREE_VERBS` made the command
work, but never made it discoverable.** `available_actions` isn't driven by
those registries -- it's assembled from `ACTION_SOURCES`, a list of
`fn(world, actor) -> [actions]` functions, each offering only what's
genuinely usable right now (`docs/ARCHITECTURE.md`'s own "THE ONE RULE"
above `core_actions`). `map` needs no state and works everywhere, so
without adding it to `core_actions`'s always-there list (`["look",
"actions", "wait", "map"]`) it simply never appeared in `actions`, the same
invisible-affordance shape this same session's charm-string/twine hint
already fixed once above -- a real player caught it by noticing `actions`
never once listed `map`. Pinned by
`test_map_is_always_listed_in_available_actions`.

Split into its own file, `map.py`, the same way `forest_text.py` split out
of `content.py`: `render_map()` takes nothing and returns the whole map as
one static string — it knows nothing about a `World` or an `Entity`.
`content.py` stays the one place with entities and design notes; `map.py`
is presentation only.

**Deliberately hand-drawn, not laid out from the room graph
algorithmically.** The outer world is one simple hub shape — yard, with the
other three as spokes off it — and a real graph-layout algorithm would be
solving a harder problem than the one that exists. Growth risk (the stated
worry when this was proposed) is handled the same way `REFERENCE.md`
guards against verb/behavior docstrings going stale: not by generating the
picture from the graph, but by a completeness test
(`test_map_completeness_against_the_live_room_graph` in `test_map.py`) that
asserts every entity the world actually has with a non-empty `exits` dict
(the same trait `look`'s "Exits:" line relies on) has a label in
`ROOM_LABELS`. Add a room without updating `map.py` and this test fails
loudly, rather than the map silently going stale in the reader's hand.

**Deliberately no "you are here" marker.** An early version of `render_map`
took the actor's current room and marked its box `(you)`. Dropped once it
was pointed out that this reads as a hand-drawn map the hero is carrying,
and a drawn map doesn't know where you're standing — that's a live-GPS
convention, not a parchment one. It also wasn't solving a real gap: `look`
already states the current room, every single turn, in its own header.
Removing the marker turned `render_map` into a fully static function (no
actor parameter at all) — pinned by `test_render_map_has_no_position_marker`
and `test_render_map_is_deterministic`.

**The forest gets a shape, not a room.** The first cut of this feature drew
only the four rooms with real exits, on the theory that anything more would
violate `docs/FOREST_SPEC.md`'s "No forest map, ever." Revisited once it
was pointed out that the objection was about *precision*, not *presence* —
a crisp `+---+` box claims the same surveyed exactness as the four real
rooms, but a shape that's visibly rough and larger than anything else on
the page claims the opposite. `_forest_shape` draws a dotted-border,
oversized rectangle labeled only "the forest," linked to Forest's Edge by a
`:` instead of the real rooms' solid `|` — connected, but the connection
itself reads uncertain. It carries no new information (the room's own
description already says the forest is there); it just renders that same
already-known fact into the picture instead of leaving it as a gap. It is
never a room: no exit, no entry in `ROOM_LABELS`, invisible to the
completeness test, and it never will gain any of those, on purpose — see
`docs/FOREST_SPEC.md`'s own "No forest map, ever" and this module's
docstring.

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

1. **Write the failing test first.** In whichever `test_*.py` already owns
   the subject (`test_curios.py`, `test_forest_edge.py`,
   `test_forest_venture.py`, `test_journal_and_seed.py`, `test_riverbank.py`,
   `test_hut_basics.py` -- or `test_world.py` if it's really an engine
   change), script the new behaviour through
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
   `--fuzz` stays clean. Regenerate the reference (`--reference > docs/REFERENCE.md`).
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
  `cmd_read` (`JOURNAL_READ_LIMIT` 5 + `JOURNAL_OLDER_SHOWN` 6), because a
  prompt pays per token every turn and a hand reading a book doesn't. *Which*
  entries get shown is one shared policy, `content.journal_view` — see the
  long note on it. Short version: never a plain tail. A tail means a run of
  similar entries becomes the whole of what the next hand inherits, and we
  watched that happen — a stretch of visits that all hit the same trouble
  filled the window with the same warning, so each arriving hand read nothing
  else and wrote another one. The journal is the strongest lever in the world
  on how a visit *feels*; a pure-recency window hands that lever to whatever
  the last few hands happened to be going through.

  **Rebalanced further, real-play ask.** `cmd_read`'s split used to be 7
  recent + 3 older (favoring recency); it's now 5 + 6 (favoring history), and
  the `older` picks themselves changed shape too. The original picker chose
  the *middle* of `older` evenly-spaced spans across the journal's non-recent
  history — deterministic, but its sample points slid smoothly as the journal
  grew, so a specific one-off entry (a hand's only mention of finding the
  statue, say) was only ever shown while a span happened to be sweeping past
  it, then permanently lost once the span moved on. `_journal_view_indices`
  now seeds a fresh `random.Random(n)` off the journal's length instead —
  never `world.rng`, whose shared, advancing stream would make a second read
  in the same visit show something different, breaking the same "won't
  change once read" promise this section leans on. Seeding by length keeps
  a GIVEN length's picks fully reproducible while making each new length an
  independent draw, so a given entry gets a fresh, real chance of appearing
  every time the journal grows further, rather than one narrow window it can
  age out of for good. `drivers.py`'s own `keep=5, older=2` inherits the same
  algorithm through the shared `journal_view` call, unchanged in count but
  picking differently now too.
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
  forever chasing a "better" one. **Gotcha we hit, round seven**: round
  four's bet — that the suffix/prefix instruction alone made it safe to
  leave "Thistle" sitting in `_STRANGE_NAME_EXAMPLES` — didn't hold up in
  real play. Three consecutive real sessions came back "Thistle" outright,
  the exact verbatim-copy failure round one first diagnosed, on a word the
  instruction explicitly says not to reuse. That stretch also coincided
  with the model's per-turn reasoning summaries thinning out again (see
  `_ask_claude`'s own gotcha on that) — suggestive of effort level being the
  real variable, same as round one's original theory, though not proven by
  three data points alone. Rather than pull Thistle from the pool again
  (round three's fix, reverted in round four on the reasoning that the
  pool provides real variety and the denylist alone was already enough for
  Marrow, which was never even a pool entry), it went on `_OVERUSED_NAMES`
  instead — Thistle stays in the pool for variety, and the same reroll
  safety net now covers it too.
- **Attribution lives in the stamp, not a sign-off** (`day_stamp`, in
  content_common.py, imported into content.py as `_day_stamp`): both
  `cmd_write` and `_leave_signoff` build their journal
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