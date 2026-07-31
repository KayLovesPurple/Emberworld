"""
content.py -- Emberworld itself: the verbs, the autonomous behaviors, the
cat, and the world as assembled fresh. world.py's engine is generic; this is
where anything specific to hearths, potatoes, journals, and cats lives.

Growing the game = adding entries here. New verbs go in VERBS with a
one-line docstring; new autonomy goes in BEHAVIORS; new content goes in
build_world(). See ARCHITECTURE.md for the full recipe.
"""

from world import World, Entity, VERBS, FREE_VERBS, BEHAVIORS, SAVE, SAVE_VERSION, DAY_LENGTH


# ---------------------------------------------------------------------------
# Behaviors -- the autonomous bits. This is where a "living world" lives.
# ---------------------------------------------------------------------------
def burning(world, e):
    """Autonomous: a lit fuel source (candle, hearth) burns down and goes out."""
    if not e.attrs.get("lit"):
        return
    e.attrs["fuel"] -= 1
    fuel = e.attrs["fuel"]
    if fuel == 3:
        world.announce(f"The {e.name} burns low.", world.room_of(e))
    if fuel <= 0:
        e.attrs["lit"] = False
        e.description = e.attrs.get("spent_desc", f"the {e.name}, burnt out")
        world.announce(e.attrs.get("out_msg", f"The {e.name} goes out."),
                       world.room_of(e))


def growing(world, plant):
    """Autonomous: a planted crop ages each tick and eventually ripens."""
    if plant.attrs.get("ready"):
        return
    plant.attrs["growth"] = plant.attrs.get("growth", 0) + 1
    if plant.attrs["growth"] >= plant.attrs.get("ripe_at", 8):
        plant.attrs["ready"] = True
        world.announce("In the patch, the potato plant has ripened.",
                       world.room_of(plant))


def patch_state(world, patch):
    """Autonomous: the vegetable patch describes itself by what's growing in it."""
    # the patch describes itself by what's growing in it -- so planting shows.
    plants = world.contents(patch.id)
    if not plants:
        patch.description = "a strip of turned soil, dark and ready"
        return
    p = plants[0]
    if p.attrs.get("ready"):
        patch.description = "turned soil with a potato plant, lush and ready to lift"
        return
    g, ripe = p.attrs.get("growth", 0), p.attrs.get("ripe_at", 8)
    if g < 3:
        patch.description = "turned soil, a fresh mound where a potato was just set"
    elif g < ripe - 2:
        patch.description = "turned soil, green potato shoots pushing up"
    else:
        patch.description = "turned soil, a potato plant leafing out, not far off ripe"


def hungering(world, actor):
    """Autonomous: the actor slowly gets hungrier over time (capped, harmless)."""
    actor.attrs["hunger"] = min(actor.attrs.get("hunger", 0) + 1, 20)


# --- the cat ---------------------------------------------------------------
# GENTLE GUARANTEE: the cat's hunger is capped and drives nothing but meowing
# and wanting food. There is no starvation, no damage, no harm state it can
# ever reach. This is enforced here and pinned by a test. Do not add harm.
CAT_HUNGER_CAP = 12


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
    hungry = cat.attrs.get("hunger", 0) >= 6
    if name:
        return (f"{name}, a small cat, pacing and hungry, watching you keenly"
                if hungry else
                f"{name}, a small cat, watching you with mild interest")
    return ("a small cat, pacing and hungry, watching you keenly"
            if hungry else
            "a small cat, watching you with mild interest, tail curled")


def _cat_go(world, cat, direction):
    src = cat.location
    room = world.get(src)
    dest = room.exits.get(direction)
    if not dest:
        return
    cat.location = dest
    world.announce(f"{_cat_cap(cat)} slips out through the doorway.", src)
    world.announce(f"{_cat_cap(cat)} pads in, tail high.", dest)


