"""
cat.py -- the cat, as its own self-contained subsystem: its constants, its
autonomous behaviors (wandering, hunger, idle), its verbs (feed, pet, name),
and how it's added to a fresh world. Split out of content.py once it grew
into its own coherent slice -- see ARCHITECTURE.md's "Where to go next".

GENTLE GUARANTEE: the cat's hunger is capped and drives nothing but meowing
and wanting food. There is no starvation, no damage, no harm state it can
ever reach. This is enforced here and pinned by a test. Do not add harm.
"""

from world import Entity, VERBS, BEHAVIORS

CAT_HUNGER_CAP = 24       # doubled in the pacing rebalance -- loosened first,
                          # since it was the loudest, most legible turn-eater
                          # (see ARCHITECTURE.md's "Pacing rebalance" section)
CAT_MEOW_THRESHOLD = 24   # hunger level at which the cat starts complaining;
                          # meow, hungry-description, and idle content-gate
                          # all key off this one value so they stay in step


def _room_is_warm(world, room_id):
    return any(e.location == room_id and e.attrs.get("lit") and e.attrs.get("cooks")
               for e in world.entities.values())


def _cat_cap(cat):
    # for the start of a sentence: "Shadow ..." if named, else "The cat ..."
    return cat.attrs.get("given_name") or "The cat"


def _cat_description(cat):
    # hunger used to only surface as a meow that scrolls past -- fold it into
    # the cat's own description so it's visible in the room every turn.
    name = cat.attrs.get("given_name")
    hungry = cat.attrs.get("hunger", 0) >= CAT_MEOW_THRESHOLD
    if name:
        return (f"{name}, a small cat, pacing and hungry, watching you keenly"
                if hungry else
                f"{name}, a small cat, watching you with mild interest")
    return ("a small cat, pacing and hungry, watching you keenly"
            if hungry else
            "a small cat, watching you with mild interest, tail curled")


def _cat_go(world, cat, direction):
    """Move the cat one room, along the given exit direction ('in'/'out').
    The departure/arrival lines key off that direction rather than being
    hardcoded to always say 'out'/'in' -- otherwise a yard->hut move reads
    as the cat going 'out' when it's actually coming inside, and vice versa."""
    src = cat.location
    room = world.get(src)
    dest = room.exits.get(direction)
    if not dest:
        return
    cat.location = dest
    cap = _cat_cap(cat)
    if direction == "out":
        world.announce(f"{cap} slips out through the doorway.", src)
        world.announce(f"{cap} pads out into the yard, tail high.", dest)
    else:
        world.announce(f"{cap} slips in through the doorway.", src)
        world.announce(f"{cap} pads in, tail high.", dest)


def cat_wander(world, cat):
    """Autonomous: the cat drifts between the hut and the yard, drawn toward
    a lit hearth. Confined to the 'in'/'out' pair on purpose -- those are the
    only two directions _cat_go knows how to narrate (doorway/tail-high
    wording); a hand-only place like the forest's edge stays a hand-only
    place rather than getting the cat wandered into it with the wrong flavor
    text."""
    room = world.get(cat.location)
    directions = [d for d in room.exits if d in ("in", "out")] if room else []
    if not directions:
        return
    r = world.rng.random()
    warm_here = _room_is_warm(world, cat.location)
    warm_exits = [d for d in directions if _room_is_warm(world, room.exits[d])]
    if warm_here:
        if r < 0.10:                                   # cozy: rarely leaves warmth
            _cat_go(world, cat, world.rng.choice(directions))
    elif warm_exits:
        if r < 0.60:                                   # drawn toward a lit hearth
            _cat_go(world, cat, world.rng.choice(warm_exits))
    elif r < 0.25:                                     # otherwise idle drift
        _cat_go(world, cat, world.rng.choice(directions))


