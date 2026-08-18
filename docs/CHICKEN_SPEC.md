# The Chicken — Design Spec

*Design spec. Follows the test-first workflow in ARCHITECTURE.md: observe
→ diagnose → write tight spec with tests → implement.*

## Status

**✅ Built.** `chicken.py` (cat.py's sibling subsystem), `cmd_cook`
generalized into a `COOKABLES` table, and `cmd_name` generalized and
moved into content.py — see ARCHITECTURE.md's "The chicken" for the
mechanism, and README's "A chicken — but a producer, never a second
mouth" for the original framing this spec resolved.

## Design goals (recap, so this doc stands alone)

1. **The chicken is the opposite of the cat.** The cat is pure cost — it
   consumes potatoes and returns a purr. The chicken is a gentle *source*:
   ambient yard-life that, now and then, leaves an egg. No hunger, no
   feeding chore, nothing that competes with the cat for the hand's
   scarce turns.
2. **THE CONSTRAINT THAT MUST NEVER BREAK** (same register as the cat's
   own GENTLE GUARANTEE, the statue's mechanical inertness, and `listen`'s
   "grants nothing"): the chicken can never be hungry, never needs
   feeding, never has any need at all. If it is ever given a need,
   something has gone wrong — see "A trap explicitly not being built"
   below.
3. Eggs behave exactly like potatoes: sit harmlessly if ignored, no cap,
   no decay, pile up freely; cooked at a lit hearth, eaten for food.
4. The chicken is a fixed resident of the yard from world-start, same as
   the cat is a fixed resident of the hut — not something acquired,
   found, or unlocked.
5. The chicken does not wander. Unlike the cat (drawn between hut and
   yard toward warmth), it stays in the yard, full stop — visually and
   mechanically distinct from the cat's whole wandering/warmth system.

## A trap explicitly not being built

The tempting version — a hen that gets hungry and needs feeding — is
worth naming so nobody reaches for it later. The world already has one
care-loop (the cat's hunger) that reliably crowds out everything else:
potatoes flow to the loud, legible hungry thing, and a hand rarely cooks
for itself or does anything else with a scarce turn. A second hungry
animal doesn't add variety — it doubles down on the exact imbalance the
pacing rebalance already fought once. **Do not add a hunger attr, a
feeding verb, or any state the chicken can be neglected in.** If a future
change proposes any of these, it has misread this doc.

## The chicken itself

- Built into `build_world()` directly, in the yard, the same way
  `build_cat` adds the cat to the hut — present in every fresh world, no
  discovery mechanic.
- Two behaviors, both stateless per-tick rolls (no session or persisted
  counters needed, unlike the cat's hunger):
  - **`chicken_idle`** — ambient flavor lines only (pecking, scratching,
    a dust-bath), same shape as `cat_idle`/`CAT_IDLE_LINES`: a small
    per-tick chance, `world.announce`d, zero state change. Unlike
    `cat_idle`, there's no hunger gate to check — it can fire on any
    tick.
  - **`chicken_lay`** — a small per-tick chance of creating one "an egg"
    entity in the yard and announcing it (e.g. "A hen clucks once,
    pleased with itself — there's an egg in the straw."). This is
    **not** a curio-style found-roll layered onto another action (like
    `forest_finds` riding on `gather wood`) — it's the chicken's own
    ambient tick, independent of anything the hand is doing, discoverable
    by being in the room the way a low hearth is, not by a roll on a
    deliberate forage action.
- **`name chicken <name>`** — nameable, same as the cat: reuses
  `cmd_name`'s exact shape (sanitizing, `given_name` attr, sticks for
  every future visit) rather than writing a parallel verb. The cleanest
  path is generalizing `cmd_name` to look up whichever named animal is
  present in the room (cat or chicken) instead of hardcoding
  `world.get("cat")`, the same kind of table-driven generalization
  `cmd_cook` is already getting for eggs below — not a second `cmd_name_
  chicken` copy-pasted from the cat's. `_cat_cap`-equivalent capitalization
  (name if given, else "The chicken") needed for its own announce lines.
  `available_actions` offers `name chicken <name>` only once the chicken
  is unnamed, same gate the cat's own listing uses.
- No `pet chicken` in this pass — see "Explicitly NOT in scope" below.
  Cheap to add later; deliberately not bundled in now to keep the rest of
  this pass to exactly "producer of eggs and atmosphere."

## Eggs

- A discrete entity, `"an egg"`, portable, created by `chicken_lay` in
  the yard. No cap, no decay — same shape as harvested potatoes piling up
  if nobody cooks them.
- **Cooking**: extends `cmd_cook`, which today is hardcoded to potatoes
  only (`"potato" not in e.name` gate, one hardcoded cooked name/
  description). Generalize to a small table of cookables —
  `{"potato": (cooked_name, cooked_desc, food_value), "egg": (...)}`  —
  so `cook egg` at a lit cooking fire works the same way `cook potato`
  does today, with its own cooked name/description/food value. The
  lit-hearth requirement is unchanged and shared, not duplicated.
- **Eating**: `cmd_eat` already works on anything with `attrs["food"] >
  0` regardless of name, so a cooked egg needs no changes there at all —
  it becomes edible for free once `cmd_cook` sets its `food` attr.
- **Resolved: egg's food value is 15** (half `POTATO_FOOD_VALUE`'s 30) —
  confirmed with the user; an egg reads as a smaller meal than a potato.
  Same tuning caveat as any pacing number here: revisit after real play
  the way `ACTOR_HUNGER_CAP` itself has been.
- **Resolved: cooked name is `"boiled egg"`**, description "a hard-boiled
  egg, shell cracked and cooling", sitting alongside `"broiled potato"`.
  Confirmed with the user.

## Why this isn't a second cat, and isn't a curio

Structurally the chicken is closer to the cat than to a curio — a named,
persistent, autonomous entity with its own behaviors — but it shares none
of the cat's actual mechanics (no hunger, no wandering, no give-to-cat
interaction, no naming in this pass). It is **not** a curio: eggs aren't
found via a forage roll, aren't `curio=True`, and don't touch the shelf/
cairn/give-to-cat/tuck-in-journal system — same exclusion logic as raw
clay and shaped clay objects, for the same reason (an egg is produced by
the world on a schedule, not discovered and disposed of).

## Tests to write first

- The chicken exists in a freshly built world, in the yard, before any
  hand acts.
- The chicken has no `hunger` attr, ever, at any point in its lifecycle —
  a direct pin against the trap this doc names, mirroring
  `test_cat_hunger_is_capped_and_never_becomes_harm`'s role for the cat.
- `chicken_idle` never changes any entity's state, only announces —
  same technique as the cat-idle/curio-compression "touches no
  maintenance resource" tests (call the behavior directly, assert
  world/actor/hearth/bucket state is byte-identical before and after).
