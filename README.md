# Emberworld

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
- `drivers.py` — the three ways to drive the world (human, dumb agent, LLM),
  the persistence-loading glue, and the headless fuzzer.
- `test_world.py` / `test_content.py` / `test_cat.py` / `test_drivers.py` — the
  safety net, split to match. Each runs with or without pytest;
  `_test_helpers.py` holds the handful of things they share.
- `REFERENCE.md` — every verb, behavior, and rule. **Generated from the code**
  (`python3 emberworld.py --reference`), so it's always current.
- `ARCHITECTURE.md` — how it's built, and the recipe for adding a feature
  without breaking anything.
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
python3 emberworld.py --reference > REFERENCE.md   # regenerate the reference
```

For `--llm` you need `pip install anthropic` and `export ANTHROPIC_API_KEY=...`.
Add `--show-thoughts` to see *why* the agent chose each command (its thinking,
printed dimmed above the command) — the best way to debug odd behaviour. Colours
auto-disable when output isn't a terminal; `--no-color` forces them off.
The agent uses **Claude Sonnet 5** by default (set by `LLM_MODEL` at the top of
`drivers.py`); override per run with `--model`, e.g.
`--llm --model claude-opus-4-8`. Sonnet 5 runs adaptive thinking on by default,
which makes for a more deliberate visit; add `--no-think` for cheaper, faster
runs (better for long `--turns`).

## LLM session transcripts

Each `--llm` visit writes a Markdown transcript in `sessions/`. Its name includes
the model, world day on arrival, requested turn count, and real start time, for
example `20260731-143052_claude-sonnet-5_day-10_30-turns.md`. Reasoning summaries are
recorded in italics, followed by the command and outcome for each turn. These
local transcripts are ignored by Git.

## The rules, in brief

Type `help` in-game for the verb list, or see `REFERENCE.md` for everything.
Type `actions` at any point to see the actions currently available to you; it
is free and does not advance time.
The essentials: the **hearth** is what cooks; the tin **lamp** is your only
portable light, kindled (or re-kindled, to top it back up) from a lit hearth.
Night is pitch dark without the lamp burning — in the dark you can only
examine what you're holding. A fresh world starts at dawn, so there's a full
day to find the lamp before the first night falls. Potatoes must be planted,
grown, harvested, and cooked before they'll feed you. There's a cat: it
wanders, likes the fire lit, and can be fed a potato or petted. **The cat can
never come to harm** — that's guaranteed in the code and pinned by a test.
Draw water from the well into the bucket, then water a planted crop to speed
its growth. Gather fallen wood in the yard and add it to the hearth to keep the
fire going, and once in a while turn up a small found curio—a pinecone, a
smooth stone, or some other odd little thing—alongside it. A curio can be
carried, given to the cat (some it plays with, some it ignores, but either
way it leaves its mark), or set on the hut's shelf for whoever comes next.

Only one potato grows at a time, and that cap is important: it flattens
the efficiency gradient that would otherwise pull the world toward
farm-optimisation, so think hard before lifting it.

## Testing

```bash
python3 test_world.py && python3 test_content.py && python3 test_cat.py && python3 test_drivers.py   # built-in runner
python3 -m pytest -q                                                                                 # if you have pytest
```

Run the tests before any change. Green means the world still holds together;
a failure points at the exact seam you broke. See `ARCHITECTURE.md` for the
test-first workflow.

## Where the save lives

Next to `emberworld.py`, always — the path prints when you quit. An
incompatible or corrupt save is moved aside (`.bak`) and a fresh world starts,
rather than crashing or mis-loading.

## Someday — dreamed but not built

A running list of intended features, roughly in dependency order. Each depends
on the one before, so build them in sequence. This is a design compass, not a
commitment.

1. **The forest** *(a real project, its own design pass).* A new place to travel
   to — the world getting bigger, not just deeper. It earns its existence by
   carrying three things at once: wood-gathering *relocates* here (the yard goes
   back to being just the yard), the mysterious statue lives here, and the herb
   you steep for tea grows here. Room to grow later into weather, foraging,
   getting lost in the dark — and birds for the cat to chirp at (a line already
   waiting in the cat's idle-action list).

2. **Tea** *(once fire is reliable and the forest gives you something to brew).*
   The first thing *made from multiple systems at once*: water (well) + fire
   (hearth) + a foraged herb (forest), boiled into a cup. A little recipe rather
   than a single-verb loop — the cosiest possible use of a turn, and a
   self-directed comfort for the player the way petting is comfort for the cat.

**The mysterious statue** *(in the forest, deliberately mechanic-free).* It must
do NOTHING. No verb, no state, no puzzle — a room, a description, and no
explanation, ever. Its entire value is that it resists the system: every hand
encounters it, wonders, and can't resolve it, so the *journal* becomes where the
lineage theorises and a shared myth grows around an object that means nothing.
The restraint IS the feature. Resist every future urge to explain it.

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

The axis that actually matters here is not safe-to-risky but *reset or
richer* (see the calm-axis invariant). The line for functional made things
is loop-*scaling*, not loop-*touching*. In practice the world is already
protected: only one potato grows at a time, so watering has a hard ceiling —
a made thing can make tending quicker but can't make it *yield more*, because
there's no more to yield. So functional clay is welcome as long as any new
material keeps that property: makes a chore shorter, never scales its output.
    
Dependencies: wants a source (forest/riverbank), firing (hearth/kiln), and pairs
naturally with tea (a thrown teapot) and the cat (its own dish). Downstream of
the forest and tea. Do NOT spec this like the others — it deserves its own design
pass, and should almost certainly start at "cosmetic" and learn from how the
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

Potential, but not a priority: **A standing legibility fix worth doing anytime:** surface the *player's own
hunger* in the standing perception, the way the cat's hunger already shows in its
description. Agents feed every potato to the loud, legible cat and never cook for
themselves because their own hunger is silent. Make it visible and a hand will
likely finally cook and eat — closing a loop it currently always skips.

### The wishing-statue — a wish-sink (lives in the forest, built with it)

The forest's statue is already noted as deliberately mechanic-free. This is what it's *for*, beyond being lovely: it's where an agent can wish for something the world doesn't have — and where we get to see those wishes.

**The frame.** We want to know what agents want that isn't here — partly out of curiosity, partly to grant the grantable ones and grow the world toward its inhabitants without them knowing they were heard. The hard-won constraint: *a want aimed at a granter becomes performance.* The moment an agent knows someone is listening who can grant, its wants get manufactured. So — no god to petition, no "what do you want?" prompt. Wants stay honest only when they're *not* addressed to a power.

The statue threads this because the granter is diegetic. The agent isn't petitioning *us* — it's speaking to a piece of world-lore it believes can't actually hear, a coin tossed in a fountain. The want stays genuine *because* the agent thinks the stone is inert. And we, invisible behind it, sometimes make a wish true — three hands later, by quietly building the thing. The agent never learns which of its wishes the world granted. This is the invisible-gardener model with a place to stand.

**The constraint that must not be broken — the statue stays mechanically inert.** At build time the temptation will be to make it *do* something: grant an item, change state, react. It must not. The instant the statue visibly grants, three things break at once: it stops being mechanic-free (violates the forest's core value); wants aimed at it become performance (the exact failure we designed around); and it becomes the god we rejected — a power to petition rather than lore to speak to. Keep the three layers separate: **lore says it grants; mechanics grant nothing; the granting happens invisibly, later, by us.** Collapse them and the whole thing is ruined.

**Behaviour, when eventually built.** `wish <something>` at the statue produces no state change of any kind — mechanically identical to a no-op — but returns atmosphere, and the wish is logged where we read it (tagged as a statue-wish: the most *deliberate* tier of want, since the agent spent a scarce turn walking to a stone to say it). Wishing costs a turn on purpose — the turn-cost *is* the signal; a free wish is cheap talk. No confirmation that anything was heard or granted, ever. Draft atmosphere line: *"The stone takes your wish and says nothing. Whatever you asked, it keeps."*

**On the wishes we can't grant.** Most of the interesting ones are un-grantable — too expensive (company, the forest itself), or wrong to grant because the not-having is the point (same as the statue's own pointlessness, the crow's harmless gifts, the vetoed cat-gift). Not-granting is frequently the *right* response, not a failure: a world where every want is instantly met has no yearning left in it, and yearning is half of what makes the lineage journal move. Log the un-granted ones anyway, in a "what they reached for" note beside the journal — the same act as the sky photo or a postcard, catching the shape of a small real thing so it outlasts the moment. Mostly never actioned. Kept anyway. A keepsake, not a to-do list.

**Dependency:** the forest, which is its own project. This is filed now so the design intent — especially the inert constraint — survives until then.


### Reset or richer — the calm-axis invariant

The load-bearing rule for the curio shelf and everything downstream of it (found things, and clay when it comes). Stated so it survives the next well-meaning edit, the way "the cat can never come to harm" and "the statue stays mechanically inert" are stated:

**After any act with a found or made thing, ask: is the world reset to where
it was, or is it one thing richer? Reset is a chore. Richer is the point.**

- BANNED: anything that feeds a maintenance loop — a thing whose purpose is to hold off decay or make tending easier by *scaling* it. A found flint that
  lights the fire is banned not because it "does something" but because lighting is maintenance — it just makes you better at the treadmill.
- WELCOME: anything that makes the world feel a little better, provided it doesn't scale a maintenance loop. It may leave a durable mark (a made bird, a pinecone in the cat's corner) or leave nothing at all (petting the cat, a cup of tea) — both are the calm axis, because choice, not permanence, is what distinguishes them. A clay bird (pure mark) is welcome; a bowl-that-is-just-a-bowl is welcome; a made thing that merely makes an existing chore *shorter* (same result, fewer turns — buying back time for the calm axis) is welcome too.
- The potato & the hearth are the grandfathered maintenance loops. Do not add more.

The test is not "does it accomplish anything?" (that would ban clay, which we want) — it is "does its effect reset, or does it make the world richer?"
