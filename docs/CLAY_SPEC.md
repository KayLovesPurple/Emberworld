# Clay — Design Spec (Cosmetic-only, Stage 1)

*Design spec, not yet built. Follows the test-first workflow in
ARCHITECTURE.md: observe → diagnose → write tight spec with tests →
implement.*

## Status

Not built. This spec covers the **cosmetic** tier only — see README's
"Someday" list, which explicitly recommends starting there: "shape + name
→ a described, persistent object with no mechanics... Cheap, charming,
low-risk." Functional clay (a pot that truly stores, a dish that changes
cat behavior) is a separate, later design pass — see "Explicitly NOT in
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
- Room description: written at implementation time, in the hut/yard/
  forest_edge voice (see `build_world`'s existing room prose for register).

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
- **`watch clouds`** (`cmd_watch_clouds`) potentially gains `"riverbank"`
  as a third eligible location — **open question, decide at
  implementation time**: does the riverbank read as open sky (reuse
  `WATCH_CLOUD_LINES`/moon logic outright, zero new lines needed) or is it
  tree-shaded (exclude it from the location tuple, same "no open sky"
  refusal as the hut)? Pin whichever is chosen with a test either way.
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
- **Open question**: fixed yield per gather (like `WOOD_PER_GATHER = 3`)
  or exactly one lump per gather? Recommend **one lump per gather** —
  shaping is a deliberate, occasional act rather than a nightly
  consumable, so a multi-lump yield would just clutter inventory the way
  it wouldn't for wood. Flagged for confirmation, not decided here.

## Shaping clay

- New verb `shape` → `cmd_shape`. Primary syntax: `shape clay into
  <name>`. **Open question**: also accept `shape <name>` / `shape clay
  <name>` as looser phrasings? Precedent: `cmd_name` already accepts both
  `name cat Shadow` and `name Shadow` — worth the same tolerance here.
- Requires a carried raw clay lump (`attrs.get("raw_clay")`); refuses
  in-world with no state change if none is carried — same plain register
  as `cmd_add_wood`'s wood refusal or `cmd_tuck`'s `TUCK_REFUSAL`.
- Sanitizes `<name>` exactly like `cmd_name`: strip whitespace, drop a
  leading quote character, keep only the first line (`.split("\n")[0]`,
  blocking multi-line injection into world prose), and cap the length.
  Recommend **40 characters** (vs. the cat's 24) — this names a short
  object phrase, not a proper name, and wants a little more room.
- Consumes the raw clay lump (`world.entities.pop`), creates one new
  entity:
  - **Open question**: is the sanitized text the *whole* name (typed
    curio-style, with its own article — "a squat clay dish"), or does the
    game auto-prefix ("a clay " + sanitized text)? Recommend
    **auto-prefixing** — it guarantees every shaped object reads as
    clay-made without relying on the hand to remember to say so, and
    keeps the input a plain noun phrase rather than a full sentence.
  - `location = actor.location` — dropped in the room where it was
    shaped, not carried automatically.
  - **Open question**: `portable`? Recommend **not portable** (mirrors
    the cairn's stones and a bloom-before-it-opens: made and left, part
    of the room from then on) — but flag this for discussion, since a
    hand may reasonably want to carry a small shaped thing around.
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

## Tests to write first

- `gather` at the riverbank creates exactly one carried raw-clay-lump
  entity, and does not touch `actor.attrs["wood"]`.
- `gather` at `forest_edge` is unaffected (still wood-only; no clay-check
  regression).
- `gather` at an unrelated location (hut, yard) refuses in-world, same as
  today.
- `shape` with no clay carried refuses gracefully, with no state change.
- `shape` consumes exactly one raw clay lump and creates exactly one new
  entity, named per the sanitized input.
- Sanitization: multi-line input keeps only the first line; leading/
  trailing whitespace and a leading quote are stripped; input longer than
  the cap is truncated.
- The shaped object is not `curio=True`, and does not appear in the
  shelf/give-to-cat/cairn/tuck's `available_actions` lists.
- The shaped object survives a save/load round-trip (ordinary entity
  persistence — no new save-format bit needed).
- `listen` at the riverbank returns riverbank-flavored lines, not
  `LISTEN_LINES`; `calm_visits` acks fire per-spot, independently of the
  forest edge's own count.
- `watch clouds` at the riverbank behaves per whichever "open sky"
  decision is made — pin the choice with a test either way.
- Fuzzer (`--fuzz`) terminates cleanly with the new verbs/location
  registered.

## Exit criteria

A hand can walk to the riverbank, spend a calm turn there independent of
the forest's edge, gather a lump of clay, and shape it into something of
their own choosing that becomes a permanent, named fixture of the room —
without touching the shelf, the cat, the cairn, or the journal, and
without adding a fifth fate to a curio system that has already asked for
a presentation-layer fix once.

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
