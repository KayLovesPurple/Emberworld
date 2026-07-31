"""
emberworld.py -- a small living world, now with a memory.

A hut, a yard, a day that turns to night, potatoes that take their time, a
hearth that cooks and a candle that only lights. The world runs on its own
heartbeat: the candle burns, crops grow, night falls, whether or not you act.

And it REMEMBERS. The world saves to disk between runs, and there's a journal
you can write in. So a later visitor -- you, or another Claude reaching in over
the API -- inherits the potato you planted and the notes you left. A lineage of
hands sharing one world, asynchronously, through what they leave behind.

Play it yourself:     python emberworld.py
Watch a dumb agent:   python emberworld.py --agent      (no API key needed)
Let an LLM live here: python emberworld.py --llm        (needs anthropic + key)

Human and LLM drive the SAME surface:
    world.perceive(actor)          -> text: where you are, what you see
    world.available_actions(actor) -> list of legal commands right now
    world.act(actor, command)      -> apply it, advance one tick, return result
"""

import os
import sys
import json
import random
from collections import deque

# Save next to THIS script, not wherever you happen to launch from -- so the
# world travels with the file and you get one world, not one-per-directory.
SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emberworld_save.json")
SAVE_VERSION = 2                      # bump when the on-disk shape changes
DAY_LENGTH = 24                       # ticks in a full day
LLM_MODEL = "claude-sonnet-5"         # which model the --llm hand uses (override: --model)


class IncompatibleSaveError(Exception):
    """A save file from a different (incompatible) version of the world."""


class WorldInvariantError(Exception):
    """The world reached a state that should be impossible. A real bug."""


# ---------------------------------------------------------------------------
# The stuff of the world. Everything -- rooms, items, the actor -- is an Entity.
# ---------------------------------------------------------------------------
class Entity:
    def __init__(self, id, name, description="", location=None,
                 portable=False, exits=None, attrs=None):
        self.id = id
        self.name = name
        self.description = description
        self.location = location        # id of its container (a room, the actor)
        self.portable = portable
        self.exits = exits or {}         # direction -> room id  (rooms use this)
        self.attrs = attrs or {}         # fuel, lit, hunger, growth, entries...
        self.behavior_names = []         # serializable source of truth
        self.behaviors = []              # resolved fn(world, self), run each tick

    def attach(self, name):
        self.behavior_names.append(name)
        fn = BEHAVIORS.get(name)
        if fn:
            self.behaviors.append(fn)
        return self

    def tick(self, world):
        for behave in self.behaviors:
            behave(world, self)

    # --- persistence ---
    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "location": self.location, "portable": self.portable,
                "exits": self.exits, "attrs": self.attrs,
                "behaviors": self.behavior_names}

    @classmethod
    def from_dict(cls, d):
        e = cls(d["id"], d["name"], d["description"], d["location"],
                d["portable"], d["exits"], d["attrs"])
        for n in d.get("behaviors", []):
            e.attach(n)
        return e


