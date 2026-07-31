# Emberworld

A small text world that keeps ticking whether or not anyone's watching — a
candle burns down, a potato grows, night falls, a cat wanders and gets hungry.
You can play it yourself, or let a Claude reach in over the API and live in it
for a while. Because the world saves to disk, visits form a lineage: one hand
plants a potato and leaves a note; a later hand — with no memory of the first —
reads that note and harvests the crop.

## Files

- `emberworld.py` — the whole game (engine, world, drivers). One file, no
  dependencies to play.
- `test_emberworld.py` — the safety net. Runs with or without pytest.
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
`emberworld.py`); override per run with `--model`, e.g.
`--llm --model claude-opus-4-8`. Sonnet 5 runs adaptive thinking on by default,
which makes for a more deliberate visit; add `--no-think` for cheaper, faster
runs (better for long `--turns`).

## The rules, in brief

Type `help` in-game for the verb list, or see `REFERENCE.md` for everything.
The essentials: the candle only gives **light**; the **hearth** is what cooks.
Night is pitch dark without a lit flame — in the dark you can only examine what
you're holding. Potatoes must be planted, grown, harvested, and cooked before
they'll feed you. There's a cat: it wanders, likes the fire lit, and can be fed
a potato or petted. **The cat can never come to harm** — that's guaranteed in
the code and pinned by a test.

## Testing

```bash
python3 test_emberworld.py       # built-in runner, no dependencies
python3 -m pytest -q             # if you have pytest
```

Run the tests before any change. Green means the world still holds together;
a failure points at the exact seam you broke. See `ARCHITECTURE.md` for the
test-first workflow.

## Where the save lives

Next to `emberworld.py`, always — the path prints when you quit. An
incompatible or corrupt save is moved aside (`.bak`) and a fresh world starts,
rather than crashing or mis-loading.
