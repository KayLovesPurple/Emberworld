# Refactoring — agreed, queued, not yet applied

*A code-health backlog, agreed after a full read of the codebase (world day
75, alongside the feature queue in README's "Someday" section). None of
these change behavior; every one should land green against the existing
tests and the fuzzer. Roughly ordered by value — and 1–5 are each small
and independently shippable, worth doing before or alongside the agreed
feature queue, since the fox and the crossing build directly on several
of them.*

## 1. An `ENSURES` registry for backfills

`drivers.load_or_build` hand-calls seven `ensure_*` functions and
`build_world` calls an overlapping subset; every new feature adds one
more to both call sites (CROSSING_SPEC already promises an
`ensure_crossing`, and the cat's corner will add another). This is the
problem the codebase has already solved three times — `VERBS` /
`BEHAVIORS` / `ACTION_SOURCES` exist precisely so world.py and drivers.py
don't have to know each feature by name. Add a fourth registry in
world.py that each module appends its backfill to, iterated by
`load_or_build` and `build_world`. Keep it a **list**, like
`ACTION_SOURCES`, in case order ever matters (it shouldn't today, but a
registry that silently reorders is how it starts mattering).

## 2. A shared `banded()` helper

`_cairn_description` (curios.py), `_charm_string_description`
(curios.py), and `_bloom_description` (content.py) are three
byte-identical walk-the-`(threshold, line)`-bands loops; the hearth and
lamp hand-roll the same idea. One small helper in content_common.py
collapses them — and it's about to earn its keep four more times: the
crossing's prose tiers, the fox's trust stages, and the cat's corner's
deepening line all want exactly this shape. Do this one *before* the
feature queue if possible, so the new features are born on the helper
rather than adding a fourth and fifth copy.

## 3. Data-key the calm verbs by room

`cmd_listen` is an if/elif over two rooms with two line pools;
`cmd_watch_clouds` and `sky_actions` each hardcode the tuple
`("yard", "forest_edge", "riverbank")` separately. Replace with a
`LISTEN_POOLS = {room_id: lines}` dict and one `OPEN_SKY_ROOMS`
constant, so the far bank's own quiet (which CROSSING_SPEC requires
Stage 2 to have) becomes a one-entry addition instead of a third elif
and a third tuple edit.

**Drive-by while there:** `_EXIT_LABELS` never got a `"river"` entry,
so the yard's Exits line reads "inside the hut, the forest's edge,
river" — the one bare key among labeled ones.

## 4. A `LOOK_OVERRIDES` hook

`cmd_look` special-cases `CHARM_STRING_ID` inline — the general verb
knowing one specific entity, which this codebase otherwise never does.
A small `LOOK_OVERRIDES = {entity_id: fn}` registry (same shape as
`PRESENCE_RULES`: the general machinery asks, the specific subsystem
answers) lets curios.py own the charm-string's ASCII rendering — and
the cat's corner (`look corner`) and the crossing (`look crossing`)
both want the same hook, so it's better built once now than
special-cased twice more.

## 5. Finish the VisitState migration

world.py carries ~50 lines of property/setter shims explicitly labeled
as aliases for existing call sites (`world.forest_depth` forwarding to
`world.visit.forest_depth`, etc.). The call sites are few — the forest
block in content.py, journal.py, drivers.py. Point them at
`world.visit.<field>` directly and delete the shims. Mechanical,
test-backed, and it removes the two-names-for-one-field trap before the
fox adds session state of its own.

## 6. Split the LLM driver out of drivers.py

drivers.py is ~930 lines, and ~600 of them are one coherent slice: the
LLM visit (the naming pools and their seven rounds of bug history,
prompts, nudges, refusal markers, flagged thoughts, the sign-off, the
session logs). That's exactly the "grew into a coherent slice"
threshold that spun off cat.py / curios.py / journal.py. Move it to
`llm_driver.py`, leaving drivers.py with play / random agent / fuzzer /
`load_or_build`. Relatedly, `llm_agent` itself is a ~110-line function;
extracting the per-turn body makes the loop's shape legible on its own.

## 7. Split the forest out of content.py

content.py is back at ~2100 lines post-splits. The forest block
(venture / return / mark trail, the statue and `wish`, the find and
wildlife rolls — ~400 lines) is the largest coherent slice left,
already has its own spec doc (FOREST_SPEC.md) and a sibling module
(forest_text.py); `forest.py` follows the house pattern exactly. The
mystery seed/bloom block (~130 lines) is a second candidate. Worth
doing *before* the feature queue lands, since fox.py and the crossing
will grow the codebase around whatever shape content.py is in.

## 8. Longer-term: refusals as a signal, not a substring list

`_REFUSAL_MARKERS` (drivers.py) is a hand-synced list of phrases that
must track every refusal string across four modules — the one genuinely
drift-prone coupling in the codebase: a reworded refusal silently
starts counting as an accomplishment in the sign-off's `did` list, with
nothing failing. The structural fix is a `refuse(msg)` helper that
verbs route refusals through, setting a per-act flag the driver reads
instead of grepping result text. It touches many call sites, so it's a
when-convenient change — but every new verb in the feature queue adds
refusal strings, and the list only gets more brittle from here. Until
then, at minimum, a test asserting each marker still matches some real
refusal string would catch silent drift.

## The order, if doing them as a batch

2 (banded) → 1 (ENSURES) → 4 (LOOK_OVERRIDES) → 3 (calm pools) →
5 (VisitState) as one small-change run; then 7 and 6 as the two big
mechanical moves; 8 whenever the verb surface is next quiet. Run the
full test suite plus `--fuzz` after each one, per ARCHITECTURE.md's
loop — none of these should ever need a `SAVE_VERSION` bump, and if one
seems to, something has gone wrong with it.