def cat_wander(world, cat):
    """Autonomous: the cat drifts between rooms, drawn toward a lit hearth."""
    room = world.get(cat.location)
    if room is None or not room.exits:
        return
    r = world.rng.random()
    warm_here = _room_is_warm(world, cat.location)
    warm_exits = [d for d, dest in room.exits.items() if _room_is_warm(world, dest)]
    if warm_here:
        if r < 0.10:                                   # cozy: rarely leaves warmth
            _cat_go(world, cat, world.rng.choice(list(room.exits)))
    elif warm_exits:
        if r < 0.60:                                   # drawn toward a lit hearth
            _cat_go(world, cat, world.rng.choice(warm_exits))
    elif r < 0.25:                                     # otherwise idle drift
        _cat_go(world, cat, world.rng.choice(list(room.exits)))


def cat_hunger(world, cat):
    """Autonomous: the cat slowly gets hungry (capped, never harmed), shows it
    in its own description once hungry, and occasionally meows to be fed."""
    # capped -- the cat gets peckish, never worse.
    cat.attrs["hunger"] = min(cat.attrs.get("hunger", 0) + 1, CAT_HUNGER_CAP)
    cat.description = _cat_description(cat)
    if cat.attrs["hunger"] >= 6 and world.rng.random() < 0.35:
        world.announce(f"{_cat_cap(cat)} winds around your ankles, "
                       f"meowing to be fed.", cat.location)


BEHAVIORS.update({"burning": burning, "growing": growing, "patch_state": patch_state,
                   "hungering": hungering, "cat_wander": cat_wander,
                   "cat_hunger": cat_hunger})


def _patch_in(world, room_id):
    return next((p for p in world.contents(room_id) if p.id == "patch"), None)


def _crop_in(world, room_id):
    patch = _patch_in(world, room_id)
    plants = world.contents(patch.id) if patch else []
    return plants[0] if plants else None


# ---------------------------------------------------------------------------
# Verbs -- the actions. Growing the game = adding entries here.
# ---------------------------------------------------------------------------
def find_visible(world, actor, name):
    name = name.lower().strip()
    if not name:
        return None
    for e in world.contents(actor.location) + world.contents(actor.id):
        if e.id == actor.id:
            continue
        if name in e.name.lower() or name == e.id:
            return e
    return None


def _carrying(world, actor, e):
    return e is not None and e.location == actor.id


def _carried_line(world, actor):
    # carried items are part of the standing perception (not hidden behind a
    # separate 'inventory' command an amnesiac agent has to choose to run),
    # and stay visible even in the dark -- you can feel what's in your hands.
    items = world.contents(actor.id)
    if not items:
        return "Your hands are empty."
    return "You are carrying: " + ", ".join(e.name for e in items) + "."


def cmd_look(world, actor, arg):
    """look [thing] -- describe the room, or examine one thing (dark hides all but what you hold)."""
    room = world.get(actor.location)
    if arg:
        target = find_visible(world, actor, arg)
        if not target:
            return f"You don't see any '{arg}' here."
        # in the dark you can only make out what's in your own hands
        if world.is_dark(room.id) and not _carrying(world, actor, target):
            return "Too dark to make it out. Pick it up, or find a light."
        return target.description
    stamp = world.timestr()
    if world.is_dark(room.id):
        return (f"[{stamp}] Pitch dark. You can make out nothing without a "
                f"light. Somewhere out there the world goes on regardless.\n\n"
                f"{_carried_line(world, actor)}")
    lines = [f"[{stamp}]  {room.name.upper()}", room.description]
    here = [e for e in world.contents(room.id) if e.id != actor.id]
    if here:
        lines += [""] + [f"  - {e.description}" for e in here]
    if room.exits:
        lines += ["", "Exits: " + ", ".join(room.exits)]
    lines += ["", _carried_line(world, actor)]
    return "\n".join(lines)


def cmd_go(world, actor, arg):
    """go <exit> -- move through a named exit (you can also just type the exit name)."""
    room = world.get(actor.location)
    dest = room.exits.get(arg.lower().strip())
    if not dest:
        return f"You can't go {arg or 'that way'}."
    actor.location = dest
    return cmd_look(world, actor, "")


def cmd_take(world, actor, arg):
    """take <thing> -- pick up a portable object."""
    e = find_visible(world, actor, arg)
    if not e:
        return f"There's no '{arg}' here to take."
    if e.location == actor.id:
        return f"You're already carrying the {e.name}."
    if not e.portable:
        return f"The {e.name} won't budge."
    e.location = actor.id
    return f"You take the {e.name}."


