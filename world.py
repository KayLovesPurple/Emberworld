"""
world.py -- the engine: Entity/World, the tick loop, persistence, and the
invariant checker.

No knowledge of any specific verb or behavior lives here. VERBS, FREE_VERBS,
and BEHAVIORS are declared as empty registries below and populated by
content.py at import time -- that's what lets this module stay generic while
content.py owns everything that's specific to Emberworld itself.
"""

import os
import json
import random

# Save next to THIS script, not wherever you happen to launch from -- so the
# world travels with the file and you get one world, not one-per-directory.
SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emberworld_save.json")
SAVE_VERSION = 2                      # bump when the on-disk shape changes
DAY_LENGTH = 24                       # ticks in a full day

PHASE_MSG = {
    "dawn": "The sky pales. Dawn.",
    "day": "The sun clears the fence. Full day.",
    "dusk": "The light goes amber, then blue. Dusk.",
    "night": "Night falls. Away from any flame, the dark is total.",
}

# Populated by content.py at import time. Keeping them here (rather than
# importing content.py, which imports US for Entity/World) is what avoids a
# circular import between the two modules.
VERBS = {}          # verb name -> handler fn(world, actor, arg)
FREE_VERBS = set()  # verb names that don't advance time
BEHAVIORS = {}       # behavior name -> fn(world, entity), run each tick


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
        self.time = 0                    # start at dawn; a full day of light to get oriented first
        self._seq = 0
        self.log = []                    # (message, room_id_or_None) this tick
        self.strict = False              # if True, check invariants every tick
        self.rng = random.Random()       # world's own randomness (cat wander, etc.)
        # FOREST_SPEC.md Stage 1: how far a hand has ventured into the forest
        # this session. Deliberately a plain runtime attribute, like rng/strict
        # above, not part of to_data()/from_data() -- position in the forest is
        # episodic (gone the instant a session ends), unlike anything a hand
        # actually carries or changes out there, which persists normally.
        self.forest_depth = 0
        # FOREST_SPEC.md Stage 5: the deepest depth marked this session via
        # `mark trail` (content.py's cmd_mark_trail) -- extends how far
        # cmd_return's Stage 4 off-course roll considers "safe" beyond the
        # flat SAFE_DEPTH_THRESHOLD. Session-scoped like forest_depth right
        # above, for the identical reason: a trail marked this visit means
        # nothing to the next, memoryless hand.
        self.forest_mark_depth = 0
        # FOREST_SPEC.md Stage 7: whether THIS session has found the statue
        # yet (content.py's cmd_venture rolls for it past STATUE_MIN_DEPTH).
        # Session-scoped like forest_depth/forest_mark_depth above, for the
        # same reason -- whether you've found it is a fact about this visit,
        # not the world; the next hand has to find it again on their own.
        self.statue_found_this_session = False
        # Calm-axis session acknowledgment (see content.py's _calm_visit_ack):
        # how many times THIS hand has chosen a calm act at a given calm spot
        # this visit, keyed by spot (e.g. "forest_edge"). Same reasoning as
        # forest_depth above -- deliberately not part of to_data()/from_data();
        # a hand's own sense of "I've been coming back here" is episodic, not
        # a fact about the world for the next hand to inherit.
        self.calm_visits = {}

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
        return VERBS["look"](self, actor, "")

    def available_actions(self, actor):
        # deferred: these two helpers are Emberworld-specific (they know about
        # "patch" and "crop" by id), so they live in content.py -- which
        # imports World/Entity from here, making a module-level import back
        # into content.py circular. Importing inside the function, once it's
        # actually called (after both modules have finished loading), avoids that.
        from content import _crop_in, _patch_in, find_visible, _is_full_moon, SHELF_CAPACITY, _statue_reachable, _room_here
        acts = ["look", "actions", "wait"]
        room = self.get(actor.location)
        for d in room.exits:
            acts.append(f"go {d}")
        here = _room_here(self, actor, room)
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
        if find_visible(self, actor, "well"):
            acts.append("draw water")
        bucket = find_visible(self, actor, "bucket")
        if crop and not crop.attrs.get("ready") and bucket and bucket.attrs.get("water", 0) > 0:
            acts.append("water crop")
        if room.id == "forest_edge":
            acts.append("gather wood")
            acts.append("listen")
            acts.append("venture")
            if self.forest_depth > 0:
                acts.append("return")
                if self.forest_depth > self.forest_mark_depth:
                    acts.append("mark trail")
            if self.forest_depth == 0 and any("stone" in e.name.lower() for e in carried):
                acts.append("stack stone on cairn")
            if _statue_reachable(self, actor):
                acts.append("wish <something>")
        if room.id in ("yard", "forest_edge") and (
                self.phase() != "night" or _is_full_moon(self)):
            acts.append("watch clouds")
        if find_visible(self, actor, "hearth") and actor.attrs.get("wood", 0) > 0:
            acts.append("add wood")
        for e in carried:
            acts.append(f"drop {e.name}")
        shelf = next((e for e in here if e.attrs.get("display_surface")), None)
        if shelf:
            if len(self.contents(shelf.id)) < SHELF_CAPACITY:
                for e in carried:
                    acts.append(f"place {e.name} on shelf")
            for e in self.contents(shelf.id):
                acts.append(f"take {e.name}")
        for e in here + carried:
            if "lit" in e.attrs:
                acts.append(("snuff " if e.attrs["lit"] else "light ") + e.name)
                if e.id == "lamp" and e.attrs["lit"]:
                    # topping up an already-lit lamp before a night is a
                    # deliberate feature -- it must stay a listed option, not
                    # just something reachable by an unlisted command.
                    acts.append(f"light {e.name}")
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
            for e in carried:
                if e.attrs.get("curio"):
                    acts.append(f"give {e.name} to {cat.name}")
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
            handler, arg = VERBS["go"], verb
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_data(), f, indent=2, ensure_ascii=False)

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
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_data(data)


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