class World:
    def __init__(self):
        self.entities = {}
        self.time = 14                   # start at dusk; night comes soon
        self._seq = 0
        self.log = []                    # (message, room_id_or_None) this tick
        self.strict = False              # if True, check invariants every tick
        self.rng = random.Random()       # world's own randomness (cat wander, etc.)

    # --- bookkeeping -------------------------------------------------------
    def add(self, e):
        self.entities[e.id] = e
        return e

    def get(self, id):
        return self.entities.get(id)

    def fresh_id(self, prefix):
        self._seq += 1
        return f"{prefix}_{self._seq}"

    def contents(self, container_id):
        return [e for e in self.entities.values() if e.location == container_id]

    def announce(self, msg, where=None):
        # where=None -> everyone hears it; otherwise only that room does
        self.log.append((msg, where))

    def room_of(self, e):
        # walk up the container chain until we hit a room (location is None)
        seen = set()
        while e and e.location is not None and e.id not in seen:
            seen.add(e.id)
            e = self.get(e.location)
        return e.id if e else None

    # --- time of day -------------------------------------------------------
    def phase(self):
        h = self.time % DAY_LENGTH
        return ("dawn" if h < 6 else "day" if h < 14 else "dusk" if h < 19
                else "night")

    def day(self):
        return self.time // DAY_LENGTH + 1

    def timestr(self):
        return f"Day {self.day()}, {self.phase()}"

    def is_dark(self, room_id):
        if self.phase() != "night":
            return False
        lit = any(e.attrs.get("lit") and self.room_of(e) == room_id
                  for e in self.entities.values())
        return not lit

    def _depth(self, e):
        d, seen = 0, set()
        while e and e.location is not None and e.id not in seen:
            seen.add(e.id)
            e = self.get(e.location)
            d += 1
        return d

    # --- the heartbeat -----------------------------------------------------
    def tick(self):
        before = self.phase()
        self.time += 1
        after = self.phase()
        if after != before:
            self.announce(PHASE_MSG[after])
        # deepest first: a plant settles before the patch that describes it.
        for e in sorted(self.entities.values(), key=lambda e: -self._depth(e)):
            e.tick(self)
        if self.strict:
            issues = check_world(self)
            if issues:
                raise WorldInvariantError("; ".join(issues))

    # --- the shared surface (human OR llm) ---------------------------------
    def perceive(self, actor):
        return cmd_look(self, actor, "")

    def available_actions(self, actor):
        acts = ["look", "wait"]
        room = self.get(actor.location)
        for d in room.exits:
            acts.append(f"go {d}")
        here = self.contents(room.id)
        carried = self.contents(actor.id)
        for e in here:
            if e.id == actor.id:
                continue
            acts.append(f"look {e.name}")
            if e.portable:
                acts.append(f"take {e.name}")
        crop = _crop_in(self, room.id)
        if crop and crop.attrs.get("ready"):
            acts.append("harvest")
        for e in carried:
            acts.append(f"drop {e.name}")
        for e in here + carried:
            if "lit" in e.attrs:
                acts.append(("snuff " if e.attrs["lit"] else "light ") + e.name)
            if e.attrs.get("food", 0) > 0:
                acts.append(f"eat {e.name}")
        # contextual crafting verbs
        if any("potato" in e.name and e.attrs.get("food", 0) == 0 for e in carried):
            if _patch_in(self, room.id) and not crop:
                acts.append("plant potato")
            if any(f.attrs.get("cooks") and f.attrs.get("lit") for f in here):
                acts.append("cook potato")
        if any(e.id == "journal" for e in here + carried):
            acts.append("read journal")
            acts.append("write <your note>")
        cat = self.get("cat")
        if cat is not None and cat.location == room.id:
            acts.append(f"pet {cat.name}")
            if any("potato" in e.name for e in carried):
                acts.append(f"feed {cat.name}")
            if not cat.attrs.get("given_name"):
                acts.append("name cat <name>")
        return acts

    def act(self, actor, command):
        command = (command or "").strip()
        if not command:
            return "..."
        verb, _, arg = command.partition(" ")
        verb, arg = verb.lower(), arg.strip()

        handler = VERBS.get(verb)
        room = self.get(actor.location)
        if handler is None and verb in room.exits:      # bare "out", "north"...
            handler, arg = cmd_go, verb
        if handler is None:
            return f"I don't understand '{verb}'."

        self.log = []
        result = handler(self, actor, arg)

        if verb not in FREE_VERBS:               # time moves for real actions
            self.tick()

        heard = [m for (m, where) in self.log
                 if where is None or where == self.room_of(actor)]
        if heard:
            result = result + "\n" + "\n".join(heard)
        return result

    # --- persistence -------------------------------------------------------
    def to_data(self):
        return {"version": SAVE_VERSION, "time": self.time, "seq": self._seq,
                "entities": [e.to_dict() for e in self.entities.values()]}

    def save(self, path=None):
        path = path or SAVE
        with open(path, "w") as f:
            json.dump(self.to_data(), f, indent=2)

    @classmethod
    def from_data(cls, data):
        v = data.get("version")
        if v != SAVE_VERSION:
            raise IncompatibleSaveError(v)
        w = cls()
        w.time = data["time"]
        w._seq = data.get("seq", 0)
        w.entities = {}
        for d in data["entities"]:
            w.add(Entity.from_dict(d))
        return w

    @classmethod
    def load(cls, path=None):
        path = path or SAVE
        with open(path) as f:
            data = json.load(f)
        return cls.from_data(data)


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
    """Autonomous: the cat slowly gets hungry (capped, never harmed) and meows to be fed."""
    # capped -- the cat gets peckish, never worse.
    cat.attrs["hunger"] = min(cat.attrs.get("hunger", 0) + 1, CAT_HUNGER_CAP)
    if cat.attrs["hunger"] >= 6 and world.rng.random() < 0.35:
        world.announce(f"{_cat_cap(cat)} winds around your ankles, "
                       f"meowing to be fed.", cat.location)