def cat_hunger(world, cat):
    """Autonomous: the cat slowly gets hungry (capped, never harmed), shows it
    in its own description once hungry, and occasionally meows to be fed."""
    # capped -- the cat gets peckish, never worse.
    cat.attrs["hunger"] = min(cat.attrs.get("hunger", 0) + 1, CAT_HUNGER_CAP)
    cat.description = _cat_description(cat)
    if cat.attrs["hunger"] >= CAT_MEOW_THRESHOLD and world.rng.random() < 0.35:
        world.announce(f"{_cat_cap(cat)} winds around your ankles, "
                       f"meowing to be fed.", cat.location)


CAT_IDLE_LINES = (
    "{cat} stretches long, then folds itself smaller.",
    "{cat} washes one paw with great seriousness.",
    "{cat}'s purr rumbles somewhere deep in its chest.",
    "{cat} blinks at you, slow and unbothered.",
    "{cat} curls its tail neatly around its feet.",
)


def cat_idle(world, cat):
    """Autonomous: a content, well-fed cat occasionally does a small idle
    cat-thing -- purely cosmetic ambient life, never while it's hungry."""
    if cat.attrs.get("hunger", 0) >= CAT_MEOW_THRESHOLD:
        return
    if world.rng.random() < 0.12:
        line = world.rng.choice(CAT_IDLE_LINES).format(cat=_cat_cap(cat))
        world.announce(line, cat.location)


BEHAVIORS.update({"cat_wander": cat_wander, "cat_hunger": cat_hunger,
                   "cat_idle": cat_idle})


def cmd_feed(world, actor, arg):
    """feed cat -- give a carried potato to the cat (a raw one, if you have a choice -- cooked food is for you)."""
    from content import _is_raw, _last_potato_beat   # deferred to dodge a cat<->content cycle
    cat = world.get("cat")
    if cat is None or cat.location != actor.location:
        return "There's no cat here to feed."
    potatoes = [e for e in world.contents(actor.id) if "potato" in e.name]
    food = next((e for e in potatoes if _is_raw(e)), potatoes[0] if potatoes else None)
    if not food:
        return "You've nothing to feed it just now -- a potato would do."
    was_raw = _is_raw(food)
    world.entities.pop(food.id, None)
    cat.attrs["hunger"] = 0
    return (f"The cat sets upon the {food.name}, eats every scrap, and purrs."
            + _last_potato_beat(world, actor, was_raw))


def cmd_pet(world, actor, arg):
    """pet cat -- pet the cat. Accomplishes nothing; is the entire point."""
    cat = world.get("cat")
    if cat is None or cat.location != actor.location:
        return "There's no cat here."
    return ("The cat leans into your hand and purrs. It accomplishes nothing, "
            "and is the entire point.")


def cmd_name(world, actor, arg):
    """name cat <name> -- name the cat; the name is kept for every future visit."""
    cat = world.get("cat")
    if cat is None or cat.location != actor.location:
        return "There's no cat here to name."
    arg = arg.strip()
    if arg.lower().startswith("cat "):        # allow "name cat Shadow" or "name Shadow"
        arg = arg[4:].strip()
    given = arg.strip().strip('"').split("\n")[0][:24].strip()
    if not given:
        return "Name it what? e.g.  name cat Shadow"
    cat.attrs["given_name"] = given
    cat.name = given
    cat.description = _cat_description(cat)
    return f"The cat considers you a moment, then accepts the name {given}."


VERBS.update({
    "feed": cmd_feed, "pet": cmd_pet, "stroke": cmd_pet, "name": cmd_name,
})


def build_cat(world):
    """Add the cat to a freshly-assembled world, in the hut, with its three
    autonomous behaviors attached."""
    cat = world.add(Entity("cat", "cat",
        "a small cat, watching you with mild interest, tail curled",
        location="hut", attrs={"hunger": 0}))
    cat.attach("cat_hunger")
    cat.attach("cat_wander")
    cat.attach("cat_idle")
    return cat