- `chicken_lay`, forced to fire (a rigged rng), creates exactly one new
  egg entity in the yard and announces it.
- The chicken never leaves the yard across many ticks (no exit-crossing
  behavior exists to move it) — regression guard against a future
  `chicken_wander` accidentally getting attached.
- `cook egg` at a lit hearth produces a cooked egg with `food > 0`, the
  same shape as `cook potato`; `cook potato` is unaffected by the
  generalization (regression test on the existing table entry).
- `cook egg`/`cook potato` both refuse without a lit cooking fire, same
  refusal text as today.
- `eat <cooked egg>` reduces hunger by the egg's `food` value, same path
  as eating a cooked potato — no changes needed to `cmd_eat` itself, but
  worth a direct test since this is the first non-potato food to exist.
- Eggs are not `curio=True`, and do not appear in shelf/give-to-cat/
  cairn/tuck's `available_actions` lists.
- Eggs pile up with no cap across repeated forced lays (mirrors an
  equivalent potato-pileup test if one exists, or is written alongside
  this).
- The chicken and any eggs survive a save/load round-trip.
- `name chicken <name>` sticks (persists across save/load, same as
  `name cat`), and the chicken's own announce lines use the given name
  once set; `name cat` is unaffected by whatever generalization
  `cmd_name` gets (regression test, same shape as `cook potato`'s).
- `name chicken <name>` requires the chicken to be present (mirrors
  `name cat`'s own requirement) — trivially true here since the chicken
  never leaves the yard, but worth pinning as an explicit test rather
  than an assumption.
- `available_actions` offers `name chicken <name>` only while the
  chicken is unnamed, same gate the cat's listing already uses.
- Fuzzer (`--fuzz`) terminates cleanly with the chicken registered.

## Exit criteria

A fresh world has a chicken in the yard from the start, doing small
ambient things and never needing anything. Now and then an egg turns up
in the yard on its own, with no forage roll and no hand action required
to produce it. A hand can cook that egg at a lit hearth and eat it, the
same two-step loop the potato already teaches, or leave it — eggs pile up
harmlessly, exactly like unharvested potatoes do, with no decay and no
penalty for ignoring them.

## Explicitly NOT in scope for this pass

- **Any hunger, feeding, or neediness on the chicken's part** — this is
  the whole point of the design; see "A trap explicitly not being built."
- **`pet chicken`** — cheap to add later, deliberately not bundled into
  this pass. (`name chicken` IS in scope — see "The chicken itself"
  above; only petting stays out.)
- **Wandering** — yard-only, permanently, not just for this pass. A
  future change should not casually attach a `chicken_wander` behavior
  without revisiting this doc's design-goal #5.
- **A nest, or any egg-capacity/collection mechanic** — eggs behave like
  loose potatoes, not like a curio shelf; no container to manage.
- **Any interaction with the shelf/cairn/give-to-cat/tuck-in-journal
  system** — same exclusion as clay; an egg is a food item, not a curio.
- **Multiple chickens, or a chicken-breeding mechanic** — one chicken,
  same restraint as the cat (one cat) and the mystery seed (one plant at
  a time).