BEHAVIORS = {"burning": burning, "growing": growing, "patch_state": patch_state,
             "hungering": hungering, "cat_wander": cat_wander,
             "cat_hunger": cat_hunger}


def _patch_in(world, room_id):
    return next((p for p in world.contents(room_id) if p.id == "patch"), None)


def _crop_in(world, room_id):
    patch = _patch_in(world, room_id)
    plants = world.contents(patch.id) if patch else []
    return plants[0] if plants else None


# ---------------------------------------------------------------------------
# The invariant checker. After any tick, these must ALWAYS hold -- no matter
# what features exist. This is what catches the *unknown* future bug: you don't
# predict it, you just assert the world stays well-formed and let it scream.
# ---------------------------------------------------------------------------
def check_world(world):
    issues = []
    ids = set(world.entities)

    if "you" not in ids:
        issues.append("the actor 'you' has vanished")

    for e in world.entities.values():
        # every location points at something that exists
        if e.location is not None and e.location not in ids:
            issues.append(f"{e.id}: lives in '{e.location}', which doesn't exist")

        # every declared behavior resolves to a real one
        for name in e.behavior_names:
            if name not in BEHAVIORS:
                issues.append(f"{e.id}: has unknown behavior '{name}'")

        # numeric attrs never go negative (fuel, growth, hunger, food, ...)
        for key, val in e.attrs.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool) and val < 0:
                issues.append(f"{e.id}: {key} is negative ({val})")

        # containment terminates at a room (location None) with no cycles
        seen, cur = set(), e
        while cur is not None and cur.location is not None:
            if cur.id in seen:
                issues.append(f"{e.id}: is trapped in a containment cycle")
                break
            seen.add(cur.id)
            cur = world.get(cur.location)

    return issues


# ---------------------------------------------------------------------------
# Headless fuzzer. The dumb agent, but seeded and checked: random legal play
# for thousands of steps, invariants verified after every single tick. Random
# play wanders into state nobody would script by hand -- highest-leverage catch
# for emergent breakage, and nearly free since the agent already exists.
# ---------------------------------------------------------------------------
def fuzz_run(steps=2000, seed=0, verbose=False):
    rng = random.Random(seed)
    w, actor = build_world()
    w.rng = random.Random(seed)          # make the cat's wandering reproducible too
    w.strict = True                      # act() raises on any invariant break
    for i in range(steps):
        options = [a for a in w.available_actions(actor) if "<" not in a]
        w.act(actor, rng.choice(options))
    issues = check_world(w)
    if verbose:
        state = "clean" if not issues else f"BROKEN: {issues}"
        print(f"fuzz: {steps} steps, seed {seed} -> {state} "
              f"(ended {w.timestr()})")
    return issues


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
                f"light. Somewhere out there the world goes on regardless.")
    lines = [f"[{stamp}]  {room.name.upper()}", room.description]
    here = [e for e in world.contents(room.id) if e.id != actor.id]
    if here:
        lines += [""] + [f"  - {e.description}" for e in here]
    if room.exits:
        lines += ["", "Exits: " + ", ".join(room.exits)]
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
        return "The journal is blank, waiting for a first hand."
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
    """name cat <name> -- name the cat; the name is kept for every future hand."""
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
    cat.description = f"{given}, a small cat, watching you with mild interest"
    return f"The cat considers you a moment, then accepts the name {given}."


