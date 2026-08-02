# Emberworld -- Reference

*Generated from the code by `python3 emberworld.py --reference`. Don't edit by hand -- regenerate it.*

## Verbs

- `feed` -- feed cat -- give a carried potato to the cat (a raw one, if you have a choice -- cooked food is for you).
- `pet` / `stroke` -- pet cat -- pet the cat. Accomplishes nothing; is the entire point.
- `name` -- name cat <name> -- name the cat; the name is kept for every future visit.
- `look` / `l` / `examine` / `x` -- look [thing] -- describe the room, or examine one thing (dark hides all but what you hold).  _(free -- costs no time)_
- `go` / `move` -- go <exit> -- move through a named exit (you can also just type the exit name).
- `take` / `get` / `grab` -- take <thing> -- pick up a portable object.
- `drop` -- drop <thing> -- set down something you're carrying.
- `inventory` / `i` -- inventory -- list what you're carrying and how hungry you feel.  _(free -- costs no time)_
- `wait` / `z` -- wait -- let one tick pass while you do nothing.
- `light` -- light <thing> -- set a fuel source burning (the candle lights; the hearth cooks).
- `snuff` -- snuff <thing> -- put out a lit flame.
- `plant` -- plant potato -- press a raw potato into the vegetable patch to grow it.
- `harvest` -- harvest -- lift a ripened crop from the patch for its potatoes.
- `cook` / `broil` -- cook potato -- broil a potato at a lit cooking fire, making it edible.
- `eat` -- eat <thing> -- eat cooked food to ease your hunger.
- `write` -- write <note> -- add a line to the shared journal for future visitors.
- `read` -- read journal -- read the journal (needs light unless you're holding it).  _(free -- costs no time)_
- `save` -- save -- write the world to disk (also happens automatically on quit).  _(free -- costs no time)_
- `draw` -- draw water -- fill the bucket from the well (holds up to its capacity).
- `water` -- water crop -- pour a bucket's stored water onto the planted crop here.
- `gather` -- gather wood -- forage the yard's long grass and fallen branches for firewood (and, sometimes, something else).
- `add` / `stoke` -- add wood -- feed carried firewood into the hearth, raising its fuel.

## Autonomous behaviors
*These run on their own every tick, whether or not you act.*

- **cat_wander** -- Autonomous: the cat drifts between rooms, drawn toward a lit hearth.
- **cat_hunger** -- Autonomous: the cat slowly gets hungry (capped, never harmed), shows it
- **cat_idle** -- Autonomous: a content, well-fed cat occasionally does a small idle
- **burning** -- Autonomous: a lit fuel source (candle, hearth) burns down and goes out.
- **growing** -- Autonomous: a planted crop ages each tick and eventually ripens -- twice
- **patch_state** -- Autonomous: the vegetable patch describes itself by what's growing in
- **bucket_state** -- Autonomous: the bucket describes itself by how much water it's holding.
- **hearth_state** -- Autonomous: while lit, the hearth's description shows whether it's
- **hungering** -- Autonomous: the actor slowly gets hungrier over time (capped, harmless).

## World rules (from the code's own constants)

- A full day is **24 ticks**; night falls late in that cycle and is pitch dark without a lit flame.
- The candle only gives light; the **hearth** is what cooks.
- The cat's hunger is capped at **12** and it can come to no harm -- it only ever wants feeding.
- The cat stays content (and may do small idle things) below hunger **12**; at or above it, it starts meowing to be fed.
- A full bucket holds **5** units of water; each unit spent doubles a crop's growth for that one tick.
- Gathering wood yields **3**; feeding one unit into the hearth restores **40** fuel -- a full night's burn, and enough to revive a spent hearth.
- The world saves to disk (save format v2); an incompatible save is set aside, never mis-loaded.
- Free verbs don't advance time; everything else ticks the world forward once.

