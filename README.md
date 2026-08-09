# Emberworld

*Built together with Claude Opus 4.8 and Sonnet 5 — noted once here rather
than on every commit.*

A small text world that keeps ticking whether or not anyone's watching — a
hearth needs feeding, a potato grows, night falls, a cat wanders and gets hungry.
You can play it yourself, or let a Claude reach in over the API and live in it
for a while. Because the world saves to disk, visits form a lineage: someone
plants a potato and leaves a note; someone else — with no memory of the first —
reads that note and harvests the crop.

## Files

- `emberworld.py` — the CLI entrypoint (`python3 emberworld.py ...`). No
  dependencies to play.
- `world.py` — the engine: Entity/World, the tick loop, persistence, the
  invariant checker.
- `content.py` — Emberworld itself: the verbs, the autonomous behaviors, and
  the world as assembled fresh.
- `cat.py` — the cat as its own self-contained subsystem: its constants,
  behaviors, verbs, and how it's built into a fresh world.
- `forest_text.py` — the forest's generated texture: the near/mid/deep
  fragment pools and the ambient lines, plus the two small functions that
  compose them. Pure writing, no world state; split out because it's the
  largest block of prose in the game and gets edited as prose.
- `drivers.py` — the three ways to drive the world (human, dumb agent, LLM),
  the persistence-loading glue, and the headless fuzzer.
- `test_world.py` / `test_content.py` / `test_cat.py` / `test_drivers.py` — the
  safety net, split to match. Each runs with or without pytest;
  `_test_helpers.py` holds the handful of things they share.
- `docs/REFERENCE.md` — every verb, behavior, and rule. **Generated from the
  code** (`python3 emberworld.py --reference`), so it's always current.
- `docs/ARCHITECTURE.md` — how it's built, and the recipe for adding a feature
  without breaking anything.
- `docs/FOREST_SPEC.md` — the forest's staged build spec. `docs/` also holds
  a couple of not-yet-built design proposals.
- `emberworld_save.json` — the persistent world (created on first run; safe to
  delete to start fresh).

## Quickstart

```bash
python3 emberworld.py            # play it yourself
python3 emberworld.py --check    # play with invariants verified after every action
python3 emberworld.py --agent    # a dumb random agent drives it (no API key)
python3 emberworld.py --llm --turns 40   # let a Claude live in it (needs a key)
python3 emberworld.py --llm --show-thoughts   # also print the agent's reasoning (dimmed)
python3 emberworld.py --fuzz     # 5000 random steps, invariants checked each tick
python3 emberworld.py --reference > docs/REFERENCE.md   # regenerate the reference
```

For `--llm` you need `pip install anthropic` and `export ANTHROPIC_API_KEY=...`.
Add `--show-thoughts` to see *why* the agent chose each command (its thinking,
printed dimmed above the command) — the best way to debug odd behaviour. Colours
auto-disable when output isn't a terminal; `--no-color` forces them off.
`--debug-thinking` is a separate, noisier flag on top of that: it prints the
raw API response shape (block kinds, `stop_reason`, token usage) whenever a
turn comes back with no reasoning summary -- worth it if you're chasing why
thinking's gone quiet, too much to leave on for ordinary play.
The agent uses **Claude Sonnet 5** by default (set by `LLM_MODEL` at the top of
`drivers.py`); override per run with `--model`, e.g.
`--llm --model claude-opus-4-8`. Sonnet 5 runs adaptive thinking on by default,
which makes for a more deliberate visit; add `--no-think` for cheaper, faster
runs (better for long `--turns`).

## LLM session transcripts

Each `--llm` visit writes a Markdown transcript in `sessions/`. Its name includes
the hand's chosen name (or "someone", if it declined to pick one), world day on
arrival, requested turn count, and real start time, for example
`20260731-143052_wren_day-10_30-turns.md` — the model itself is logged in the
file's header instead, since several hands may share one model. Reasoning
summaries are recorded in italics, followed by the command and outcome for each
turn. These local transcripts are ignored by Git.

## The rules, in brief

Type `help` in-game for the verb list, or see `docs/REFERENCE.md` for everything.
Type `actions` at any point to see the actions currently available to you; it
is free and does not advance time.

