# Clay — Design Spec (Cosmetic-only, Stage 1)

*Design spec. Follows the test-first workflow in ARCHITECTURE.md: observe
→ diagnose → write tight spec with tests → implement.*

## Status

**✅ Built — cosmetic tier.** The riverbank, `gather`/`shape clay into
<name>`, and both calm verbs are live; see ARCHITECTURE.md's "The
riverbank and clay" for the mechanism and this doc's now-resolved open
questions below for the decisions actually shipped. Functional clay (a
pot that truly stores, a dish that changes cat behavior) is a separate,
later design pass, deliberately not started — see "Explicitly NOT in
scope" below.

## Design goals (recap, so this doc stands alone)

1. Clay is the first *open* material: a hand shapes it into whatever they
   intend, rather than pulling a fixed object off a table the way a found
   curio does. That's a real difference in kind, not just a new resource
   loop — see "Why not a curio" below.
2. A shaped clay object does **not** join the shelf/give-to-cat/cairn/
   tuck-in-journal system. That quartet is already carrying real weight —
   `docs/CURIO_VISUAL_COMPRESSION.md` exists specifically because loose
   curios were already cluttering room descriptions before clay entered
   the conversation. Adding a fifth fate to a system that already needed
   a presentation-layer fix is the wrong move; a shaped object gets its
   own, much simpler home instead (see below).
3. The riverbank is a new location, structurally parallel to the forest's
   edge (its own branch off the yard), not nested inside or gated behind
   forest depth.
