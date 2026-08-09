# Emberworld -- Reference

*Generated from the code by `python3 emberworld.py --reference`. Don't edit by hand -- regenerate it.*

## Verbs

- `feed` -- feed cat -- give a carried potato to the cat (a raw one, if you have a choice -- cooked food is for you); "feed hearth" is an alias for "add wood" (two hands independently reached for it).
- `pet` / `stroke` -- pet cat -- pet the cat. Accomplishes nothing; is the entire point.
- `name` -- name cat <name> -- name the cat; the name is kept for every future visit.
- `look` / `l` / `examine` / `x` -- look [thing] -- describe the room, or examine one thing (dark hides all but what you hold); "look actions" works the same as "actions".  _(free -- costs no time)_
- `go` / `move` -- go <exit> -- move through a named exit (you can also just type the exit name; "inside" works anywhere "in" does).
- `take` / `get` / `grab` -- take <thing> -- pick up a portable object.
- `drop` -- drop <thing> -- set down something you're carrying.
- `inventory` / `i` -- inventory -- list what you're carrying and how hungry you feel.  _(free -- costs no time)_
- `actions` -- actions -- list the things you can do from here right now.  _(free -- costs no time)_
- `wait` / `z` -- wait -- let one tick pass while you do nothing.
- `light` / `kindle` -- light <thing> -- set a fuel source burning (the hearth cooks); light lamp / kindle lamp lights the tin lamp from a lit hearth.
- `snuff` -- snuff <thing> -- put out a lit flame.
- `plant` -- plant <potato|seed> -- press a raw potato into the vegetable patch, or set the seed you found in the ground by the fence.
- `harvest` -- harvest -- lift a ripened crop from the patch for its potatoes.
- `cook` / `broil` -- cook potato -- broil a potato at a lit cooking fire, making it edible.
- `eat` -- eat <thing> -- eat cooked food to ease your hunger.
- `write` -- write <note> -- add a line to the shared journal for future visitors.
- `read` -- read journal -- read the journal (needs light unless you're holding it); shows a spread of entries rather than all of them, and `read journal all` shows the lot; anything tucked into a shown entry (see `tuck`) is named alongside it.  _(free -- costs no time)_
- `save` -- save -- write the world to disk (also happens automatically on quit).  _(free -- costs no time)_
- `tuck` -- tuck <thing> in journal -- press a flat curio (a feather, or the mystery seed's bloom) into this visit's journal entry; permanent, like a stone on the cairn.
- `draw` -- draw water -- fill the bucket from the well (holds up to its capacity).
- `water` -- water crop -- pour a bucket's stored water onto the planted crop here.
- `place` / `put` -- place <thing> [on shelf] -- set a carried object on the hut's curio shelf (holds up to 10 at once); "put wood in hearth" is an alias for "add wood" (two hands independently reached for it).
- `gather` -- gather wood -- forage the forest's edge for fallen branches and deadfall.
- `give` -- give <thing> to cat -- hand a carried curio to the cat; it plays with some and ignores others, but the gesture always leaves its mark.
- `listen` -- listen -- stop and take in the forest's edge; a chosen, unpressured turn that changes nothing (only at the forest's edge).
- `watch` -- watch clouds -- pause under open sky and watch the clouds (or, on a full or near-full moon night, the moon itself) move; a chosen, unpressured turn that changes nothing.
- `venture` -- venture -- push a little further into the forest, past the edge.
- `return` -- return -- fall back toward the forest's edge from wherever you've ventured (past a safe depth, this can land you somewhere other than expected).
- `mark` -- mark trail -- mark your current depth in the forest as a safe checkpoint, so return only risks landing off-course beyond this point, not the whole way back.
- `wish` -- wish <something> -- speak a wish to the statue, deep in the forest; it changes nothing and confirms nothing, ever.
- `add` / `stoke` -- add wood -- feed carried firewood into the hearth, raising its fuel (offered even with none carried, so the refusal teaches where it comes from).
- `stack` -- stack stone [on cairn] -- add a carried stone to the cairn at the forest's edge, permanently; it's no longer yours once it joins the pile.

## Autonomous behaviors
*These run on their own every tick, whether or not you act.*

- **cat_wander** -- Autonomous: the cat drifts between the hut and the yard, drawn toward a lit hearth.
- **cat_hunger** -- Autonomous: the cat slowly gets hungry (capped, never harmed), shows it in its own description once hungry, and occasionally meows to be fed.
- **cat_idle** -- Autonomous: a content, well-fed cat occasionally does a small idle cat-thing -- purely cosmetic ambient life, never while it's hungry.
- **cat_replay** -- Autonomous: rarely, if something the cat has already played with (a curio previously given away, see cmd_give's "plays" reaction) is lying in its current room, the cat bats at it again.
- **burning** -- Autonomous: a lit fuel source (the hearth) burns down and goes out.
- **growing** -- Autonomous: a planted crop ages each tick and eventually ripens -- twice as fast on any tick it spends a unit of stored water.
- **patch_state** -- Autonomous: the vegetable patch describes itself by what's growing in it, including whether it was just watered.
- **patch_volunteer** -- Autonomous: if the patch stays continuously empty for PATCH_VOLUNTEER_TURNS turns, one volunteer potato plant sprouts on its own -- deterministic, self-healing ground so a lineage can never be permanently seedless.
- **bucket_state** -- Autonomous: the bucket describes itself by how much water it's holding.
- **hearth_state** -- Autonomous: the hearth's description bands by fuel level whether lit or not -- a cold hearth used to say nothing about how much fuel it was holding, so a hand couldn't tell "unlit but stocked" from "unlit and empty" without trying to light it and failing.
- **hungering** -- Autonomous: the actor slowly gets hungrier over time (capped, harmless).
- **lamp_burning** -- Autonomous: a lit tin lamp burns down one fuel per tick, wherever it is -- carried or set down -- warning inline as it runs low and again when it finally goes dark.
- **forest_finds** -- Autonomous: while a hand lingers at the forest's edge (arriving, or spending any later turn there -- venture/return included, since neither verb actually moves `actor.location` off this room), each turn has a small chance of turning up something underfoot: usually a curio, and a slice of that same chance a stray piece of wood instead, no `gather wood` required.
- **wildlife_glimpse** -- Autonomous: while a hand is present, a small independent chance per tick of glimpsing something living and entirely unrelated to whatever the hand is doing -- see WILDLIFE_LINES/WILDLIFE_CHANCE above.
- **seedfall** -- Autonomous: while nothing of the seed's arc is in play anywhere in the world -- no seed carried, shelved, or lying about, and no mystery plant growing or bloomed in the yard -- the forest's edge offers one to the next hand who stands here.
- **blooming** -- Autonomous: a planted seed comes up on its own schedule and eventually opens.

## World rules (from the code's own constants)

- A full day is **24 ticks**; night falls late in that cycle and is pitch dark without a lit flame. A fresh world starts at dawn, giving a full day's light before the first night falls.
- The moon is a real clock, independent of anyone's visits: **7** nights out of every **29** show something at night instead of nothing (full, or near enough), offset so a fresh lineage reaches one within its first week rather than its first month.
- The tin lamp is the only portable light, kindled from a lit hearth; the **hearth** is what cooks.
- The lamp holds **32** fuel once kindled and warns when it drops to **8**; it can be re-kindled at any lit hearth, which tops it back to full.
- The cat's hunger is capped at **24** and it can come to no harm -- it only ever wants feeding.
- Your own hunger is capped at **40** and comes to no harm either -- but unlike the cat's, it says nothing on its own until you `look` or check `inventory`. Both surface the same mood, from "stuffed" up to "ravenous" at **32**.
- The cat stays content (and may do small idle things) below hunger **24**; at or above it, it starts meowing to be fed.
- A full bucket holds **5** units of water; each unit spent doubles a crop's growth for that one tick.
- Gathering wood yields **3**; feeding one unit into the hearth restores **60** fuel -- a full night's burn, and enough to revive a spent hearth.
- A found curio turns up **8%** of the time on any turn spent at the forest's edge (gathering wood included) -- a delight, never a guarantee.
- If the vegetable patch stays empty for **30** turns straight, one volunteer potato plant sprouts on its own -- a floor against a seedless lineage, not a routine source.
- The hut's curio shelf holds up to **10** things at once -- personal and curated, unlike the forest-edge cairn, which is collective and never full.
- A found seed turns up at the forest's edge whenever none is in play (carried, shelved, or growing) -- deterministic, not a roll. Planted in the yard, it takes **120 ticks** (longer than any one visit) to bloom into one of a handful of flowers, fixed the moment it's planted but hidden until it opens -- and water never speeds it up.
- The world saves to disk (save format v2); an incompatible save is set aside, never mis-loaded.
- Free verbs don't advance time; everything else ticks the world forward once.