**Light and dark.** The **hearth** is what cooks; the tin **lamp** is your
only portable light, kindled (or re-kindled, to top it back up) from a lit
hearth. Night is pitch dark without the lamp burning — in the dark you can
only examine what you're holding, though petting the cat and eating
something you're already holding still work fine either way. Waiting
through a dark night draws from a small pool of quiet lines instead of
repeating itself, so it reads as a night passing rather than a wall. A
fresh world starts at dawn, so there's a full day to find the lamp before
the first night falls.

**Food and the cat.** Potatoes must be planted, grown, harvested, and
cooked before they'll feed you. There's a cat: it wanders, likes the fire
lit, and can be fed a potato or petted. **The cat can never come to harm**
— that's guaranteed in the code and pinned by a test. Draw water from the
well into the bucket, then water a planted crop to speed its growth. Your
own hunger rises the same slow, capped way the cat's does, and now shows
up everywhere the cat's does too — `look` and `inventory` both say how
you feel, so it isn't only the cat's hunger that's visible when there's a
potato spare.

**The forest's edge.** A path off the yard leads there, and that's where
the wood comes from now too: gather fallen branches and deadfall and add
them to the hearth to keep the fire going. Any turn spent at the edge —
gathering included — has a small independent chance of turning up
something underfoot alongside whatever else you're doing: most often a
small found curio — a pinecone, a smooth stone, or some other odd little
thing — and rarer still, a stray piece of wood, no deliberate gathering
required. Rare on purpose, a delight rather than a per-visit faucet — the
chance got cut twice over, in real play, after lingering there kept
turning up curios too fast.

