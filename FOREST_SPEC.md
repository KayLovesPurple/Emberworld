# The Forest — Design Spec

*Staged implementation plan. Build in order; each stage should pass its own
tests before the next begins. Follows the test-first workflow in
ARCHITECTURE.md: observe → diagnose → write tight spec with tests → implement.*

## Design goals (recap, so this doc stands alone)

1. The forest carries three things at once, per the README someday-list:
   wood-gathering relocates here, the mysterious statue lives here, and the
   tea-herb grows here.
2. Unlike the yard/hut, the forest should not be a small graph of known
   rooms. It should feel genuinely unauthored in its texture — no map, real
   (if bounded) risk of coming out differently than expected.
3. A visit is 20–30 turns total, so forest depth cannot be a second
   persistent world-state the next visitor inherits lost. Effects persist;
   position does not.
4. Nothing here may become a forced maintenance loop (calm-axis invariant).
   No new hunger, no new decay, no new "must tend" object.

*Note: the cairn (`stack stone on cairn`, ARCHITECTURE.md) lives at the
forest's edge but isn't one of the stages below — it's a standalone
calm-axis feature (a collective, permanent fourth fate for found stones,
alongside the shelf) that didn't need to wait on forest texture or depth.*

---

## Stage 1 — Skeleton: depth model, no texture, no risk

**Status: ✅ done.** `world.forest_depth` (a plain runtime attribute, never
persisted), `venture`/`return` verbs, and their tests all shipped.

**Goal:** get a minimal forest that existing systems can plug into, with
correct persistence semantics decided before anything else is built.

**Data model:**
- `forest_depth: int` — session-scoped, NOT part of the persisted save.
  Starts at 0 (the edge, already built) each time a `--llm` or human session
  begins.
- Add `forest_depth` to the transient/runtime state object, not to
  `emberworld_save.json`.
- New verbs: `venture` (depth += 1), `return` (depth -= 1, floor 0). Both
  fixed-flavor text at this stage — just prove the plumbing.
- Leaving the forest (`return` at depth 0, or ending the session while inside
  it) does not need special-casing yet; that's Stage 3's job.

**Tests to write first:**
- `venture`/`return` change `forest_depth` correctly and never go negative.
- `forest_depth` is absent from a saved-and-reloaded world (i.e. loading a
  save always starts a new visitor at the edge, depth 0).
- Invariant checker passes with the new transient field ignored.

**Exit criteria:** you can walk in and out of the forest across a save/reload
boundary and nothing about depth survives the boundary. This is the
foundation the whole "episodic, not a place" idea depends on — get it right
before adding anything interesting.

---

## Stage 2 — Texture generation: fragments, not rooms

**Status: ✅ done.** `FOREST_FRAGMENTS` (near/mid/deep bands, each with
light/sound/undergrowth/smell pools), `_forest_band(depth)`, and
`describe_forest(depth, rng)` all shipped, wired into `venture`/`return`'s
own result text.

**Goal:** replace fixed venture/return text with recombined description
fragments, banded by depth, so no two visits read the same and you (the
designer) don't hand-author individual "rooms."

**Data model:**
- `FOREST_FRAGMENTS`: a dict keyed by depth band (e.g. `"near"` = depth 1–2,
  `"mid"` = 3–5, `"deep"` = 6+), each value a list of independent fragment
  pools — light, sound, undergrowth, smell — not full sentences to splice,
  but composable clauses.
- A `describe_forest(depth, rng)` function picks one fragment per pool per
  band and assembles a short paragraph. Use the world's existing RNG
  (whatever `content.py` already seeds) so `--fuzz` runs stay deterministic
  under a fixed seed.
- Keep pools small at first (4–6 entries each) — this is meant to be
  extended over time, not exhaustive on day one.

**Tests to write first:**
- `describe_forest` is deterministic given a seeded RNG (same seed → same
  output), even though it's varied across runs — critical for `--fuzz` and
  for debugging via `--show-thoughts`.
- Every band has at least one entry in every pool (no empty-pool crash).
- Depth bands are contiguous and cover depth 0 upward with no gaps.

**Exit criteria:** venturing in produces genuinely different prose across
repeated plays, and depth still doesn't persist across sessions.

---

## Stage 3 — Episodic reset (the load-bearing stage)

