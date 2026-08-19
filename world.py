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
from dataclasses import dataclass, field

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
ACTION_SOURCES = []  # fn(world, actor) -> the actions it can offer right now.
                     # A list, not a dict, because the ORDER a hand reads the
                     # actions in is part of the surface -- so content.py
                     # registers them all at one site, in one deliberate
                     # order, rather than leaving it to import order.


class IncompatibleSaveError(Exception):
    """A save file from a different (incompatible) version of the world."""


class WorldInvariantError(Exception):
    """The world reached a state that should be impossible. A real bug."""


@dataclass
class VisitState:
    """Session-scoped state for one hand's visit. Never written by World.to_data()."""

    forest_depth: int = 0
    forest_mark_depth: int = 0
    statue_found_this_session: bool = False
    calm_visits: dict = field(default_factory=dict)
    hand_name: str | None = None
    journal_entry_index: int | None = None
    journal_entry_is_placeholder: bool = False


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
        # Session-scoped visit state (forest depth, calm ack, hand name, …).
        # See VisitState and to_data()'s four-key shape -- nothing here persists.
        self.visit = VisitState()

    # --- visit-scoped fields (alias VisitState for existing call sites) ----
    @property
    def forest_depth(self):
        return self.visit.forest_depth

    @forest_depth.setter
    def forest_depth(self, value):
        self.visit.forest_depth = value

    @property
    def forest_mark_depth(self):
        return self.visit.forest_mark_depth

    @forest_mark_depth.setter
    def forest_mark_depth(self, value):
        self.visit.forest_mark_depth = value

    @property
    def statue_found_this_session(self):
        return self.visit.statue_found_this_session

    @statue_found_this_session.setter
    def statue_found_this_session(self, value):
        self.visit.statue_found_this_session = value

    @property
    def calm_visits(self):
        return self.visit.calm_visits

    @property
    def hand_name(self):
        return self.visit.hand_name

    @hand_name.setter
    def hand_name(self, value):
        self.visit.hand_name = value

    @property
    def journal_entry_index(self):
        return self.visit.journal_entry_index

    @journal_entry_index.setter
    def journal_entry_index(self, value):
        self.visit.journal_entry_index = value

    @property
    def journal_entry_is_placeholder(self):
        return self.visit.journal_entry_is_placeholder

    @journal_entry_is_placeholder.setter
    def journal_entry_is_placeholder(self, value):
        self.visit.journal_entry_is_placeholder = value

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
        """Every command that can do something here, right now -- the shared
        surface a human reads off `actions` and an LLM picks from.

        WHICH actions those are is entirely Emberworld's business, not the
        engine's: it turns on hearths, potatoes, cats and how deep into the
        forest someone has wandered, none of which this module knows about.
        So the list is assembled from ACTION_SOURCES, filled by content.py
        the same way it fills VERBS and BEHAVIORS -- which is what lets the
        promise at the top of this file stay true.

        (It didn't used to. This method was 89 lines of hardcoded "yard",
        "forest_edge", "potato", "lamp", "journal", "cat" -- the single
        reason this module needed a deferred import back into content.py to
        dodge a circular import, and the single thing every new feature
        anywhere had to come here to edit.)"""
        acts = []
        for source in ACTION_SOURCES:
            acts.extend(source(self, actor))
        # Several sources build one action per matching entity (every "take
        # <curio>", "look <curio>", "give <curio> to <cat>"), and it's
        # ordinary for a room or a pack to hold more than one curio sharing a
        # name (three stones, say) -- which used to mean the exact same
        # command text repeated once per duplicate. They're the same action
        # regardless of which physical copy answers it (find_visible always
        # resolves the string the same way), so collapsed here, once,
        # centrally, rather than in every action source that could ever
        # produce a same-named entity. dict.fromkeys preserves first-seen
        # order; genuinely distinct strings ("light lamp" vs "snuff lamp")
        # are untouched.
        return list(dict.fromkeys(acts))

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