def cmd_drop(world, actor, arg):
    """drop <thing> -- set down something you're carrying."""
    e = find_visible(world, actor, arg)
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    e.location = actor.location
    return f"You set down the {e.name}."


def cmd_inventory(world, actor, arg):
    """inventory -- list what you're carrying and how hungry you feel."""
    items = world.contents(actor.id)
    hunger = actor.attrs.get("hunger", 0)
    mood = ("stuffed" if hunger < 3 else "fine" if hunger < 10
            else "hungry" if hunger < 16 else "ravenous")
    head = f"You feel {mood}."
    if not items:
        return head + "\nYour hands are empty."
    return head + "\nYou are carrying:\n" + "\n".join(f"  - {e.name}" for e in items)


def cmd_wait(world, actor, arg):
    """wait -- let one tick pass while you do nothing."""
    return "You wait. Time passes."


def cmd_light(world, actor, arg):
    """light <thing> -- set a fuel source burning (the candle lights; the hearth cooks)."""
    e = find_visible(world, actor, arg)
    if not e or "lit" not in e.attrs:
        return "You can't light that."
    if e.attrs["lit"]:
        return f"The {e.name} is already lit."
    if e.attrs.get("fuel", 0) <= 0:
        return f"The {e.name} is spent -- nothing left to burn."
    e.attrs["lit"] = True
    e.description = e.attrs.get("lit_desc", f"the {e.name}, alight")
    return f"You light the {e.name}. Warm light spills out."


def cmd_snuff(world, actor, arg):
    """snuff <thing> -- put out a lit flame."""
    e = find_visible(world, actor, arg)
    if not e or "lit" not in e.attrs:
        return "You can't snuff that."
    if not e.attrs["lit"]:
        return f"The {e.name} isn't lit."
    e.attrs["lit"] = False
    e.description = e.attrs.get("unlit_desc", f"the {e.name}, unlit")
    return f"You pinch out the {e.name}."


def cmd_plant(world, actor, arg):
    """plant potato -- press a raw potato into the vegetable patch to grow it."""
    e = find_visible(world, actor, arg or "potato")
    if not e or e.location != actor.id or "potato" not in e.name \
            or e.attrs.get("food", 0) > 0:
        return "You need a raw potato in hand to plant."
    patch = _patch_in(world, actor.location)
    if not patch:
        return "There's no turned soil here to plant in."
    if world.contents(patch.id):
        return "Something's already growing here. Let it finish first."
    world.entities.pop(e.id, None)
    plant = world.add(Entity(world.fresh_id("plant"), "potato plant",
        "a just-planted potato", location=patch.id,
        attrs={"growth": 0, "ripe_at": 8}))
    plant.attach("growing")
    return "You press the potato into the soil and firm it down. Now: time."


def cmd_harvest(world, actor, arg):
    """harvest -- lift a ripened crop from the patch for its potatoes."""
    crop = _crop_in(world, actor.location)
    if not crop or not crop.attrs.get("ready"):
        return "Nothing here is ready to harvest."
    world.entities.pop(crop.id, None)
    for _ in range(2):
        world.add(Entity(world.fresh_id("potato"), "potato",
            "a firm potato, fresh from the earth",
            location=actor.id, portable=True))
    return "You lift the plant and shake two fat potatoes from the roots."


def cmd_cook(world, actor, arg):
    """cook potato -- broil a potato at a lit cooking fire, making it edible."""
    e = find_visible(world, actor, arg or "potato")
    if not e or "potato" not in e.name:
        return "You can only cook a potato here (for now)."
    if e.attrs.get("food", 0) > 0:
        return f"The {e.name} is already cooked."
    fire = next((f for f in world.contents(actor.location)
                 if f.attrs.get("lit") and f.attrs.get("cooks")), None)
    if not fire:
        return "You need a lit cooking fire. The hearth, if you light it."
    e.name = "broiled potato"
    e.description = "a hot broiled potato, skin blistered and steaming"
    e.attrs["food"] = 8
    return "You bury the potato in the embers. Soon it's blistered and steaming."