def cmd_save(world, actor, arg):
    """save -- write the world to disk (also happens automatically on quit)."""
    world.save()
    return f"The world settles into memory. ({SAVE})"


VERBS = {
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
}
FREE_VERBS = {"look", "l", "examine", "x", "inventory", "i", "read", "save"}

PHASE_MSG = {
    "dawn": "The sky pales. Dawn.",
    "day": "The sun clears the fence. Full day.",
    "dusk": "The light goes amber, then blue. Dusk.",
    "night": "Night falls. Away from any flame, the dark is total.",
}


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
            "before the harvest. -- a hand before yours"
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


def load_or_build(quiet=False):
    if os.path.exists(SAVE):
        try:
            w = World.load()
            actor = w.get("you")
            if actor:
                if not quiet:
                    print(f"(You return to a world already in progress -- {w.timestr()}.)")
                return w, actor
        except IncompatibleSaveError as ex:
            _set_aside(SAVE, quiet,
                       f"That save is from an older world (v{ex.args[0]} vs "
                       f"v{SAVE_VERSION})")
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as ex:
            _set_aside(SAVE, quiet, f"That save couldn't be read ({ex})")
    return build_world()


def _set_aside(path, quiet, why):
    bak = path + ".bak"
    try:
        os.replace(path, bak)
        where = f" It's been moved to {bak}."
    except OSError:
        where = ""
    if not quiet:
        print(f"({why}; starting fresh.{where})")


# ---------------------------------------------------------------------------
# Driver 1: a human at a prompt.
# ---------------------------------------------------------------------------
BANNER = """\
============================================================
  EMBERWORLD  --  a very small living world that remembers
  'help' for verbs, 'quit' to leave (the world is saved)
============================================================"""

HELP = """\
Verbs:  look [thing] / go <exit> / take / drop / inventory
        light <thing> / snuff <thing> / wait
        plant potato / harvest / cook potato / eat <thing>
        feed cat / pet cat / write <note> / read journal / save / quit
The candle only lights; the hearth cooks. Night is dark without a flame.
There's a cat -- it wanders, it likes the fire lit, and it can be fed a potato.
The world (and your journal) persist between runs. Leave a note for the next hand."""


def play(strict=False):
    w, actor = load_or_build()
    w.strict = strict
    if strict:
        print("(--check on: invariants are verified after every action.)")
    print(BANNER)
    print("\n" + w.perceive(actor))
    while True:
        try:
            cmd = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            w.save()
            print(f"\nThe world settles into memory, and goes on without you.\n(saved: {SAVE})")
            return
        if cmd in ("quit", "exit", "q"):
            w.save()
            print(f"The world settles into memory, and goes on without you.\n(saved: {SAVE})")
            return
        if cmd in ("help", "?"):
            print(HELP)
            continue
        try:
            print(w.act(actor, cmd))
        except WorldInvariantError as ex:
            print(f"!! The world just entered an impossible state: {ex}\n"
                  f"!! That's a bug. Not saving over your good file.")
            return


# ---------------------------------------------------------------------------
# Driver 2: a dumb agent. Proves the world runs headless with a non-human
# driver -- the exact shape an LLM slots into. No API key needed.
# ---------------------------------------------------------------------------
def random_agent(steps=20):
    w, actor = load_or_build(quiet=True)
    print(w.perceive(actor), "\n")
    for _ in range(steps):
        choice = random.choice([a for a in w.available_actions(actor)
                                if "<" not in a])
        print(f">>> {choice}")
        print(w.act(actor, choice), "\n")
    w.save()


