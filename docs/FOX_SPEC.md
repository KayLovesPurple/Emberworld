# The Fox — Design Spec

*Design spec. Follows the test-first workflow in ARCHITECTURE.md: observe
→ diagnose → write tight spec with tests → implement.*

## Status

**Not built.** Agreed design, ready to implement after the smaller queued
items (twine truth-fix, reed whistle, cat's corner — see README's
"Someday" section).

## Where this came from

Two observations from real lineage play, taken together:

1. **The egg glut.** The hen produces faster than anyone eats; a real
   session ended with a hand carrying nine eggs. Eggs have exactly one
   fate (cook, eat), so "richer" was drifting toward "more stuff."
2. **The texture animals worked.** The fox/owl/deer sightings — pure
   atmosphere, no verb attached — landed as intended: proof the world
   holds more than the hand walking through it.

The fox takes one of those animals and gives it the slowest arc in the
game: a relationship measured in *lineage* time, not visit time. No
single hand can tame her; no hand ever knows how far along she is.

## Design goals

1. **The fox is the cat's wild counterpart.** The cat is a relationship
   on visit-time (feed, pet, purr, all within one hand's stay). The fox
   is a relationship on lineage-time: offerings across many hands slowly
   ratchet a trust counter, and the payoffs arrive on the world's
   schedule, likely to a different hand than the one who earned them —
   the planter-and-stranger logic of the mystery seed, applied to an
   animal.
2. **Offering is the egg's second fate, and it's a chosen one.** `leave
   an egg out` in the yard is one-way and anonymous, cairn-grammar: the
   egg is gone by morning, from the very first offering onward (no
   doorstep clutter at low trust), and nothing owes you anything for it.
   This is the egg sink — surplus converted into yearning instead of
   inventory.
3. **THE CONSTRAINT THAT MUST NEVER BREAK** (same register as the cat's
   GENTLE GUARANTEE and the statue's inertness): **the fox can never
   come to harm and can never do harm.** She never touches the hen,
   never takes an ordinary yard egg (only one deliberately left out),
   never has hunger, never has any need, and trust never decreases. A
   real fox eats chickens; this one is prose, and prose is gentle here.
4. **The fox is not an entity.** She is never present in any room, never
   listed, never actable-on. All her state (trust, name, gift
   bookkeeping) lives in `attrs` on the yard. This isn't an
   implementation shortcut — it's the guarantee in goal 3 made
   structural: there is no fox object to harm, feed, chase, or cage.
   (`name fox` is the one verb that touches her, and it writes to the
   yard's attrs — see "Naming" below.)

## A trap explicitly not being built: the transactional fox

The tempting version — offer an egg, get a gift — is a vending machine,
and worth naming so nobody reaches for it later. The moment a gift
legibly follows an offering, hands will farm her (eggs in, curios out),
which is the cat-hunger crowding-out problem in fur, and the exact
"manufactured want" failure the wishing-statue was designed around.

The two halves are therefore **decoupled, hard**:

- **Offerings raise trust.** A one-way lifetime ratchet, persisted,
  never decaying (decay would be a maintenance loop). Trust gates which
  texture stage the lineage is in and, at its ceiling, whether gifts are
  *possible at all*.
- **Gifts run on her own clock.** Once trust has crossed its ceiling, a
  gift is a rare per-tick world roll (through `world.rng`), deliberately
  independent of recent offerings — and **suppressed for a window of
  ticks after any offering**, so the correlation can never be observed
  even by accident. A hand who never leaves an egg can find a gift; a
  hand who leaves five sees nothing for it that visit.

If a future change proposes tying gift timing or gift rate to offerings
in any legible way, it has misread this doc.

## The arc, stage by stage

Trust thresholds (exact numbers are tuning, like all pacing numbers
here) gate texture only, until the ceiling:

1. **Prints.** The first offerings vanish overnight; morning texture in
   the yard says only "small prints in the dew, gone at the gate."
2. **A glimpse.** Something russet at the treeline at dusk, gone before
   you're sure — deliberately reusing the register of the existing
   uninvited-animal lines.
3. **Seen.** She is seen, once, actually taking the egg — the first
   confirmed fact the lineage has about her. **Naming unlocks here**
   (see below): you name what you've laid eyes on.
4. **She lingers.** Taking the egg, she pauses a beat before the dark
   takes her.
5. **Ceiling.** Gifts become possible, on her clock, forever after.
   Trust keeps counting (harmlessly) but nothing further gates on it.

## The offering

- **`leave egg out`** — new verb, listed in `available_actions` while in
  the yard carrying an egg (raw or cooked alike; she's not fussy). Sets
  the egg by the fence: a placed, visible entity for the rest of the
  day ("an egg left by the fence, for whoever the night brings").
- During the night, the offering is **always taken** — removed, trust
  incremented, morning texture queued per the current stage. Always,
  from offering one: an untouched offering would just rebuild the egg
  clutter one room over.
- At most one offering can be out at a time (`available_actions` simply
  stops listing the verb while one waits) — same one-in-play restraint
  as the mystery seed.
- The verb needs no fox-knowledge to appear — a fresh hand can leave an
  egg out on day one for no reason they could articulate, which is
  exactly the right amount of mystery. The *result* (prints in the dew)
  is how the fox announces herself.

## Naming

- **`name fox <name>`** — unlocks at the "seen" stage and behaves like
  `name cat`/`name chicken` from the hand's side, but writes
  `given_name` into the yard's fox-attrs, since there is no fox entity.
  `cmd_name`'s animal lookup grows one virtual entry rather than a
  parallel verb.
- Once named, the name flows into every subsequent texture line —
  "prints in the dew again; Sorrel, someone decided" — which is how a
  memoryless hand inherits both her existence and her name in one line,
  the same trick the cat's given name already pulls.
- Before the "seen" stage the verb does not exist anywhere: a fresh
  world can't name a fox it has no evidence of (affordances-on-sleeve,
  and it keeps the reveal honest).

## The gifts

- A small **fox-specific pool**, not reused forest curios. The fox
  travels where no hand can ever go, so her gifts read as postcards
  from off the map: a feather from no bird the yard knows, a pebble
  smoothed by some upstream water, a scrap of faded ribbon, a tiny blue
  eggshell. Each description carries her provenance ("it smells faintly
  of fox, and of somewhere else") so a hand knows on sight it was
  *brought*, not found.
- Spawned at the hut's doorstep (in the yard, by the door), announced
  in morning texture. **At most one unclaimed gift in the world at a
  time** — no new roll succeeds while one waits (seed-restraint again).
- Gifts are ordinary curios (`curio=True`): carry, shelf, give to the
  cat — there is something right about giving Ember a fox's gift — with
  each item picking its subset of fates like any curio. Unlike cat
  traces, they are fully portable; they enter the economy, they don't
  memorialize it.
- Rare on purpose, in the "cut twice in real play" register of the
  forest find-chance: a gift should be an event a journal entry gets
  written about, not a faucet.

## Persistence

- Trust counter, given name, offering-out flag, gift bookkeeping (and
  the post-offering suppression window) all persist in the yard's
  attrs. `SAVE_VERSION` bumps if the shape demands it; a pre-fox save
  backfills to zero-trust cleanly (no `ensure_` entity needed — there's
  no entity).

## Tests to write first

- `leave egg out` appears in `available_actions` only in the yard,
  only while carrying an egg, and not while an offering is already out.
- An offering is always gone by morning (forced night ticks), trust
  incremented by exactly one, and the correct stage's morning texture
  announced.
- The hen and ordinary yard eggs are untouched across many forced
  night ticks at every trust stage — the direct pin on design-goal 3.
- No fox entity exists in the world at any trust stage (structural pin
  on design-goal 4).
- Trust never decreases across any sequence of actions and ticks.
- `name fox` is absent from `available_actions` below the "seen" stage,
  present at it while unnamed, sticks across save/load, and appears in
  subsequent texture lines; `name cat`/`name chicken` unaffected
  (regression, same shape as the chicken spec's).
- With trust at ceiling and a rigged rng, a gift spawns at the
  doorstep, is `curio=True`, portable, and joins the curio economy
  (shelf/give-to-cat listings appear as appropriate).
- No gift can spawn within the suppression window after an offering,
  even with a rigged rng — the direct pin on the vending-machine trap.
- No second gift spawns while one is unclaimed.
- Full state survives a save/load round-trip; a pre-fox save loads
  cleanly at zero trust.
- Fuzzer (`--fuzz`) terminates cleanly with the fox behaviors
  registered.

## Exit criteria

A hand can leave an egg out in the yard for no promised reason; by
morning it is gone and the world says one small true thing about what
took it. Across many hands and many offerings the texture deepens in
stages, until she has been seen and can be named. From then on, rarely
and on no schedule anyone can game, something small and far-travelled
turns up at the doorstep — carriable, shelvable, givable to the cat —
and no hand ever knows which offering, if any, earned it.

## Explicitly NOT in scope

- **A fox entity, ever** — no petting, feeding, chasing, or presence in
  any room. She is prose. (Structural, not just this pass.)
- **Any hunger, need, or harm** — in either direction. See design-goal 3.
- **Trust decay, or any way trust decreases.**
- **Any legible offering→gift linkage** — see the trap section.
- **Weather/season interplay, a den, kits, a second animal arc** — none
  of it until a lineage has lived with this version for a long while.