def cmd_eat(world, actor, arg):
    """eat <thing> -- eat cooked food to ease your hunger."""
    e = find_visible(world, actor, arg)
    if not e:
        return f"You have no '{arg}' to eat."
    food = e.attrs.get("food", 0)
    if food <= 0:
        if "potato" in e.name:
            return "You could eat it raw, but you'd regret it. Cook it first."
        return f"You can't eat the {e.name}."
    actor.attrs["hunger"] = max(0, actor.attrs.get("hunger", 0) - food)
    world.entities.pop(e.id, None)
    return f"You eat the {e.name}. Warm, and it settles you."


def cmd_write(world, actor, arg):
    """write <note> -- add a line to the shared journal for future visitors."""
    journal = find_visible(world, actor, "journal")
    if not journal:
        return "You've no journal to hand. It's in the hut."
    if not arg:
        return "Write what? e.g.  write planted two potatoes near the fence."
    journal.attrs.setdefault("entries", []).append(f"[Day {world.day()}] {arg}")
    return "You write in the journal. The ink dries slowly. It will keep."


def cmd_read(world, actor, arg):
    """read journal -- read the journal (needs light unless you're holding it)."""
    journal = find_visible(world, actor, arg or "journal")
    if not journal or "entries" not in journal.attrs:
        return "There's nothing written there."
    if world.is_dark(actor.location) and not _carrying(world, actor, journal):
        return "Too dark to read. Pick it up, or bring a light."
    entries = journal.attrs["entries"]
    if not entries:
        return "The journal is blank, waiting for someone's first entry."
    return "The journal reads:\n" + "\n".join(f"  {ln}" for ln in entries)


def cmd_feed(world, actor, arg):
    """feed cat -- give a carried potato to the cat if it's in the room."""
    cat = world.get("cat")
    if cat is None or cat.location != actor.location:
        return "There's no cat here to feed."
    food = next((e for e in world.contents(actor.id) if "potato" in e.name), None)
    if not food:
        return "You've nothing to feed it just now -- a potato would do."
    world.entities.pop(food.id, None)
    cat.attrs["hunger"] = 0
    return f"The cat sets upon the {food.name}, eats every scrap, and purrs."


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


def cmd_save(world, actor, arg):
    """save -- write the world to disk (also happens automatically on quit)."""
    world.save()
    return f"The world settles into memory. ({SAVE})"


VERBS.update({
    "look": cmd_look, "l": cmd_look, "examine": cmd_look, "x": cmd_look,
    "go": cmd_go, "move": cmd_go,
    "take": cmd_take, "get": cmd_take, "grab": cmd_take,
    "drop": cmd_drop,
    "inventory": cmd_inventory, "i": cmd_inventory,
    "wait": cmd_wait, "z": cmd_wait,
    "light": cmd_light, "snuff": cmd_snuff,
    "plant": cmd_plant, "harvest": cmd_harvest,
    "cook": cmd_cook, "broil": cmd_cook, "eat": cmd_eat,
    "write": cmd_write, "read": cmd_read, "save": cmd_save,
    "feed": cmd_feed, "pet": cmd_pet, "stroke": cmd_pet, "name": cmd_name,
})
FREE_VERBS.update({"look", "l", "examine", "x", "inventory", "i", "read", "save"})


# ---------------------------------------------------------------------------
# Self-documenting reference. Built from the VERBS/BEHAVIORS registries and the
# world's own constants, so it can never drift out of sync with the code.
#   python3 emberworld.py --reference > REFERENCE.md
# A test asserts every verb and behavior carries a docstring, so nothing new
# can slip in undocumented.
# ---------------------------------------------------------------------------
def _first_line(fn):
    return (fn.__doc__ or "(undocumented)").strip().split("\n")[0]