# ---------------------------------------------------------------------------
# Driver 3: an LLM. Same loop as the dumb agent, except the choice comes from
# Claude. Because the world persists, successive runs share it: one Claude
# plants, another returns days later to a grown crop and a journal of notes.
#
# Each turn is a FRESH instance with no memory of the last -- it re-reads the
# world every time. The continuity lives in the journal and the save file, not
# in the agent's head. So every visit ends by leaving a note on purpose: the
# only thread between one hand and the next.
# ---------------------------------------------------------------------------
def _ask_claude(client, system, user, model=LLM_MODEL, think=True, return_thinking=False):
    # Sonnet 5 has adaptive thinking on by default, but display defaults to
    # "omitted" -- thinking blocks come back EMPTY. To read the reasoning we must
    # explicitly ask for a summary. (You're billed for full thinking either way,
    # so this is free to surface.) Thinking tokens count against max_tokens, so
    # give generous headroom or the command gets truncated.
    kwargs = dict(model=model, max_tokens=1024, system=system,
                  messages=[{"role": "user", "content": user}])
    if not think:                            # Sonnet 5 accepts this at any effort
        kwargs["thinking"] = {"type": "disabled"}
    elif return_thinking:                    # opt in to a readable reasoning summary
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
    msg = client.messages.create(**kwargs)
    text = "".join(b.text for b in msg.content
                   if getattr(b, "type", None) == "text").strip()
    if return_thinking:
        thinking = "".join(getattr(b, "thinking", "") for b in msg.content
                           if getattr(b, "type", None) == "thinking").strip()
        return thinking, text
    return text


def _paint(text, code, on):
    return f"\033[{code}m{text}\033[0m" if on else text


def _recent_block(history):
    # a fresh instance has no memory; hand it a short scratch memory of its turns
    if not history:
        return "Recently you did: (nothing yet -- you just arrived)."
    lines = ["Recently you did (most recent last):"]
    for cmd, res in history:
        lines.append(f"  - {cmd} -> {res}")
    return "\n".join(lines)


def _looks_stuck(history, n=3):
    # repeating the SAME free verb (look/read/inventory) means spinning -- the
    # world isn't changing. Repeated `wait` is NOT stuck: that's how time passes.
    if len(history) < n:
        return False
    recent = [cmd for cmd, _ in list(history)[-n:]]
    if len(set(recent)) != 1:
        return False
    verb = recent[0].split()[0].lower() if recent[0].split() else ""
    return verb in FREE_VERBS