4. Gathering wood (forest's edge) and gathering clay (riverbank) are
   strictly separate per-location rolls. No shared find-chance, no
   interaction, no double-counting.
5. Nothing here becomes a forced maintenance loop (calm-axis invariant).
   Shaping is a freely chosen act with no decay, no upkeep, and no undo.

## New location: the riverbank

- New room `"riverbank"`, added as a second branch off the yard, parallel
  to `"forest"`: `yard.exits = {"in": "hut", "forest": "forest_edge",
  "river": "riverbank"}`, with its own `exits={"yard": "yard"}` back.
- Room description (as built): "The path from the yard ends at a bend in
  a slow, brown river, its bank thick with reeds. Grey clay shows through
  where the current has cut the bank away. Open sky stretches overhead,
  unbroken by trees." — the last sentence is load-bearing: it's what
  resolves the "does watch clouds work here" open question below.
- Backfilled onto older saves by `ensure_riverbank(world)`, same role as
  `ensure_shelf`/`ensure_cairn` — called from both `build_world()` and
  `drivers.load_or_build`. `yard.exits.setdefault("river", ...)` so it
  never clobbers an already-present or hand-edited exit.

### Calm-axis affordances at the riverbank

Both reuse **existing verbs** — no new verb syntax needed. The parser only
ever dispatches on the first word (`cat.py`'s own comment on this: "the
parser only looks at the first word"), and both `cmd_listen` and
`cmd_watch_clouds` already ignore their `arg` entirely — `watch clouds`
and bare `watch` already behave identically today. So `listen to the
water` and `watch the water` parse into the existing `listen`/`watch`
verbs with a discarded argument, exactly like now.

- **`listen`** gains a second location branch: a new `RIVER_LISTEN_LINES`
  pool, chosen instead of `LISTEN_LINES` when `actor.location ==
  "riverbank"`, mirroring the varied-line-pool approach `LISTEN_LINES`
  already uses (see `test_listen_returns_varied_lines_not_always_the_same_
  one`'s equivalent for the new pool).
- **`watch clouds`** (`cmd_watch_clouds`) gains `"riverbank"` as a third
  eligible location. **Resolved:** the riverbank reads as open sky ("Open
  sky stretches overhead, unbroken by trees" is in its own room
  description) — so it reuses `WATCH_CLOUD_LINES`/moon logic outright,
  zero new lines needed. Pinned by
  `test_watch_clouds_works_at_the_riverbank`.
- Both share the existing `world.calm_visits` keying (per-spot, not
  per-verb — see `_calm_visit_ack`). `"riverbank"` becomes a new key
  alongside `"forest_edge"`; the ack fires independently there
  (`CALM_ACK_AT = 3` per spot, same as now).
- **THE CONSTRAINT THAT MUST NEVER BREAK** (inherited unchanged from
  `listen`/`watch`'s existing invariant): grants nothing, ever. No
  find-chance bump, no state change, no accumulation of any kind.

## Gathering clay

- Reuse the existing `gather` verb (`cmd_gather`), which already branches
  on location for wood at `forest_edge`. Add a second branch: `gather` at
  `"riverbank"` produces clay; the `forest_edge` branch is untouched.
- Unlike wood — an abstract counter (`actor.attrs["wood"]`) — clay is a
  **discrete carried entity**, because `shape clay into X` needs something
  specific to consume, the same shape as a raw potato existing before
  `cook`. Working name: `"a lump of raw clay"`, `portable=True`,
  `attrs={"raw_clay": True}` (or equivalent marker `cmd_shape` checks for).
- No cap on carried raw clay (mirrors wood's no-cap, unlike the shelf's
  `SHELF_CAPACITY`) — the friction point belongs in the shaping choice,
  not in stockpiling raw material.
- **Resolved: one lump per gather**, not a `WOOD_PER_GATHER`-style fixed
  multi-unit yield — shaping is a deliberate, occasional act rather than
  a nightly consumable, so a bigger yield would just clutter inventory
  the way it wouldn't for wood. Confirmed with the user before build.

## Shaping clay

- New verb `shape` → `cmd_shape`. **Resolved: strict syntax, only `shape
  clay into <name>`** — a plain prefix check on `arg`, no looser
  `shape <name>` / `shape clay <name>` tolerance (unlike `cmd_name`'s
  dual acceptance). One clear phrasing to document and test; simplest to
  implement. Anything else returns "Shape what into what? e.g.  shape
  clay into a squat dish".
- Requires a carried raw clay lump (`attrs.get("raw_clay")`); refuses
  in-world with no state change if none is carried — same plain register
  as `cmd_add_wood`'s wood refusal or `cmd_tuck`'s `TUCK_REFUSAL`.
- Sanitizes `<name>` almost exactly like `cmd_name`: strip whitespace,
  drop a leading quote character, keep only the first line
  (`.split("\n")[0]`, blocking multi-line injection into world prose),
  and cap the length at `CLAY_NAME_CAP = 40` (vs. the cat's 24 — this
  names a short object phrase, not a proper name, and wants a little
  more room). One extra step `cmd_name` doesn't need: a leading article
  (`"a "`/`"an "`) is stripped *before* the cap, discovered as a real bug
  during manual testing — a hand naturally types `shape clay into a
  squat dish`, and without the strip the auto-prefix below doubled it
  into "a clay a squat dish". Pinned by
  `test_shaping_strips_a_leading_article_so_it_never_doubles`.
- Consumes the raw clay lump (`world.entities.pop`), creates one new
  entity:
  - **Resolved: auto-prefix `"a clay "` + the sanitized name** (not the
    hand typing the whole name, article included) — guarantees every
    shaped object reads as clay-made, and keeps the input a plain noun
    phrase. `shape clay into a squat dish` → "a clay squat dish".
  - `location = actor.location` — dropped in the room where it was
    shaped, not carried automatically.
  - **Resolved: not portable**, for now — mirrors the cairn's stones and
    a bloom-before-it-opens: made and left, part of the room from then
    on. The user flagged this as a likely future extension ("start out
    not portable but we will likely want to extend it later") rather
    than a permanent decision — worth checking back in on once a
    lineage has lived with the not-portable version for a while, same
    "learn before extending" posture as functional clay generally.
  - **Not** tagged `curio=True` — deliberately excluded from the shelf/
    give-to-cat/cairn/tuck ecosystem; see "Why not a curio" below.
  - Permanent: no verb to un-shape, rename, or destroy it, matching the
    cairn's and tuck's one-way register — making something is a freely
    chosen, permanent act, not a chore with an undo.
- Costs a turn, like every other curio-disposal-family action.

## Why not a curio

The shelf/cairn/give-to-cat/tuck-in-journal quartet is already carrying
real weight — `docs/CURIO_VISUAL_COMPRESSION.md` exists specifically
because loose curios were cluttering room descriptions before clay was
ever on the table. A shaped clay object is categorically different from a
found one anyway: it's authored by the hand's own chosen name, not drawn
from a fixed pool, so it doesn't need a generic disposal system at all —
it just *is* the thing it was shaped into, sitting wherever it was made,
the plainest possible "richer, not reset" move (README's reset-or-richer
invariant). It is explicitly **not**: added to `_room_listing_line`'s
curio-prefixing special case, offered by `place`/`give`/`stack`/`tuck`, or
tagged `curio=True`.

## Tests written (test_content.py, "THE RIVERBANK AND CLAY" section)

All of the below are in place and passing, plus the article-doubling
regression caught during manual testing:

- `gather` at the riverbank creates exactly one carried raw-clay-lump
  entity, and does not touch `actor.attrs["wood"]`.
- `gather` at `forest_edge` is unaffected (still wood-only; no clay-check
  regression).
- `gather` at an unrelated location (hut, yard) refuses in-world, same as
  today.
- `shape` with no clay carried, or with the wrong syntax, refuses
  gracefully, with no state change.
- `shape` consumes exactly one raw clay lump and creates exactly one new
  entity, named per the sanitized input.
- A leading article in the typed name is stripped so it never doubles
  with the auto-prefix.
- Sanitization: multi-line input keeps only the first line; input longer
  than the cap is truncated.
- The shaped object is not `curio=True`, and does not appear in the
  shelf/give-to-cat/cairn/tuck's `available_actions` lists.
- The shaped object survives a save/load round-trip (ordinary entity
  persistence — no new save-format bit needed).
- `listen` at the riverbank returns riverbank-flavored lines, not
  `LISTEN_LINES`; `calm_visits` acks fire per-spot, independently of the
  forest edge's own count.
- `watch clouds` works at the riverbank.
- `ensure_riverbank` backfills a room/exit missing from an older save,
  and is idempotent (never clobbers an already-present exit).
- Gathering/shaping never touch another resource's own state (hearth
  fuel, bucket water) — same invariant and technique (direct handler
  calls, not `world.act`, so an unrelated tick can't muddy the result) as
  `test_giving_or_placing_a_curio_touches_no_maintenance_resource`.
- Fuzzer (`--fuzz`) terminates cleanly with the new verbs/location
  registered.

## Exit criteria

**Met.** A hand can walk to the riverbank, spend a calm turn there
independent of the forest's edge, gather a lump of clay, and shape it
into something of their own choosing that becomes a permanent, named
fixture of the room — without touching the shelf, the cat, the cairn, or
the journal, and without adding a fifth fate to a curio system that has
already asked for a presentation-layer fix once.

## Explicitly NOT in scope for this pass

- **Functional clay** — a pot that actually stores, a dish that changes
  cat behavior, anything with real mechanics. Cosmetic only, per README's
  "start here" ordering; revisit once a lineage has lived with the
  cosmetic version for a while.
- **Tea, or any clay object built specifically to pair with tea** (the
  "thrown teapot" example from README) — tea itself isn't built yet.
- **A second riverbank resource** (fish, reeds, water for the bucket,
  etc.) — scope is clay plus the two calm verbs only.
- **Any interaction between raw clay or shaped objects and the shelf/
  cairn/give-to-cat/tuck systems** — deliberately excluded; see "Why not
  a curio."
- **Firing/kiln mechanics** — README lists firing (hearth/kiln) as a clay
  dependency, but a cosmetic-only pass has no functional distinction
  between fired and unfired clay to model, so this is deferred along with
  functional making generally.