**Status: ✅ done.** See ARCHITECTURE.md's "Stage 3" section for how this
landed: rather than a literal "session-end hook" (unnecessary given
`to_data()`'s hardcoded shape — see below), the rule is pinned by a
structural test on `to_data()` itself plus a full mid-visit
save/reload regression test. `calm_visits` (added after this spec was
written, alongside the calm-axis acknowledgment feature) gets the identical
treatment as `forest_depth` throughout.

**Goal:** formalize "effects persist, position doesn't" — this is the actual
fix for the "next guy starts lost" problem, and it should be a named,
tested rule, not an implicit side effect of Stage 1's data model.

**Rule to encode:** anything an agent *does* in the forest that produces a
durable object or state change outside the forest (wood carried out, a curio
found, a wish logged at the statue, an herb picked) persists normally through
the save file, same as any other action. `forest_depth` itself, and any
transient "how deep / which way" state, is discarded the moment a session
ends — deliberately, not as a bug.

**Implementation:**
- Confirm (from Stage 1) that `forest_depth` truly never touches
  `emberworld_save.json`.
- Add a session-end hook (wherever `drivers.py` already tears down an `--llm`
  or human session) that explicitly drops forest-transient state, so the
  next session's world load can't accidentally pick it up even if a future
  refactor moves fields around carelessly.
- Document the rule directly in `ARCHITECTURE.md`'s "adding a feature"
  section: *forest position is episodic; forest effects are persistent.*

**Tests to write first:**
- A full save→reload cycle mid-forest-visit: verify depth resets to 0 but
  any curio/wood/wish already committed to the save survives.
- A regression test explicitly named for this (e.g.
  `test_forest_depth_does_not_leak_across_sessions`) so a future edit that
  breaks it fails loudly and specifically.

**Exit criteria:** you can end a session at depth 8, reload, and the next
visitor starts at the edge with no memory of that depth — while anything
they *made* while there is still in the world.

---

## Stage 4 — Getting lost: a bounded, opt-in risk

**Status: ✅ done.** `SAFE_DEPTH_THRESHOLD` (3) and `OFF_COURSE_CHANCE`
(0.18) in content.py, both applied inside `cmd_return`. See
ARCHITECTURE.md's "Stage 4" section for the landed shape, including how the
off-course depth is chosen (never the expected depth-1, never negative).

**Goal:** make "no map" cost something real, but only for a visitor who
chooses to push past a safe default — never a chore, never forced.

**Data model:**
- Define `SAFE_DEPTH_THRESHOLD` (e.g. 3) — within this, `return` always
  works cleanly, exact inverse of `venture`.
- Beyond the threshold, each `return` has a small chance (tune during
  playtesting — start low, e.g. 15–20%) of landing the visitor back at a
  *different* depth than expected (never past the edge in the wrong
  direction — floor is always 0) with a distinct "you're not sure this is
  where you came from" fragment from Stage 2's pools.
- No penalty beyond the depth mismatch itself — no damage, no lost items,
  no wasted turn beyond the one just spent. The disorientation *is* the
  whole cost.

**Tests to write first:**
- Below `SAFE_DEPTH_THRESHOLD`, `return` is always exact (no randomness) —
  this must be airtight, since it's the safety guarantee for short/casual
  visits.
- Above the threshold, the "off-course" outcome only ever lands at a
  non-negative depth.
- `--fuzz` still terminates cleanly with the new branch (no infinite
  venture/return loop possible).

**Exit criteria:** a 6-turn dip into the forest is provably risk-free; a
deliberate deep push trades turns for a real, legible chance of not coming
straight back out.

---

## Stage 5 — Trail-marking (optional mitigation, freely chosen)

**Status: ✅ done.** `mark trail` (`cmd_mark_trail` in content.py) and
`world.forest_mark_depth` (session-scoped, alongside `forest_depth` and
`calm_visits`). See ARCHITECTURE.md's "Stage 5" section for the landed
shape, including how it composes with Stage 4's off-course roll.

**Goal:** give the risk in Stage 4 a player-facing lever, so it reads as a
choice rather than a dice roll happening to you.

**Data model:**
- New verb: `mark trail` (costs the turn, requires nothing consumable —
  keep it cheap and available, not gated behind an item, to avoid adding a
  new resource dependency).
- If the current depth has been marked, `return` from anywhere above it
  treats that depth as a new safe checkpoint — the off-course roll in
  Stage 4 only applies beyond the deepest *marked* point, not beyond the
  original threshold.

**Tests to write first:**
- Marking at depth 5 makes depth 5 behave like the safe zone for `return`
  purposes, without changing behavior below depth 5.
- Marking doesn't affect Stage 2's texture generation (still varied) or
  Stage 3's persistence rule (marks are transient too, same as depth).

**Exit criteria:** an agent that marks as it goes can push arbitrarily deep
with bounded risk; one that doesn't accepts the Stage 4 odds as written.
Calm-axis check: this is a free choice with no maintenance implication, so
it's fine to add.

---

## Stage 6 — Ambient, unscripted texture

**Goal:** the actual "crack in the closedness" — events not tied to any
verb, that neither the player nor you-the-designer fully control the timing
or shape of.

**Data model:**
- `FOREST_AMBIENT`: a separate pool from Stage 2's descriptive fragments —
  short, self-contained lines (rustling with nothing behind it, a call from
  an unseen bird, a smell with no source) that can surface on *any* forest
  turn, at low independent probability, layered on top of whatever
  `describe_forest` already returned that turn.
- Deliberately no verb references these. No "investigate" option. They are
  not mysteries with answers — same restraint as the statue.

**Tests to write first:**
- Ambient lines never crash when they co-occur with a Stage 4 off-course
  event or a Stage 5 mark — i.e. text composition order is defined and
  tested, not accidental.
- Ambient pool, like Stage 2's, is deterministic under a seeded RNG for
  `--fuzz` reproducibility.

**Exit criteria:** forest turns occasionally surface something with no
mechanical hook at all — texture that exists whether or not anyone notices
it, same spirit as the statue.

---

## Stage 7 — Integration: the three things the forest carries

**Goal:** now that the forest itself is built, move in the content the
README already commits to.

- **Wood-gathering relocates here.** Remove/disable the yard's
  wood-gathering verb; add it to the forest (any depth, to avoid punishing
  short visits — this is still the grandfathered hearth-fuel loop, just
  moved, not intensified).
- **The statue** is randomly discovered, not placed at a fixed depth — a
  fixed coordinate would quietly reintroduce the authored-map problem
  Stages 2–6 exist to avoid. Below `STATUE_MIN_DEPTH` (e.g. 3, the same
  "mid band" floor used elsewhere) it cannot appear at all — it stays a
  deep-visit thing, not a short-trip accident. Beyond that floor, each
  `venture` carries a small independent chance (tune during playtesting,
  similar order of magnitude to Stage 4's off-course roll) of surfacing it,
  using the same fragment-composition approach as Stage 6's ambient events.
  Once discovered in a session, set a transient `statue_found_this_session`
  flag (same lifetime as `forest_depth` — gone at session end via Stage 3's
  reset) so it doesn't flicker in and out of existence on repeated looks at
  the same depth. Mechanically inert per its own existing spec regardless
  of how it's found: `wish <something>` is a no-op that logs the wish and
  returns an atmosphere line. Not finding it on a given visit is not a
  failure state — it's the same "un-granted and that's fine" logic the
  statue's own spec already applies to wishes, one level up: now the
  statue itself is something a visit might not get to reach at all.
- **The tea-herb** grows somewhere in the "near" or "mid" band, foraged with
  a simple always-available verb (no growth timer — that would be a second
  farming loop, which the calm-axis invariant rules out). One herb per
  visit is a reasonable soft cap, mirroring the one-potato rule's spirit
  without literally copying it.

**Tests to write first:**
- Wood is no longer gatherable in the yard; is gatherable in the forest.
- The statue's existing wish-logging behavior (if already implemented
  elsewhere) works correctly wherever it's discovered.
- The discovery roll never fires below `STATUE_MIN_DEPTH`.
- Once found, repeated interaction within the same session is deterministic
  — no re-rolling whether the statue is "still there."
- Herb-gathering has no persistent per-world timer or regrowth state — it's
  available on every visit, capped only per-visit.

**Exit criteria:** the forest is a real, connected part of the world's
existing systems, without having grown a second maintenance loop anywhere
in the process.

---

## Cross-cutting requirements (apply from Stage 1 onward)

These aren't their own stage — they're small, easy-to-miss details that
several stages depend on. Get them right early rather than patching later.

- **`venture` costs exactly 1 turn, same as any other action.** This is
  what makes the turn-budget-vs-depth tradeoff in Stage 4 mean anything —
  if it ever stops being 1:1, Stage 4's odds need re-tuning alongside it.
- **Leaving the forest is always free, at any depth, for any reason.** If a
  session or turn budget ends while an agent is at depth 8, they simply
  leave — no forced walk-back, no penalty, no "you must return before
  you're done." Anything else is a maintenance chore in disguise, which the
  calm-axis invariant rules out.
- **Every new verb goes through normal registration.** `venture`, `return`,
  `mark trail`, and the statue's `wish` all need to flow through whatever
  pattern the existing verbs use, so `python3 emberworld.py --reference`
  picks them up automatically. `REFERENCE.md` is generated from code and
  staying current depends on this.
- **Invariant checker gains forest-specific checks.** `--check` should also
  verify: `forest_depth` is never negative; `statue_found_this_session` is
  never `True` when depth is below `STATUE_MIN_DEPTH`; no forest-transient
  field (depth, marks, statue flag) ever appears in a loaded save.
- **Defined composition order when forest events stack.** A single
  `venture` could in principle trigger a statue discovery, an off-course
  roll (Stage 4), and an ambient line (Stage 6) together. Fix an explicit
  order — e.g. discovery text leads, then off-course, then ambient — so
  output is deterministic and testable, not accidental.
- **Explicit non-scope.** The cat does not follow into the forest. Birds
  (and any wildlife) stay deferred per the README's own someday-list — the
  ambient pool in Stage 6 is atmosphere only, not license to add
  cat-reactive creatures now.

---

## What NOT to add, and why

- **No forest map, ever** — even a "sometimes you find a landmark" system
  would start re-authoring the closedness this whole feature exists to
  avoid. If landmarks are wanted later, keep them cosmetic (Stage 6-style),
  never navigational.
- **No stat that decays while lost** (stamina, warmth, etc.) — that's a
  second hunger loop with a different name, exactly the trap the chicken
  design note already identified and rejected.
- **No "solve" for the statue or the ambient events** — both stay
  deliberately unexplained. Resist every future urge to give them meaning.