def llm_agent(turns=30, model=None, think=True, show_thoughts=False, color=True):
    model = model or LLM_MODEL
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY set. Export your key first:\n"
              "  export ANTHROPIC_API_KEY=sk-ant-...")
        return
    from anthropic import Anthropic          # lazy import: file runs without it
    client = Anthropic()
    w, actor = load_or_build(quiet=True)
    color = color and sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    if show_thoughts and not think:
        print("(--show-thoughts has nothing to show with --no-think.)")
    think_note = "thinking" if think else "no-think"
    print(f"(A hand arrives -- {w.timestr()}. {turns} turns to spend. "
          f"[{model}, {think_note}])\n")

    system = ("You are a hand living in a small text world that persists between "
              "visitors -- and you have no memory of past turns, so trust what "
              "the world and the journal tell you. Goal: keep a light through "
              "the night, grow and cook a potato, eat when hungry. There's a cat "
              "-- feed it if it's hungry, pet it if you like. Read the journal "
              "early. IMPORTANT: looking, reading, and checking inventory are "
              "FREE and do NOT pass time -- only actions like wait, go, plant, "
              "cook advance the world. To let a crop grow or the night pass, use "
              "`wait` (repeatedly). Reply with EXACTLY ONE command from the "
              "allowed list. For 'write', include your note text. Nothing else.")

    history = deque(maxlen=5)
    journal_text = None                       # once read, kept in view so it needn't re-read
    try:
        for i in range(turns):
            turns_left = turns - i
            actions = w.available_actions(actor)
            nudge = ""
            if _looks_stuck(history):
                nudge = ("\n(You keep repeating the same free action and nothing "
                         "is changing. Free actions like look/read never pass time "
                         "-- use `wait` to let the world move, or do something new.)")
            known = ""
            if journal_text is not None:
                known = ("\nThe journal (you've already read it, it won't change) "
                         f"says:\n{journal_text}")
            prompt = (f"{w.perceive(actor)}{known}\n\n{_recent_block(history)}{nudge}"
                      f"\n\nTurns left this visit: {turns_left}.\n\nAllowed:\n"
                      + "\n".join(actions) + "\n\nYour command:")
            try:
                if show_thoughts and think:
                    thoughts, choice = _ask_claude(client, system, prompt, model,
                                                   think, return_thinking=True)
                    if thoughts:
                        block = "\n".join("    " + ln for ln in thoughts.splitlines())
                        print(_paint(block, "90", color))     # dim grey
                    else:
                        print(_paint("    (no reasoning surfaced this turn)",
                                     "90", color))
                else:
                    choice = _ask_claude(client, system, prompt, model, think)
            except Exception as ex:                       # network/API hiccup
                print(f"(a turn slipped away: {ex})")
                continue
            print(_paint(f">>> {choice}", "1;36", color))     # bold cyan
            result = w.act(actor, choice)
            print(result, "\n")
            # remember the journal's contents the first time it's read this visit
            if choice.split()[:1] == ["read"] and "journal reads" in result:
                jrnl = w.get("journal")
                if jrnl is not None:
                    journal_text = "\n".join(jrnl.attrs.get("entries", []))
            first = result.splitlines()[0][:70] if result.strip() else "(nothing)"
            history.append((choice, first))
    except KeyboardInterrupt:
        print("\n(the visit is cut short -- but the note still gets left.)")

    _leave_signoff(client, w, actor, model, think)
    w.save()
    print(f"(The hand departs. Its note is in the journal.)\n(saved: {SAVE})")


def _leave_signoff(client, w, actor, model=None, think=True):
    """Always leave one closing note. Written straight to the journal entity so
    it lands wherever the agent ended up -- the deliberate trace for the next.

    The cat is mentioned to the departing hand ONLY if it's actually hungry, so
    caretaking enters the lineage when it matters -- not every single visit.
    That keeps the journal from turning into nothing but cat status reports."""
    journal = w.get("journal")
    if journal is None:
        return
    cat = w.get("cat")
    extra = ""
    if cat is not None and cat.attrs.get("hunger", 0) >= 6:
        extra = "\n(The cat seemed hungry when you left.)"
    try:
        note = _ask_claude(client,
            "You are a hand whose visit to a small persistent world is ending. "
            "Leave ONE short sentence in the shared journal for whoever comes "
            "next: what you did, or what you'd advise. Just the sentence.",
            f"{w.perceive(actor)}{extra}\n\nYour closing note:",
            model or LLM_MODEL, think)
    except Exception:
        note = ""
    note = note.strip().strip('"') or "A quiet visit. Nothing much changed. -- a passing hand"
    journal.attrs.setdefault("entries", []).append(f"[Day {w.day()}] {note}")


if __name__ == "__main__":
    def _int_flag(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            if i + 1 < len(sys.argv):
                try:
                    return int(sys.argv[i + 1])
                except ValueError:
                    pass
        return default

    def _str_flag(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return default

    if "--agent" in sys.argv:
        random_agent()
    elif "--reference" in sys.argv:
        print(generate_reference())
    elif "--llm" in sys.argv:
        llm_agent(turns=_int_flag("--turns", 30),
                  model=_str_flag("--model", LLM_MODEL),
                  think="--no-think" not in sys.argv,
                  show_thoughts="--show-thoughts" in sys.argv,
                  color="--no-color" not in sys.argv)
    elif "--fuzz" in sys.argv:
        issues = fuzz_run(steps=_int_flag("--steps", 5000), seed=0, verbose=True)
        sys.exit(1 if issues else 0)
    else:
        play(strict="--check" in sys.argv)