def generate_reference():
    # group verb aliases that point at the same function, keeping first-seen order
    order, aliases = [], {}
    for name, fn in VERBS.items():
        if fn not in aliases:
            order.append(fn)
            aliases[fn] = []
        aliases[fn].append(name)

    out = ["# Emberworld -- Reference",
           "",
           "*Generated from the code by `python3 emberworld.py --reference`. "
           "Don't edit by hand -- regenerate it.*",
           "",
           "## Verbs", ""]
    for fn in order:
        names = " / ".join(f"`{a}`" for a in aliases[fn])
        free = "  _(free -- costs no time)_" if any(
            a in FREE_VERBS for a in aliases[fn]) else ""
        out.append(f"- {names} -- {_first_line(fn)}{free}")

    out += ["", "## Autonomous behaviors",
            "*These run on their own every tick, whether or not you act.*", ""]
    for name, fn in BEHAVIORS.items():
        out.append(f"- **{name}** -- {_first_line(fn)}")

    out += ["", "## World rules (from the code's own constants)", "",
            f"- A full day is **{DAY_LENGTH} ticks**; night falls late in that "
            "cycle and is pitch dark without a lit flame.",
            "- The candle only gives light; the **hearth** is what cooks.",
            f"- The cat's hunger is capped at **{CAT_HUNGER_CAP}** and it can "
            "come to no harm -- it only ever wants feeding.",
            f"- The world saves to disk (save format v{SAVE_VERSION}); an "
            "incompatible save is set aside, never mis-loaded.",
            "- Free verbs don't advance time; everything else ticks the world "
            "forward once.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The world, assembled fresh (used only when there's no save to inherit).
# ---------------------------------------------------------------------------
def build_world():
    w = World()
    w.add(Entity("hut", "A One-Room Hut",
        "Rough plank walls, a dirt floor, the smell of old woodsmoke. A cold "
        "hearth waits against one wall. Through the doorway, the yard.",
        exits={"out": "yard"}))
    w.add(Entity("yard", "The Yard",
        "Long grass, wet with evening. A vegetable patch of turned soil runs "
        "along the fence; the dark shape of a well stands near the gate.",
        exits={"in": "hut"}))

    candle = w.add(Entity("candle", "candle",
        "a stub of tallow candle, burning steadily", location="hut",
        portable=True, attrs={"lit": True, "fuel": 12,
            "lit_desc": "a stub of tallow candle, burning steadily",
            "unlit_desc": "an unlit stub of tallow candle",
            "spent_desc": "a spent candle, a curl of smoke off the black wick",
            "out_msg": "The candle sputters and goes out."}))
    candle.attach("burning")

    hearth = w.add(Entity("hearth", "hearth",
        "a cold stone hearth, ash and a few charred sticks", location="hut",
        attrs={"lit": False, "fuel": 40, "cooks": True,
            "lit_desc": "the hearth, full of red embers and low flame",
            "unlit_desc": "a cold stone hearth, ash and a few charred sticks",
            "spent_desc": "the hearth, gone to grey ash",
            "out_msg": "The fire in the hearth sinks to embers, then ash."}))
    hearth.attach("burning")

    journal = w.add(Entity("journal", "journal",
        "a worn journal, its cover soft with handling", location="hut",
        portable=True, attrs={"entries": [
            "[Day 1] To whoever comes next: the hearth cooks, the candle only "
            "lights. Plant early -- the potatoes take their time. There's a cat; "
            "feed it a potato if it's hungry, and it likes the fire lit. I left "
            "before the harvest. -- someone before you"
        ]}))

    cat = w.add(Entity("cat", "cat",
        "a small cat, watching you with mild interest, tail curled",
        location="hut", attrs={"hunger": 0}))
    cat.attach("cat_hunger")
    cat.attach("cat_wander")

    patch = w.add(Entity("patch", "vegetable patch",
        "a strip of turned soil, dark and ready", location="yard"))
    patch.attach("patch_state")
    w.add(Entity("knife", "knife",
        "a small iron knife, good for whittling or gutting fish",
        location="hut", portable=True))
    w.add(Entity("potato", "potato",
        "a firm potato, a few eyes already sprouting",
        location="yard", portable=True))

    actor = w.add(Entity("you", "you", "It's you.", location="hut",
                         attrs={"hunger": 0}))
    actor.attach("hungering")
    return w, actor
