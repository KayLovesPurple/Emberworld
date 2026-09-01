# The Crossing — Design Spec

*Design spec. Follows the test-first workflow in ARCHITECTURE.md: observe
→ diagnose → write tight spec with tests → implement.*

## Status

**Not built.** Agreed direction; the biggest thing since the forest, and
deliberately last in the current queue (see README's "Someday"). Stage 2
(the far bank's actual content) is intentionally under-specified until
Stage 1 exists.

## The idea, in one paragraph

The river is already a boundary you stand at. The crossing makes getting
over it a **collective construction project**: driftwood, washed up
rarely at the riverbank, laid piece by piece into a crossing — one-way
and anonymous, cairn-grammar — needing enough pieces that no single
visit completes it. Each hand sees its state, contributes or doesn't,
and almost certainly leaves before it's done. One day some hand arrives,
finds the last gap closed by whoever came before, and is the first in
the lineage to step across. This is the cairn's mechanic graduated into
consequence: the first time "many hands, one-way" *unlocks* something
rather than only accumulating — which is the game's thesis at scale.

## Design goals

1. **No single hand can open the far bank.** The piece count is tuned so
   the crossing takes many visits across many hands (at the observed
   cadence — rare driftwood finds, ~1–2 visits a world-day — think
   weeks). The payoff is structurally impossible alone.
2. **Driftwood, not hearth-wood, not stones.** Two reasons, both
   load-bearing:
   - **Fuel must not compete.** Gathered wood feeds the hearth — the
     grandfathered forced loop. If the crossing ate the same wood, every
     contribution would compete with maintenance, and hands would learn
     to starve the fire for it (or the crossing would starve instead).
     Driftwood is its own material, and it **cannot be burned** — the
     refusal says why ("waterlogged through; it will never take flame").
   - **Stones stay the cairn's.** A found stone's one collective fate is
     the cairn; giving stones a second lineage-project would dilute what
     the cairn means.
   There's also the quiet poetry, worth keeping: the river supplies the
   means of its own crossing.
3. **The crossing never washes out.** A one-way ratchet, like the cairn.
   Rebuilding a bridge is a forced maintenance loop, and the calm-axis
   invariant bans new ones. Once laid, a piece is laid forever.
4. **The far bank is pure elsewhere.** Whatever ends up there (Stage 2),
   it gets no patch, no hearth, no animal with needs — nothing to tend.
   It is the world's first place that exists only to be *reached* and
   *been in*. Chores stay on the near side, permanently.

## Stage 1 — driftwood and the crossing

### Driftwood

- A rare find at the riverbank: an independent per-turn chance while
  acting there, the same shape as the forest edge's per-tick find roll
  (and tuned in the same "cut it if it's too fast" spirit). It is
  washed up by the river, not dug — `gather` at the riverbank still
  yields clay, untouched.
- Portable, plain, and **not a curio**: no shelf, no cairn, no
  give-to-cat, no tuck (same exclusion logic as clay and twine — it's a
  means, not a find). `give driftwood to cat` is refused the way twine's
  is, and for the same reason: it's needed whole.
- **Never burns.** `add wood`/the hearth path must not accept it — the
  one rule that keeps the fuel economy and the crossing economy fully
  separate (design-goal 2).

### Laying it

- **`lay driftwood on the crossing`** — at the riverbank, carrying
  driftwood: consumes the piece, increments a persisted counter,
  permanently and anonymously. No take-back, no attribution — cairn
  grammar exactly.
- The crossing's state is always visible in the riverbank's description
  via prose tiers, charm-string-style — from "a first weathered plank
  reaches into the current" through "the crossing stands a few strides
  short of the far bank" — so every arriving hand inherits the project's
  state at a glance, no journal required (though the journal will
  narrate it anyway, and that's half the point).
- `look crossing` gives the exact count's worth of description, the way
  `look cairn`/`look charm` do.
- **Threshold: ~15–20 pieces** (tuning; pick once real find-rates are
  chosen, and err toward too many — a crossing finished in a week is a
  feature that evaporated).

### Completion

- When the last piece is laid, the room announces it plainly, once —
  the laying hand gets that moment; it's the one attributed-feeling beat
  in an otherwise anonymous project, and it costs nothing to give.
- From then on the riverbank has a new exit, `across`, to the far bank,
  and the crossing's description settles into its finished form. The
  exit appearing IS the unlock — no key, no flag a hand can see, just a
  way that wasn't there before.

## Stage 2 — the far bank (deliberately thin here)

Decisions deferred until Stage 1 is real and a lineage has actually
crossed; only the constraints are fixed now:

- Pure elsewhere (design-goal 4): its own quiet, its own `listen`/
  `watch clouds` flavor, possibly its own small curio pool.
- The strongest candidate for what lives there: **the tea-herb** (the
  one unbuilt Stage-7 forest item) — which would make tea itself partly
  a lineage achievement. Candidate, not commitment.
- Nothing on the far side may ever need tending, produce food, or
  extend a maintenance loop. If a proposal for far-bank content does any
  of those, it has misread this doc.

## Persistence

- The crossing counter (and, once open, the exit) persist; backfilled
  onto older saves by an `ensure_crossing(world)` in the
  `ensure_shelf`/`ensure_riverbank` mold. `SAVE_VERSION` bumps if the
  shape demands it.

## Tests to write first

- Driftwood turns up at the riverbank with a rigged rng, is portable,
  and is not `curio=True` (absent from shelf/cairn/give/tuck listings).
- `gather` at the riverbank still yields clay, unchanged (regression).
- The hearth refuses driftwood, with the waterlogged line; `add wood`
  with real firewood is unaffected (regression).
- `give driftwood to cat` is refused, twine-style.
- `lay driftwood on the crossing` consumes exactly one carried piece,
  increments the counter, and is listed in `available_actions` only at
  the riverbank while carrying driftwood.
- The counter never decreases across any action sequence (ratchet pin,
  design-goal 3).
- Prose tiers change at their thresholds; `look crossing` reflects the
  exact count.
- Laying the final piece announces completion once, adds the `across`
  exit, and the exit persists across save/load.
- Before completion, no path to the far bank exists by any action
  sequence (the fuzzer helps here too).
- A pre-crossing save backfills cleanly at count zero via
  `ensure_crossing`.
- Fuzzer (`--fuzz`) terminates cleanly with everything registered —
  including, eventually, runs long enough to complete the crossing.

## Exit criteria (Stage 1)

A hand at the riverbank sometimes finds driftwood the river left, can
lay it into the crossing permanently and anonymously, and can read the
project's progress in the room itself. No single visit can finish it.
When, across many hands, the last piece goes in, the riverbank gains an
exit that was never there before, and whoever happens to be standing
there gets to be first across — inheriting every hand's work, exactly
like reading the journal, except this one you walk on.

## Explicitly NOT in scope

- **Any wash-out, decay, or rebuild mechanic** — see design-goal 3.
- **Burning driftwood, ever** — see design-goal 2.
- **Accepting stones, firewood, clay, or anything but driftwood** — one
  material, one meaning.
- **Far-bank content beyond the constraints above** — Stage 2 gets its
  own pass, spec'd after a lineage has crossed.
- **A boat, a ford of stones, or a second way over** — the crossing is
  the way, and the wait is part of it.