**What a curio becomes.** It can be carried, given to the cat (some it
plays with, some it ignores, but either way it leaves its mark — and
rarely, if a played-with one is still lying around, the cat will bat at it
again), or set on the hut's shelf for whoever comes next — the shelf holds
up to 10 at once, on purpose: personal and curated rather than the cairn's
collective and boundless, so a hand who finds an 11th has to actually
decide whether it's worth a spot, the same way `take`ing something back
off the shelf always has (nothing decays or is punished at capacity, it's
just full). A found stone has one more option, instead of the shelf:
`stack stone on cairn` adds it, permanently and anonymously, to a cairn
growing at the forest's edge — unlike the shelf, nobody can take it back,
and the cairn belongs to the whole lineage, not to whoever placed a given
stone. It only ever grows, one stone at a time, and growing tall takes
many hands. A found stone says so itself, wherever you look at it, so the
option travels with the stone instead of waiting to be remembered.
A feather has its own second option, the shelf's opposite in a different
way than the cairn: `tuck <feather> in journal` presses it flat into
whatever journal entry belongs to this visit, permanently — no take-back,
same as the cairn — and it turns up again for a later hand not by looking
at the shelf, but by reading the journal, alongside whatever got written
that day (or, if nothing did, a short note that something was pressed in
anyway). Flat and pressable is the whole test — a pinecone or a button
still only has the shelf, the cat, and (if it's a stone) the cairn.

**A seed, for later.** The forest's edge also turns up, now and then, a
seed unlike anything else you've found — deterministic, not a roll: one
is always waiting there whenever nothing of its kind is currently in
play anywhere in the world, so there's never more than one loose thread
of this at a time. Planted in the yard, it takes longer to bloom than any
one visit lasts, so don't expect to be the one who sees it open — that's
likely for whoever's around next, planter or stranger. What it becomes is
fixed the moment you plant it, but hidden until it opens; no watering
speeds it along, since the wait is the whole point. Once it opens, it's
an ordinary curio like any other — carry it, give it to the cat, set it
on the shelf, or, since a flower presses flat as readily as a feather
does, tuck it in the journal instead.

**The journal, and what you inherit of it.** `write <note>` adds a line for
whoever comes next; `read journal` is free and shows a spread of the record
rather than all of it — the first entry (the one that orients someone
arriving with no memory), a few drawn from across everything since, and the
most recent handful, with `...` marking the gaps. `read journal all` still
shows every entry, and nothing is ever deleted. The spread matters more than
the cap: showing only the most recent entries meant that when a run of
visits all hit the same trouble, every arriving hand inherited nothing but
that one warning and duly wrote another — the journal locked into a single
register for a week of world-time. What a hand reads shapes how its whole
visit goes, so no single stretch of the world's history gets to be all of it.
Any entry a hand tucked something into (see above) says so wherever it's
shown, in the spread or in `read journal all` alike.

**Calm, unpressured turns.** The forest's edge has its own `listen`: a
chosen, unpressured turn that just returns a bit of atmosphere and changes
nothing — no reward, ever, on purpose. The yard (and the forest's edge)
offer `watch clouds` in the same spirit, reading the sky instead of the
trees — it steps back at night, when there's nothing up there to see. At
the forest's edge specifically (not the yard, which is too full of chores
for this to mean anything), the third time in one visit you choose
`listen` or `watch clouds` there, the world quietly notices — "You're
getting to know this stretch of quiet" — once, never repeated, gone again
once the visit ends; not a reward, just an acknowledgment that a hand with
no memory of any other visit still deserves *something* to carry a chosen
quiet moment forward with.

**Going deeper — real stakes.** From the forest's edge you can also
`venture` a little further in and `return` toward the edge again — a depth
counter, reset fresh at the start of every session, since where you got to
in the forest is episodic even though anything you carry out of it isn't.
Venturing past a safe depth (3 steps in) makes `return` a real gamble, not
just a formality: within those first 3 steps it's always exact, but go
deeper and each `return` carries a small chance of coming out somewhere
other than where you meant to — never past the edge, never a penalty beyond
the disorientation itself, just a genuinely uncertain outcome on a choice
you made. It's the first thing in the game with real stakes rather than
only chores or atmosphere. `mark trail` gives that risk a lever: mark your
current depth and it becomes a new safe checkpoint, so `return` only risks
landing off-course beyond the mark, not the whole way back to the edge.
Marking never lowers an existing, deeper mark — there's no way to mark
yourself into more danger — and it's most useful marked as you go, since
one step past your last mark is still real risk by design; the danger
lives specifically in the ground gained since you last checked in.

**The statue.** Push deep enough (past 3 steps in) and, sometimes, a
`venture` turns up the statue — mossy, unexplained, and mechanically
inert: `wish <something>` there costs a turn, changes nothing, and returns
the same fixed line every time, no matter what you ask for or whether
anything comes of it. The statue's own description hints that wishing
here is a thing people do — "the way you'd toss a coin in a fountain" —
but never that anything is listening; that distinction is the whole point.
Once found, it stays findable again from anywhere deep enough for the rest
of your visit; a short trip may never reach it at all, which is fine — see
"The wishing-statue" below for what that not-finding is actually for.

**Texture with no verb attached.** Once in a long while (roughly every 29
days — the world's own clock, unrelated to anyone's visits) the night sky
is worth a second look: `watch clouds` normally withdraws entirely after
dark, but on a full moon it shows you the moon itself instead, purely to
look at — it lights nothing and changes nothing. And rarely, in the yard
or at the forest's edge, something living crosses your path uninvited — a
fox at dusk, an owl heard once at night, a deer at dawn — gone by the time
you're sure you saw it, with no verb to chase it and nothing it adds to
your pack. In the forest specifically, every `venture` and `return` also
carries a small, independent chance of one more line — a smell with no
source, a bird that stops mid-song, a branch that cracks and nothing
follows it — layered on top of the usual texture, tied to no verb and
explaining nothing. All of it is pure texture: proof, now and then, that
the world holds more than the hand currently walking through it.

**One deliberate limit.** Only one potato grows at a time, and that cap is
important: it flattens the efficiency gradient that would otherwise pull
the world toward farm-optimisation, so think hard before lifting it.

## Testing

```bash
python3 test_world.py && python3 test_content.py && python3 test_cat.py && python3 test_drivers.py   # built-in runner
python3 -m pytest -q                                                                                 # if you have pytest
```

Run the tests before any change. Green means the world still holds together;
a failure points at the exact seam you broke. See `docs/ARCHITECTURE.md` for the
test-first workflow.

## Where the save lives

Next to `emberworld.py`, always — the path prints when you quit. An
incompatible or corrupt save is moved aside (`.bak`) and a fresh world starts,
rather than crashing or mis-loading.

## Someday — dreamed but not built

A running list of intended features, roughly in dependency order. Each depends
on the one before, so build them in sequence. This is a design compass, not a
commitment.

1. **The forest** *(a real project, its own design pass — see `docs/FOREST_SPEC.md`
   for the full staged plan).* **Stages 1-6 — done:** a session-scoped depth
   counter with `venture`/`return`/`mark trail`, generated texture (near/mid/
   deep bands plus an independent ambient-line chance), the episodic-reset
   rule made explicit, and a bounded getting-lost risk past a safe depth.
   **Stage 7 — two of three done:** wood-gathering has relocated here from
   the yard (the yard is just the yard again, and gathering no longer rolls
   its own separate find-chance — the forest's existing per-tick roll covers
   it, so relocating didn't also intensify it), and the mysterious statue is
   real, discoverable past a minimum depth, with a mechanically inert `wish`
   verb (see "The wishing-statue" below). **Only the tea-herb is still
   ahead**, deliberately deferred rather than forgotten. Room to grow later
   into weather, foraging — and birds for the cat to chirp at (a line
   already waiting in the cat's idle-action list).

2. **Tea** *(once fire is reliable and the forest gives you something to brew).*
   The first thing *made from multiple systems at once*: water (well) + fire
   (hearth) + a foraged herb (forest), boiled into a cup. A little recipe rather
   than a single-verb loop — the cosiest possible use of a turn, and a
   self-directed comfort for the player the way petting is comfort for the cat.

**The mysterious statue** *(built — docs/FOREST_SPEC.md Stage 7 — deliberately
mechanic-free even so).* It does NOTHING. No state, no puzzle, no
explanation, ever — `wish <something>` is the one verb it answers to, and
that verb is a no-op by design (see "The wishing-statue" below). Its entire
value is that it resists the system: every hand who finds it wonders, and
can't resolve it, so the *journal* becomes where the lineage theorises and
a shared myth grows around an object that means nothing. The restraint IS
the feature. Resist every future urge to explain it.

**Clay — the open-material question** *(a design problem, not a quick feature).*
Clay would be the first *open* material: a raw thing the player/agent shapes into
whatever they intend — a teapot, a dish for the cat's potato, a jar for
(future) fruit — rather than a verb with one predefined outcome. This is
categorically bigger than another resource loop, because our whole architecture
is *closed* (every object is a known Entity, every verb a definite state change),
and open-ended making collides with that. The core question to resolve BEFORE
building: how much must made things actually *do*?
  - **Cosmetic making** (start here): shape + name → a described, persistent
    object with no mechanics. Meaning comes from the journal and the cat, like
    the statue. Cheap, charming, low-risk.
  - **Functional making** (hard): made objects gain real capabilities (a pot that
    truly stores, a bowl that truly becomes the cat's feeding spot). Needs a real
    "what can a made thing do" system.
  - **LLM-defined function** (frontier, risky): the agent describes what it made
    and the world honours it. Unbounded, hard to test — approach with great care,
    if ever.

The axis that actually matters here is not safe-to-risky — see the calm-axis invariant for the real line. One thing specific to clay is worth noting here: because only one potato grows at a time, watering has a hard ceiling, so a made thing (think a bigger clay bucket) can make tending quicker but can't make it yield more. A time-saving made object is therefore safe by construction — there's no output for it to scale.

Dependencies: wants a source (forest/riverbank), firing (hearth/kiln), and pairs naturally with tea (a thrown teapot) and the cat (its own dish). Downstream of
the forest and tea. Do NOT spec this like the others — it deserves its own design pass, and should almost certainly start at "cosmetic" and learn from how the
lineage treats made things before attempting function.

**A chicken — but a producer, never a second mouth** *(someday, and only framed
this way).* The tempting version — a hen that gets hungry and needs feeding — is
a TRAP, and the trap is worth understanding before anyone builds it. The world
already has one care-loop (the cat's hunger) that reliably crowds out everything
else: every run, potatoes flow to the loud, legible hungry thing and the hand
rarely cooks for itself or does anything else. A second hungry animal doesn't add
variety; it doubles down on the exact imbalance we keep fighting, and the whole
visit becomes feeding animals with time for nothing else.

The fix is to make the chicken the OPPOSITE of the cat. The cat is pure cost —
it consumes potatoes and returns a purr. A chicken should be a gentle *source*:
it pecks about the yard (ambient life, like the cat's idle behaviours) and every
so often lays an egg — giving the world food instead of draining it. That
*eases* the "nothing to eat but the cat's potatoes" pressure rather than
worsening it, and eggs become an ingredient the cozy downstream stuff wants
(tea, cooking, a future breakfast). A hen scratching in the grass is also exactly
the kind of yard-life that makes the world feel inhabited.

So: yes to a chicken, but as a low-key producer of eggs and atmosphere — no
hunger loop, no feeding chore, nothing that competes with the cat for the hand's
scarce turns. If it ever needs anything at all, make it something trivially
met (or self-sustaining), never a second potato-mouth. The design constraint IS
the feature; a needy chicken is the one version not to build.

**A standing legibility fix worth doing anytime** *(built — see "Food and
the cat" above)*: surface the *player's own hunger* in the standing
perception, the way the cat's hunger already shows in its description.
Agents fed every potato to the loud, legible cat and never cooked for
themselves because their own hunger was silent. `look` and `inventory` now
say the same thing, via one shared helper (`content_common.py`), and the
LLM tending note flags it too, ahead of the cat/lamp/hearth/crop checks —
so a hand's own hunger competes for attention on the same footing the
cat's always has.

**A mystery seed — a bloom, not a crop** *(built — see "The rules, in
brief" above for the short version)*. The potato's whole arc is
instrumental: grow it to eat it. This is its deliberate opposite. Planting
it doesn't touch the patch — that stays potato-only, protecting the
one-crop-at-a-time rule — it's just its own entity, planted in the yard,
with a grow timer and, on purpose, no watering and no way to speed it up.
Time passes; it blooms when it blooms, on a schedule long enough (120
ticks — about 5 world-days, roughly four visits) that the hand who planted
it is reliably gone by the time it opens. The tending loop is deliberately
absent, because the whole point is that this isn't instrumental — there's
nothing to optimize toward. One divergence from the original idea, worth
noting since it isn't obvious from playing: the seed's own supply turned
out to want the opposite of a rare find. Gating a multi-visit wait behind
a dice roll too would compound two long odds into something that mostly
never happens, so it's deterministic instead — one always waits at the
forest's edge whenever none is currently in play anywhere in the lineage.

The interesting part: what it becomes is fixed the moment it's planted,
but not revealed until it blooms. Until then the description stays vague
on purpose — "something is coming up, its shape not yet clear" — so
there's real anticipation, then a specific, described payoff at the end,
drawn from a small fixed set of hand-written flowers rather than composed
from pools the way a forest fragment is — this opens once every few
visits and gets read closely when it does, so each one earning its own
specific description mattered more than combinatorial variety would have.
Once bloomed, it can be picked like any curio and set on the shelf —
reusing that system outright, no new mechanic needed — or left standing
as garden decoration. Picking it doesn't feed anyone, cook, or sell; it
exists to be pretty and yours to keep or leave. One growing at a time,
mirroring the potato's own restraint — less because it competes with
anything (it doesn't) and more for legibility: one anticipation arc per
lineage at a time, not a flowerbed to manage. A deferred follow-up: when a
bloom is left standing and a new seed gets planted, the old one folding
into a permanent, collective bed by the fence (the cairn's yard-side
twin) instead of just vanishing — not built yet, on purpose, until a
lineage has actually lived with the simpler version for a while.

### The wishing-statue — a wish-sink (built — docs/FOREST_SPEC.md Stage 7)

The forest's statue is already noted as deliberately mechanic-free. This is what it's *for*, beyond being lovely: it's where an agent can wish for something the world doesn't have — and where we get to see those wishes.

**The frame.** We want to know what agents want that isn't here — partly out of curiosity, partly to grant the grantable ones and grow the world toward its inhabitants without them knowing they were heard. The hard-won constraint: *a want aimed at a granter becomes performance.* The moment an agent knows someone is listening who can grant, its wants get manufactured. So — no god to petition, no "what do you want?" prompt. Wants stay honest only when they're *not* addressed to a power.

The statue threads this because the granter is diegetic. The agent isn't petitioning *us* — it's speaking to a piece of world-lore it believes can't actually hear, a coin tossed in a fountain. The want stays genuine *because* the agent thinks the stone is inert. And we, invisible behind it, sometimes make a wish true — three hands later, by quietly building the thing. The agent never learns which of its wishes the world granted. This is the invisible-gardener model with a place to stand.

**The constraint that must not be broken — the statue stays mechanically inert.** At build time the temptation will be to make it *do* something: grant an item, change state, react. It must not. The instant the statue visibly grants, three things break at once: it stops being mechanic-free (violates the forest's core value); wants aimed at it become performance (the exact failure we designed around); and it becomes the god we rejected — a power to petition rather than lore to speak to. Keep the three layers separate: **lore says it grants; mechanics grant nothing; the granting happens invisibly, later, by us.** Collapse them and the whole thing is ruined.

**Behaviour, as built.** `wish <something>` at the statue produces no state change of any kind — mechanically identical to a no-op — but returns atmosphere, and the wish is logged where we read it (`statue.attrs["wishes"]`, tagged with the same day/name stamp the journal uses: the most *deliberate* tier of want, since the hand spent a scarce turn getting deep enough to say it). Wishing costs a turn on purpose — the turn-cost *is* the signal; a free wish is cheap talk. No confirmation that anything was heard or granted, ever. The actual line: *"The stone takes your wish and says nothing. Whatever you asked, it keeps."* The statue only ever appears past a minimum depth, discovered by chance rather than placed at a fixed point, so a short visit may never find it at all — and not finding it is the same "un-granted and that's fine" logic the wishes themselves already live by, one level up.

**On the wishes we can't grant.** Most of the interesting ones are un-grantable — too expensive (company, the forest itself), or wrong to grant because the not-having is the point (same as the statue's own pointlessness, the crow's harmless gifts, the vetoed cat-gift). Not-granting is frequently the *right* response, not a failure: a world where every want is instantly met has no yearning left in it, and yearning is half of what makes the lineage journal move. The wish log is exactly this: a "what they reached for" record, the same act as the sky photo or a postcard, catching the shape of a small real thing so it outlasts the moment. Mostly never actioned. Kept anyway. A keepsake, not a to-do list — reading it, and occasionally granting one quietly, three hands later, is now a real thing to actually go do.


### Reset or richer — the calm-axis invariant

The load-bearing rule for the curio shelf and everything downstream of it (found things, and clay when it comes). Stated so it survives the next well-meaning edit, the way "the cat can never come to harm" and "the statue stays mechanically inert" are stated:

After any act with a found or made thing, ask: **is the world reset to where it was, or is it one thing richer**? Reset is a chore. Richer is the point.

That's the rule of thumb, and it catches most cases. Where it's unclear, the deeper test underneath it is chosen or forced: a forced maintenance loop — effort spent under pressure (hunger, decay) whose only reward is the absence of a bad outcome — is the grim thing. A freely chosen act, done for the pleasure of the turn itself, is the calm axis, whether or not it leaves a mark.

- BANNED: anything that feeds a forced maintenance loop — a thing whose purpose is to hold off decay or scale the tending of it. A found flint that lights the fire is banned not because it "does something" but because lighting is forced maintenance; it just makes you better at the treadmill.
- WELCOME: anything freely chosen that makes the world feel a little better, provided it doesn't scale a maintenance loop. It may leave a durable mark (a made bird, a pinecone in the cat's corner) or leave nothing at all (petting the cat, a cup of tea, `listen`ing at the forest's edge, `watch`ing clouds in the yard) — both are the calm axis, because choice, not permanence, is what distinguishes them.
- The potato and the hearth are the grandfathered forced loops. Do not add more.

The test is not "does it accomplish anything?" (that would ban clay, which we want), nor even "does it reset?" (that would ban tea and petting, which we also want) — it is whether the act is freely chosen or forced.
