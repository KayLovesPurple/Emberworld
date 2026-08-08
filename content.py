"""
content.py -- Emberworld itself: the verbs, the autonomous behaviors, and the
world as assembled fresh. world.py's engine is generic; this is where
anything specific to hearths, potatoes, and journals lives. The cat is its
own self-contained subsystem -- see cat.py.

Growing the game = adding entries here. New verbs go in VERBS with a
one-line docstring; new autonomy goes in BEHAVIORS; new content goes in
build_world(). See ARCHITECTURE.md for the full recipe.
"""

from world import (World, Entity, VERBS, FREE_VERBS, BEHAVIORS, ACTION_SOURCES,
                   SAVE, SAVE_VERSION, DAY_LENGTH)
from cat import CAT_HUNGER_CAP, CAT_MEOW_THRESHOLD, build_cat, _cat_cap, cat_actions
from forest_text import (FOREST_FRAGMENTS, FOREST_AMBIENT, FOREST_AMBIENT_CHANCE,
                         _forest_band, describe_forest, _forest_ambient)
from content_common import (
    ACTOR_HUNGER_CAP, ACTOR_HUNGER_HUNGRY, actor_hunger_line,
    _the, _is_raw, _is_cooked, LAST_POTATO_BEAT, _patch_has_crop,
    _last_potato_beat, day_stamp as _day_stamp,
)


# ---------------------------------------------------------------------------
# Behaviors -- the autonomous bits. This is where a "living world" lives.
# ---------------------------------------------------------------------------
def burning(world, e):
    """Autonomous: a lit fuel source (the hearth) burns down and goes out."""
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
    """Autonomous: a planted crop ages each tick and eventually ripens -- twice
    as fast on any tick it spends a unit of stored water."""
    if plant.attrs.get("ready"):
        return
    boosted = plant.attrs.get("watered", 0) > 0
    plant.attrs["boosted"] = boosted   # so patch_state can describe THIS tick truthfully
    if boosted:
        plant.attrs["growth"] = plant.attrs.get("growth", 0) + 2
        plant.attrs["watered"] -= 1
    else:
        plant.attrs["growth"] = plant.attrs.get("growth", 0) + 1
    if plant.attrs["growth"] >= plant.attrs.get("ripe_at", 8):
        plant.attrs["ready"] = True
        world.announce("In the patch, the potato plant has ripened.",
                       world.room_of(plant))


def patch_state(world, patch):
    """Autonomous: the vegetable patch describes itself by what's growing in
    it, including whether it was just watered."""
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
    watered = ", well-watered" if p.attrs.get("boosted") else ""
    if g < 3:
        patch.description = f"turned soil, a fresh mound where a potato was just set{watered}"
    elif g < ripe - 2:
        patch.description = f"turned soil, green potato shoots pushing up{watered}"
    else:
        patch.description = f"turned soil, a potato plant leafing out, not far off ripe{watered}"


PATCH_VOLUNTEER_TURNS = 30   # comfortably more than one grow cycle (ripe_at=8)
                              # or a full day (24) -- a rescue, not a routine


def patch_volunteer(world, patch):
    """Autonomous: if the patch stays continuously empty for
    PATCH_VOLUNTEER_TURNS turns, one volunteer potato plant sprouts on its
    own -- deterministic, self-healing ground so a lineage can never be
    permanently seedless. A floor, not a faucet: the counter only advances
    while the patch is empty, and a volunteer's own arrival makes it
    non-empty, so a second one can never queue up behind the first."""
    if world.contents(patch.id):
        patch.attrs["empty_turns"] = 0
        return
    patch.attrs["empty_turns"] = patch.attrs.get("empty_turns", 0) + 1
    if patch.attrs["empty_turns"] >= PATCH_VOLUNTEER_TURNS:
        _sow(world, patch)
        patch.attrs["empty_turns"] = 0
        world.announce("A stray shoot has come up in the turned soil — a "
                       "potato you missed, returning on its own.",
                       world.room_of(patch))


def bucket_state(world, bucket):
    """Autonomous: the bucket describes itself by how much water it's holding."""
    water = bucket.attrs.get("water", 0)
    if water <= 0:
        bucket.description = "an empty wooden bucket by the well"
    else:
        bucket.description = f"a wooden bucket, holding water ({water})"


HEARTH_FUEL_START = 60      # the hearth's starting fuel, in build_world -- raised
                            # (was 40) in the pacing rebalance so wood-adding is
                            # occasional, not a recurring beat every visit
HEARTH_LOW_FUEL = HEARTH_FUEL_START // 4    # below this, it reads as dying


def hearth_state(world, hearth):
    """Autonomous: the hearth's description bands by fuel level whether lit
    or not -- a cold hearth used to say nothing about how much fuel it was
    holding, so a hand couldn't tell "unlit but stocked" from "unlit and
    empty" without trying to light it and failing. Banded the same way a lit
    hearth already shows dying-low vs steady, so the standing perception
    carries the fact before it's needed."""
    fuel = hearth.attrs.get("fuel", 0)
    if hearth.attrs.get("lit"):
        if fuel <= HEARTH_LOW_FUEL:
            hearth.description = "the hearth, embers dying low -- it wants more wood"
        else:
            hearth.description = hearth.attrs.get(
                "lit_desc", "the hearth, full of red embers and low flame")
        return
    if fuel <= 0:
        hearth.description = hearth.attrs.get(
            "spent_desc", "the hearth, burnt out")
    elif fuel <= HEARTH_LOW_FUEL:
        hearth.description = ("a cold hearth, only a little wood laid in -- "
                               "feed it more before lighting")
    else:
        hearth.description = hearth.attrs.get(
            "unlit_desc", "a cold stone hearth, ash and a few charred sticks")


def hungering(world, actor):
    """Autonomous: the actor slowly gets hungrier over time (capped, harmless)."""
    actor.attrs["hunger"] = min(actor.attrs.get("hunger", 0) + 1, ACTOR_HUNGER_CAP)


LAMP_FUEL_START = 32       # doubled in the pacing rebalance -- one kindling now
                           # comfortably covers a full typical visit, not just
                           # one night, so re-kindling stops being a recurring beat
LAMP_LOW_FUEL = 8          # warns with enough runway left to reach the hearth


def _lamp_description(lamp):
    """The lamp's description in full -- the sole source of truth for its
    three states, used both by verbs (on kindling/snuffing) and by its own
    tick behavior, so the text never drifts out of sync with its state."""
    if not lamp.attrs.get("lit"):
        return "a tin lamp, cold and dark — kindle it at the hearth"
    if lamp.attrs.get("fuel", 0) <= LAMP_LOW_FUEL:
        return "a tin lamp, its flame guttering low"
    return "a tin lamp, its flame steady and bright"


def lamp_burning(world, lamp):
    """Autonomous: a lit tin lamp burns down one fuel per tick, wherever it
    is -- carried or set down -- warning inline as it runs low and again when
    it finally goes dark."""
    if not lamp.attrs.get("lit"):
        return
    lamp.attrs["fuel"] -= 1
    fuel = lamp.attrs["fuel"]
    if fuel == LAMP_LOW_FUEL:
        world.announce("The lamp's flame shrinks — not long left in it.",
                       world.room_of(lamp))
    if fuel <= 0:
        lamp.attrs["lit"] = False
        world.announce("The lamp gutters, sputters, and goes dark.",
                       world.room_of(lamp))
    lamp.description = _lamp_description(lamp)


FOREST_FIND_CHANCE = 0.08   # pacing rebalance, round two: was 0.2. BUG WE HIT:
                            # a hand that lingered at the forest's edge for even
                            # a handful of turns (waiting, or -- once
                            # FOREST_SPEC.md Stage 1 added venture/return --
                            # shuttling depth back and forth) kept landing 3-4
                            # curios in "a few steps." The roll fires on ANY
                            # tick spent at forest_edge regardless of which
                            # verb burns it (see forest_finds below), so more
                            # turns there always means more rolls -- 0.2 per
                            # tick compounds fast once a few turns are spent in
                            # one place.
                            #
                            # FOREST_SPEC.md Stage 7: wood-gathering relocated
                            # here from the yard, and deliberately does NOT
                            # bring its own separate find-roll along with it
                            # (see cmd_gather below) -- this per-tick roll
                            # already fires on a gather-wood turn same as any
                            # other, so a second roll stacked on top would be
                            # exactly the intensification the relocation spec
                            # explicitly ruled out ("moved, not intensified").
                            # The old yard-side FOUND_ITEM_CHANCE (0.15) and
                            # its "somewhat better bet than the yard" framing
                            # are retired along with the yard roll itself.

# A hand asked to also stumble onto loose wood while exploring, not just via
# the deliberate `gather wood` turn. Carved out of the EXISTING roll above
# rather than an independent one stacked alongside it -- an independent
# roll would double the chance of anything happening on a given tick,
# exactly the intensification already ruled out once (see cmd_gather's
# comment). This share of an already-rare roll landing on wood keeps the
# overall per-tick odds unchanged at FOREST_FIND_CHANCE; it just
# occasionally spends that same roll on wood instead of a curio.
_STRAY_WOOD_SHARE = 0.15
WOOD_PER_STRAY_FIND = 1     # well under WOOD_PER_GATHER's deliberate haul --
                            # a nice-to-notice, not a replacement for foraging.


def forest_finds(world, room):
    """Autonomous: while a hand lingers at the forest's edge (arriving, or
    spending any later turn there -- venture/return included, since neither
    verb actually moves `actor.location` off this room), each turn has a
    small chance of turning up something underfoot: usually a curio, and a
    slice of that same chance a stray piece of wood instead, no `gather
    wood` required. One roll, not two -- see _STRAY_WOOD_SHARE above.
    Deliberately rare, not a guaranteed per-visit faucet: a find should stay a
    delight, not fill out a pack on autopilot -- and the chance is a per-tick
    roll, so more turns spent here always means more chances, however they're
    spent (see FOREST_FIND_CHANCE's comment for the incident that pinned this
    down to a low number)."""
    actor = world.get("you")
    if actor is None or actor.location != room.id:
        return
    roll = world.rng.random()
    if roll >= FOREST_FIND_CHANCE:
        return
    if roll >= FOREST_FIND_CHANCE * (1 - _STRAY_WOOD_SHARE):
        actor.attrs["wood"] = actor.attrs.get("wood", 0) + WOOD_PER_STRAY_FIND
        world.announce(
            f"A stray branch, dry enough to burn — you add it to your wood. "
            f"You now have {actor.attrs['wood']} wood.", room.id)
        return
    name, look_line, reaction = world.rng.choice(FOUND_ITEMS)
    world.add(Entity(world.fresh_id("found"), name,
                      _found_description(look_line, reaction, name),
                      location=actor.id, portable=True,
                      attrs={"curio": True, "cat_reaction": reaction}))
    world.announce(f"Half-buried by the path, {name} — you pocket it.",
                   room.id)


# Ambient wildlife -- glimpsed, not met. No verb triggers it, no verb
# resolves it, same restraint as the statue: it exists whether or not a hand
# notices, and nothing a hand can do makes it happen or explains it. Phase-
# keyed per room so what might be seen matches when it'd make sense to see
# it (a fox doesn't cross the yard at noon). Distinct from forest_finds --
# this never adds anything to a pack or the world; it's texture, not a find.
WILDLIFE_CHANCE = 0.03   # per eligible tick -- rare, an occasional delight

WILDLIFE_LINES = {
    "yard": {
        "dusk": (
            "A fox crosses the yard, unhurried, and is gone before you're "
            "sure you saw it.",
        ),
        "night": (
            "Something small rustles along the fence line, then goes still.",
        ),
    },
    "forest_edge": {
        "dawn": (
            "A deer stands at the treeline a moment, then steps back and is "
            "gone.",
        ),
        "night": (
            "An owl calls once from deeper in the trees, and doesn't call "
            "again.",
        ),
    },
}


def wildlife_glimpse(world, room):
    """Autonomous: while a hand is present, a small independent chance per
    tick of glimpsing something living and entirely unrelated to whatever
    the hand is doing -- see WILDLIFE_LINES/WILDLIFE_CHANCE above."""
    actor = world.get("you")
    if actor is None or actor.location != room.id:
        return
    pool = WILDLIFE_LINES.get(room.id, {}).get(world.phase())
    if not pool:
        return
    if world.rng.random() < WILDLIFE_CHANCE:
        world.announce(world.rng.choice(pool), room.id)


BEHAVIORS.update({"burning": burning, "growing": growing, "patch_state": patch_state,
                   "patch_volunteer": patch_volunteer,
                   "bucket_state": bucket_state, "hearth_state": hearth_state,
                   "hungering": hungering, "lamp_burning": lamp_burning,
                   "forest_finds": forest_finds, "wildlife_glimpse": wildlife_glimpse})


def _patch_in(world, room_id):
    return next((p for p in world.contents(room_id) if p.id == "patch"), None)


def _crop_in(world, room_id):
    patch = _patch_in(world, room_id)
    plants = world.contents(patch.id) if patch else []
    return plants[0] if plants else None


def _sow(world, patch):
    """Create a growing potato plant in the given patch -- the shared
    creation path for a hand's cmd_plant and the ground's own volunteer, so
    both produce identical entities and share the same grow/ripen/harvest
    machinery. The only difference between them is provenance (the message
    each one earns), never the mechanics."""
    plant = world.add(Entity(world.fresh_id("plant"), "potato plant",
        "a just-planted potato", location=patch.id,
        attrs={"growth": 0, "ripe_at": 8}))
    plant.attach("growing")
    return plant


# ---------------------------------------------------------------------------
# Verbs -- the actions. Growing the game = adding entries here.
# ---------------------------------------------------------------------------
# Which entities are actually present where they nominally live. Nearly all
# of them simply are; a couple are conditional, and those register a rule
# here -- keyed by entity id, fn(world, actor) -> bool -- from whichever
# part of the game owns them. Same idea as VERBS/BEHAVIORS/ACTION_SOURCES:
# the general machinery asks, the specific subsystem answers.
PRESENCE_RULES = {}

# Ids that, when they ARE present, sit at the end of the listing rather than
# wherever insertion order would put them. Only the statue, and deliberately:
# it reads as a beat at the end of what you can see, after the ordinary
# furniture of the clearing, rather than as one item among them. The original
# hand-rolled version of this function got that for free by filtering the
# statue out and re-appending it; keeping it explicit here means the ordering
# survived the rewrite instead of quietly changing the day someone dropped a
# curio at the edge after finding the statue.
PRESENCE_LAST = {"statue"}


def _always_present(world, actor):
    return True


def _room_here(world, actor, room):
    """The entities actually present in `room` right now -- ordinarily just
    world.contents(room.id), minus anything whose PRESENCE_RULE says it
    isn't really here at the moment.

    The rules exist because the forest's edge doubles as every forest depth
    (venturing is a session-scoped counter, not a real room change --
    actor.location never leaves "forest_edge"), so a flat content list makes
    things visible and reachable from anywhere in the whole forest rather
    than only where they belong:

    BUG WE HIT: once discovered, the statue appeared in the forest_edge room
    description forever after for the rest of the session -- even back at
    depth 0, right at the edge, contradicting its own "resists the system"
    design (it should never be a standing fixture you just look around and
    see). The cairn had the milder version of the same bug: it was reachable
    (via `look cairn`, even `stack stone on cairn`) from any depth, when
    it's meant to be a landmark you pass specifically AT the edge.

    Used by cmd_look, the action sources, AND find_visible, so a hand can't
    reach past a rule just by typing the object's name directly instead of
    picking it from the action list.

    This used to name the statue and the cairn inline, by id, which put
    knowledge of the forest inside the helper every verb in the game reaches
    through to find anything at all. The rules now live with the forest.
    """
    here, trailing = [], []
    for e in world.contents(room.id):
        if not PRESENCE_RULES.get(e.id, _always_present)(world, actor):
            continue
        (trailing if e.id in PRESENCE_LAST else here).append(e)
    return here + trailing


def find_visible(world, actor, name, prefer=None):
    """Find the nearest thing matching `name`. When several match (e.g. a
    raw and a broiled potato both contain "potato"), `prefer` -- a
    predicate(entity) -> bool -- picks the one that actually satisfies the
    caller's need. If none of the matches satisfy it, falls back to the
    first match anyway, so the caller's own refusal message still fires
    against a sensible target instead of silently finding nothing."""
    name = name.lower().strip()
    if not name:
        return None
    room = world.get(actor.location)
    here = _room_here(world, actor, room) if room else []
    displayed = [item for surface in here if surface.attrs.get("display_surface")
                 for item in world.contents(surface.id)]
    matches = [e for e in here + world.contents(actor.id) + displayed
               if e.id != actor.id and (name in e.name.lower() or name == e.id)]
    if not matches:
        return None
    if prefer:
        for e in matches:
            if prefer(e):
                return e
    return matches[0]


def _carrying(world, actor, e):
    return e is not None and e.location == actor.id


def _lamp_state_tag(lamp):
    if not lamp.attrs.get("lit"):
        return "unlit"
    if lamp.attrs.get("fuel", 0) <= LAMP_LOW_FUEL:
        return "lit, low"
    return "lit"


def _carried_names(world, actor):
    # identical items (two potatoes, say) group into one line with a count,
    # in first-seen order, rather than repeating the name.
    order, counts = [], {}
    for e in world.contents(actor.id):
        if e.name not in counts:
            order.append(e.name)
        counts[e.name] = counts.get(e.name, 0) + 1
    names = [f"{n} ({counts[n]})" if counts[n] > 1 else n for n in order]
    # the lamp's state matters everywhere it's shown, even in this terse
    # summary line -- not just in its full description when looked at directly.
    lamp = next((e for e in world.contents(actor.id) if e.id == "lamp"), None)
    if lamp is not None:
        idx = order.index(lamp.name)
        names[idx] = f"{lamp.name} ({_lamp_state_tag(lamp)})"
    # wood is stored as a plain integer attr on the actor, not an entity, so
    # it's folded in here as one line item -- everywhere carried things are
    # listed shows it, not just a place that happens to loop over entities.
    wood = actor.attrs.get("wood", 0)
    if wood > 0:
        names.insert(0, f"firewood ({wood})")
    return names


def _carried_line(world, actor):
    # carried items are part of the standing perception (not hidden behind a
    # separate 'inventory' command an amnesiac agent has to choose to run),
    # and stay visible even in the dark -- you can feel what's in your hands.
    # Hunger rides along on the same line for the same reason: cmd_inventory
    # is the only other place a hand's own hunger was ever legible, so a
    # hand that never runs it was otherwise blind to itself (see the "fed
    # every spare potato to the cat" pattern this fixes).
    names = _carried_names(world, actor)
    hands = "Your hands are empty." if not names \
        else "You are carrying: " + ", ".join(names) + "."
    return hands + "\n" + actor_hunger_line(actor)


_EXIT_LABELS = {
    "hut": {"out": "the yard"},
    "yard": {"in": "inside the hut", "forest": "the forest's edge"},
    "forest_edge": {"yard": "back to the yard"},
}

# A hand's own wording for an exit doesn't always match the short key rooms
# are keyed by (see build_world's `exits={...}`) -- "go inside" is a natural
# way to say "go in" near the hut. Mapped to the canonical key before
# `room.exits` is consulted, so it only ever works where that key actually
# exists as an exit (i.e. "inside" does nothing without an "in" exit nearby).
_DIRECTION_ALIASES = {"inside": "in"}


def _exit_label(room_id, direction):
    """A longer, legible phrase for an exit's entry in the Exits: line --
    purely cosmetic scene-setting text, distinct from the short direction key
    a hand actually types (`go <direction>`, still listed as-is by
    available_actions). Falls back to the bare key for any room/direction
    without a bespoke label, so a future exit degrades gracefully rather
    than crashing."""
    return _EXIT_LABELS.get(room_id, {}).get(direction, direction)


# BUG WE HIT: a dropped curio showed up in the room listing as a bare
# fragment -- "sea-frosted, edges gone soft." with no indication of what it
# even was. Every other room entity's .description is written to stand alone
# ("a stone well, its bucket-rope disappearing into the dark") because that
# same field is what the room listing prints -- but a curio's .description is
# deliberately just its bare look_line (see _found_description), reused
# as-is by `look <item>` where the name is already implied by having typed
# it. Those two uses want different text, and the room listing was quietly
# using the wrong one.
#
# Only a curio still capable of being picked up needs its name prefixed back
# on -- a curio that's been given to the cat (cmd_give) is still tagged
# curio=True but its description was overwritten with a full, already
# self-naming trace ("a pinecone, well-battered after a game with the cat"),
# and cmd_give is the one place that un-portables a curio when it makes that
# trace. Prefixing the name again there would double it. portable is what
# tells the two states apart.
def _room_listing_line(e):
    if e.attrs.get("curio") and e.portable:
        return f"{e.name}, {e.description}"
    return e.description


# An LLM hand reached for "look actions" more than once -- a plausible-
# sounding guess, since there's no entity named "actions" to find; the word
# is just its own free verb (cmd_actions). Honoring the guess is simpler
# than fighting it.
def cmd_look(world, actor, arg):
    """look [thing] -- describe the room, or examine one thing (dark hides all but what you hold); "look actions" works the same as "actions"."""
    if arg and arg.strip().lower() == "actions":
        return cmd_actions(world, actor, "")
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
                f"light — a lamp kindled at the hearth would do, or you could "
                f"wait for dawn. Somewhere out there the world goes on "
                f"regardless.\n\n{_carried_line(world, actor)}")
    lines = [f"[{stamp}]  {room.name.upper()}", room.description]
    here = [e for e in _room_here(world, actor, room) if e.id != actor.id]
    if here:
        lines += [""] + [f"  - {_room_listing_line(e)}" for e in here]
    if room.exits:
        lines += ["", "Exits: " + ", ".join(
            _exit_label(room.id, d) for d in room.exits)]
    lines += ["", _carried_line(world, actor)]
    return "\n".join(lines)


def cmd_go(world, actor, arg):
    """go <exit> -- move through a named exit (you can also just type the exit name; "inside" works anywhere "in" does)."""
    room = world.get(actor.location)
    key = arg.lower().strip()
    key = _DIRECTION_ALIASES.get(key, key)
    dest = room.exits.get(key)
    if not dest:
        return f"You can't go {arg or 'that way'}."
    actor.location = dest
    return cmd_look(world, actor, "")


def cmd_take(world, actor, arg):
    """take <thing> -- pick up a portable object."""
    # BUG WE HIT: with one stone already carried and more of the same name
    # still sitting on the shelf, `take a smooth grey stone` again reported
    # "already carrying" -- find_visible's default order is here + carried +
    # displayed, so once a match is carried it sorts ahead of any other still
    # -available copy of the same name (room OR shelf). `take`'s whole point
    # is getting a copy into your hands, so it must prefer one that ISN'T
    # already there; only fall back to an already-carried match (and the
    # refusal that follows) once no other copy is left to take.
    e = find_visible(world, actor, arg, prefer=lambda x: x.location != actor.id)
    if not e:
        return f"There's no '{arg}' here to take."
    if e.location == actor.id:
        return f"You're already carrying {_the(e.name)}."
    if not e.portable:
        return f"The {e.name} won't budge."
    surface = world.get(e.location)
    e.location = actor.id
    if surface is not None and surface.attrs.get("display_surface"):
        # cmd_place recomputes this on the way onto the shelf; taking
        # something back off it needs the same refresh, or the shelf goes
        # on describing itself as still holding what's already been carried
        # away.
        surface.description = _shelf_description(world, surface)
    return f"You take {_the(e.name)}."


def cmd_drop(world, actor, arg):
    """drop <thing> -- set down something you're carrying."""
    e = find_visible(world, actor, arg, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    e.location = actor.location
    return f"You set down {_the(e.name)}."


# The shelf is deliberately capped, unlike the cairn. The cairn already is
# the "everything, forever, anonymous" answer to what to do with a found
# curio -- a second unlimited container doing the same job would be
# redundant. Capping the shelf turns it into the cairn's opposite: personal
# and curated rather than collective and boundless. Nothing decays and
# nothing's punished for being full -- a hand just has to decide whether a
# new find is worth a spot, the same kind of small, real, freely-chosen
# choice as everything else on the calm axis. `take` (already existing,
# no new mechanic) is how a hand makes room.
SHELF_CAPACITY = 10


def _shelf_description(world, shelf):
    """Describe the shelf as a small, visible record of what hands kept."""
    items = world.contents(shelf.id)
    if not items:
        return "a narrow curio shelf, empty but for a little dust"
    full = ", full up" if len(items) >= SHELF_CAPACITY else ""
    return (f"a narrow curio shelf{full}, holding: "
            + ", ".join(e.name for e in items))


_PUT_WOOD_IN_HEARTH = {
    "wood in hearth", "wood in the hearth", "wood on hearth", "wood on the hearth",
}


def cmd_place(world, actor, arg):
    """place <thing> [on shelf] -- set a carried object on the hut's curio shelf (holds up to 10 at once); "put wood in hearth" is an alias for "add wood" (two hands independently reached for it)."""
    if arg.lower().strip() in _PUT_WOOD_IN_HEARTH:
        return cmd_add_wood(world, actor, "")
    shelf = next((e for e in world.contents(actor.location)
                  if e.attrs.get("display_surface")), None)
    if not shelf:
        return "There's nowhere here to set that out. The shelf is in the hut."
    if len(world.contents(shelf.id)) >= SHELF_CAPACITY:
        return ("The shelf's full -- ten small things already set out. Take "
                "something back if you want room for this one.")
    item_name = arg.lower().strip()
    if item_name.endswith(" on shelf"):
        item_name = item_name[:-len(" on shelf")].strip()
    e = find_visible(world, actor, item_name, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    e.location = shelf.id
    shelf.description = _shelf_description(world, shelf)
    return f"You set {_the(e.name)} on the shelf."


# The give-to-cat reaction and the durable trace it leaves behind, keyed by
# the curio's own cat_reaction. The gesture matters regardless of which
# fires -- see cmd_give's docstring and the reset-or-richer invariant it
# guards: either way the thing is gone from the pack and the world is one
# thing richer, never reset.
_CAT_GIVE_REACTIONS = {
    "plays": "{cap} pounces on {thing}, batting it round before losing interest.",
    "ignores": "{cap} sniffs {thing} once, unimpressed, and stalks off.",
}
_CAT_GIVE_TRACES = {
    "plays": "{name}, well-battered after a game with the cat",
    "ignores": "{name}, given to the cat and roundly ignored",
}


def cmd_give(world, actor, arg):
    """give <thing> to cat -- hand a carried curio to the cat; it plays with some and ignores others, but the gesture always leaves its mark."""
    if not arg:
        return "Give what to the cat? e.g.  give pinecone to cat"
    cat = world.get("cat")
    if cat is None or cat.location != actor.location:
        return "There's no cat here to give that to."
    item_name = arg.lower().strip()
    if " to " in item_name:
        item_name = item_name.split(" to ", 1)[0].strip()
    e = find_visible(world, actor, item_name, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    if not e.attrs.get("curio"):
        return "That's not something to give the cat like this -- food goes through `feed cat`."
    reaction = e.attrs.get("cat_reaction", "ignores")
    cap, thing, name = _cat_cap(cat), _the(e.name), e.name
    e.location = actor.location
    e.portable = False
    e.description = _CAT_GIVE_TRACES[reaction].format(name=name)
    return _CAT_GIVE_REACTIONS[reaction].format(cap=cap, thing=thing)


def cmd_inventory(world, actor, arg):
    """inventory -- list what you're carrying and how hungry you feel."""
    names = _carried_names(world, actor)
    head = actor_hunger_line(actor)
    if not names:
        return head + "\nYour hands are empty."
    return head + "\nYou are carrying:\n" + "\n".join(f"  - {n}" for n in names)


def cmd_actions(world, actor, arg):
    """actions -- list the things you can do from here right now."""
    return "Available actions:\n" + "\n".join(
        f"  - {action}" for action in world.available_actions(actor))


# A dark night is mostly `wait` -- there's little else safe to do out there,
# and that's correct. But a flat "You wait. Time passes." said turn after
# turn reads as a lockout, when the mechanics underneath are just an
# ordinary quiet stretch. A small pool of quiet lines -- drawn only once
# it's actually dark -- makes the identical night atmospheric instead of
# blank. The last line hints dawn is on its way, so the wait reads as a
# night being gotten through, not an open-ended void.
WAIT_DARK_LINES = (
    "You wait. Far off, one sound, then nothing. The dark keeps to itself.",
    "You wait. The cold settles in properly. Nothing else moves.",
    "You wait. The dark feels a shade thinner than it did. Not yet, but coming.",
)

# Only true indoors, where there's a hearth and a doorway to feel the cold
# come up through the floor from -- said outside, at the yard or the
# forest's edge, it would describe furniture that isn't there.
WAIT_DARK_HUT_LINES = (
    "You wait. The cold comes up through the floor; the doorway is a faint grey square.",
    "You wait. The hearth ticks as the last of its warmth leaves it.",
)

# Only when the cat is actually in the room to be heard -- {cat} follows
# _cat_cap's given-name-or-"The cat" convention, so a named cat gets named.
WAIT_DARK_CAT_LINE = "You wait. Somewhere in the dark, {cat} shifts and resettles."


def _wait_dark_lines(world, actor):
    lines = list(WAIT_DARK_LINES)
    if actor.location == "hut":
        lines += WAIT_DARK_HUT_LINES
    cat = world.get("cat")
    if cat is not None and cat.location == actor.location:
        lines.append(WAIT_DARK_CAT_LINE.format(cat=_cat_cap(cat)))
    return lines


def cmd_wait(world, actor, arg):
    """wait -- let one tick pass while you do nothing."""
    if world.is_dark(actor.location):
        return world.rng.choice(_wait_dark_lines(world, actor))
    return "You wait. Time passes."


def _kindle_lamp(world, actor, lamp):
    """The lamp's own kindling logic: needs a lit hearth to catch from, tops
    an already-lit lamp back to full rather than refusing (a deliberate way
    to top up before a night)."""
    hearth = find_visible(world, actor, "hearth")
    if not hearth:
        return "Nothing out here to kindle from. The fire's inside."
    if not hearth.attrs.get("lit"):
        return "The hearth is dark — there's no fire to catch. Feed it first."
    already_lit = lamp.attrs.get("lit", False)
    lamp.attrs["lit"] = True
    lamp.attrs["fuel"] = LAMP_FUEL_START
    lamp.description = _lamp_description(lamp)
    if already_lit:
        return "You dip the wick to the embers again; the flame steadies to full."
    return "You tip the wick to the embers until it catches. The lamp wakes, warm and yellow."


def cmd_light(world, actor, arg):
    """light <thing> -- set a fuel source burning (the hearth cooks); light lamp / kindle lamp lights the tin lamp from a lit hearth."""
    e = find_visible(world, actor, arg)
    if e is not None and e.id == "lamp":
        return _kindle_lamp(world, actor, e)
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
    e.description = _lamp_description(e) if e.id == "lamp" \
        else e.attrs.get("unlit_desc", f"the {e.name}, unlit")
    return f"You pinch out the {e.name}."


def cmd_plant(world, actor, arg):
    """plant <potato|seed> -- press a raw potato into the vegetable patch, or set the seed you found in the ground by the fence."""
    e = find_visible(world, actor, arg or "potato", prefer=_is_raw)
    if e is not None and e.attrs.get("seed") and _carrying(world, actor, e):
        return _plant_seed(world, actor, e)
    if not e or e.location != actor.id or "potato" not in e.name \
            or e.attrs.get("food", 0) > 0:
        return "You need a raw potato in hand to plant."
    patch = _patch_in(world, actor.location)
    if not patch:
        return "There's no turned soil here to plant in."
    if world.contents(patch.id):
        return "Something's already growing here. Let it finish first."
    world.entities.pop(e.id, None)
    _sow(world, patch)
    return "You press the potato into the soil and firm it down. Now: time."


def _plant_seed(world, actor, seed):
    """The mystery seed's own planting path -- entirely independent of the
    patch and its one-crop-at-a-time rule (that rule is load-bearing and
    the seed must never touch it; this creates a freestanding entity in the
    yard, never anything inside the patch). One mystery plant at a time,
    mirroring the potato's own restraint -- one anticipation arc per
    lineage, not a flowerbed to manage."""
    if actor.location != "yard":
        return "The seed wants proper ground -- plant it in the yard."
    if _mystery_plant(world) is not None:
        return "Something's already coming up by the fence. Let it finish first."
    world.entities.pop(seed.id, None)
    kind = world.rng.choice(BLOOM_KINDS)
    plant = world.add(Entity(world.fresh_id("bloom"), "seedling",
        _bloom_description(0), location="yard", portable=False,
        attrs={"growth": 0, "blooms_at": BLOOM_TICKS,
               "bloom_name": kind[0], "bloom_look": kind[1],
               "bloom_reaction": kind[2]}))
    plant.attach("blooming")
    return "You press the seed into the ground by the fence. It will take what it takes."


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


BUCKET_CAPACITY = 5


def cmd_draw(world, actor, arg):
    """draw water -- fill the bucket from the well (holds up to its capacity)."""
    well = find_visible(world, actor, "well")
    if not well:
        return "There's no well here to draw from."
    bucket = find_visible(world, actor, "bucket")
    if not bucket:
        return "There's no bucket here to fill."
    if bucket.attrs.get("water", 0) >= BUCKET_CAPACITY:
        return f"The bucket is already full ({BUCKET_CAPACITY})."
    bucket.attrs["water"] = BUCKET_CAPACITY
    return f"You draw water from the well. The bucket now holds {BUCKET_CAPACITY}."


def cmd_water(world, actor, arg):
    """water crop -- pour a bucket's stored water onto the planted crop here."""
    crop = _crop_in(world, actor.location)
    if not crop:
        return "There's nothing planted here to water."
    bucket = find_visible(world, actor, "bucket")
    if not bucket or bucket.attrs.get("water", 0) <= 0:
        return "The bucket's empty. Draw water from the well first."
    bucket.attrs["water"] -= 1
    crop.attrs["watered"] = crop.attrs.get("watered", 0) + 1
    return "You pour water over the soil. The crop drinks it in."


WOOD_PER_GATHER = 3          # a little more than one night's worth, to stock up
FUEL_PER_WOOD = HEARTH_FUEL_START    # one add wood restores a full night's fuel

# Small, purely cosmetic finds forest_finds (above) can turn up. Each is
# (name, look_line, cat_reaction): look_line is a bare, odd, specific
# fragment -- not a summary sentence -- assembled into a full description by
# _found_description below. cat_reaction ("plays"/"ignores") drives both the
# look-line's optional cat hint and what `give <thing> to cat` does with it;
# see the invariant at cmd_give: this shelf/give pairing is the world's calm
# axis, and neither affordance may touch a maintenance resource (fire, food,
# water) -- only ever leave the world one durable thing richer.
FOUND_ITEMS = (
    ("a pinecone", "tight and resinous, one scale broken", "plays"),
    ("a small brown feather", "barred, downy at the quill", "plays"),
    ("a smooth grey stone", "river-worn, a pale band round its middle", "ignores"),
    ("a pebble of blue glass", "sea-frosted, edges gone soft", "ignores"),
    ("a bone button", "four holes, one thread still knotted through", "ignores"),
    ("a jay's feather", "blue-black, sharply barred, one edge gone soft", "plays"),
    ("a knot of bleached twine", "sun-bleached, knotted twice, frayed at both ends", "plays"),
    ("a curl of birch bark", "curled tight, papery, peels if you're not careful", "ignores"),
    ("a sprig of dried moss", "dry and soft, crumbles a little at the edges", "ignores"),
)


# `stack stone on cairn` has worked since Stage 7, but the cairn was only
# ever named in the forest-edge room text -- a cue a hand loses the moment
# they carry a stone anywhere else. Observed in play: the shelf filled with
# duplicate stones while the cairn barely grew. The fix is to put the cue on
# the stone itself, the same way the shelf always describes its own held
# capacity regardless of where a hand stands -- see ARCHITECTURE.md's
# "Stone -> cairn legibility" note. Named directly: unlike the statue, the
# cairn is a real mechanic, so there's no reason to euphemize it.
STONE_CAIRN_HINT = "it could go on the cairn at the forest's edge"


def _found_description(look_line, reaction, name=""):
    """Assemble a curio's full description from its bare look_line -- adding
    the cat hint only for a cat_reaction of "plays" (only those finds are
    worth a cat's attention), and the cairn hint for anything named a stone
    (only found stones have one, and no other curio has a cairn-equivalent
    yet). `name` defaults to "" so existing call sites that never mention a
    stone see byte-identical output to before this hint existed."""
    text = look_line
    if reaction == "plays":
        text += " — the cat might bat at it"
    if "stone" in name.lower():
        text += f" — {STONE_CAIRN_HINT}"
    return text + "."


# ---------------------------------------------------------------------------
# The mystery seed -- the first thing in Emberworld where one hand changes
# what a LATER hand can do, rather than what they can read about. A seed
# found at the forest's edge, planted in the yard, that takes longer to
# bloom than any one visit lasts and opens for whoever happens to be around
# when it does -- planter or stranger. Adds no new verbs: `plant` learns a
# second thing to plant, and once bloomed the flower is just an ordinary
# portable/curio, picked up and shelved by the verbs that already exist.
SEED_NAME = "a seed you don't recognise"

# The core decision, pinned by test_a_bloom_outlives_a_single_visit so a
# future "this feels slow" edit has to argue with an assertion, not just a
# comment: this must exceed a visit (~30 turns), or the planter starts
# seeing their own bloom and the whole multi-visit point collapses into a
# slow potato. 120 ticks is 5 world-days, ~4 visits -- comfortably past one
# visit, short enough that a dozen-visit lineage sees several open. If this
# ever drops below ~72 ticks, re-read this comment before touching it.
BLOOM_TICKS = 120
BLOOM_SHOWING_AT = 30       # growth at which anything is visible above ground
BLOOM_BUDDING_AT = 84       # growth at which it's clearly about to be something

# Mid-arc description, banded like CAIRN_BANDS/_cairn_description -- most
# hands who meet this thing meet it here, not at either end, so the middle
# bands matter as much as the payoff.
BLOOM_BANDS = (
    (0, "a patch of turned earth by the fence, nothing showing yet"),
    (BLOOM_SHOWING_AT, "something is coming up by the fence, its shape not clear yet"),
    (BLOOM_BUDDING_AT, "a green stalk by the fence, a bud closed tight at the top of it"),
)


def _bloom_description(growth):
    text = BLOOM_BANDS[0][1]
    for threshold, line in BLOOM_BANDS:
        if growth >= threshold:
            text = line
    return text


# What it becomes -- fixed the instant it's planted, hidden until it opens.
# Shaped exactly like FOUND_ITEMS (name, look_line, cat_reaction) for the
# same reason: the look_line feeds _found_description, and cat_reaction is
# set explicitly on the bloom at open time rather than left to
# ensure_shelf's FOUND_ITEMS-only backfill (which only ever touches
# "found_"-prefixed entities and would silently default any of these to
# "ignores"). A FIXED tuple, deliberately not composed from pools the way a
# forest fragment is: fragments are composed because they fire every step
# and need combinatorial depth to survive repetition; a bloom opens roughly
# once every four visits and gets read closely when it does. A handful of
# flowers that each read like a real specific thing beats a mad-libs
# generator with more permutations -- composition is the right tool for
# texture that repeats, not for a payoff that doesn't.
BLOOM_KINDS = (
    ("a tall white flower", "taller than it should be, six narrow petals, "
     "and a scent like cold water", "plays"),
    ("a low blue flower", "close to the ground, the blue so dark it reads "
     "black at the centre", "ignores"),
    ("a rust-red flower", "ragged-edged petals, the colour of old iron left "
     "out in rain", "ignores"),
    ("a papery yellow flower", "thin as a moth's wing, rattling faintly "
     "when the wind moves it", "plays"),
    ("a single black bloom", "glossy, almost wet-looking, and colder to the "
     "touch than it has any business being", "ignores"),
    ("a spray of small pink flowers", "a dozen tiny blooms crowded on one "
     "stem, each one barely open", "plays"),
    ("a green-throated flower", "white on the outside, a deep green flare "
     "hidden at the centre", "ignores"),
    ("a striped orange flower", "bold bands of colour, the kind of thing "
     "that looks painted on", "plays"),
)


def _seed_in_world(world):
    """The one still-unplanted seed, if one exists anywhere -- carried,
    shelved, or lying on the ground. Used by seedfall to decide whether the
    forest's edge has anything left to offer."""
    return next((e for e in world.entities.values() if e.attrs.get("seed")), None)


def _mystery_plant(world):
    """The one mystery-seed plant, growing or already bloomed, if one
    exists -- or None. `blooms_at` is unique to this plant kind (the
    potato plant's own growth attrs are `ripe_at`), so this is a plain
    attrs check, the same shape as _crop_in's patch-containment check,
    not an id-prefix guess."""
    return next((e for e in world.entities.values() if "blooms_at" in e.attrs), None)


def seedfall(world, room):
    """Autonomous: while nothing of the seed's arc is in play anywhere in
    the world -- no seed carried, shelved, or lying about, and no mystery
    plant growing or bloomed in the yard -- the forest's edge offers one to
    the next hand who stands here. Deterministic, like patch_volunteer,
    not a dice roll: the arc is already slow (a multi-visit bloom), and
    stacking a rare find on top of a multi-visit wait compounds two long
    odds into content that mostly doesn't happen. The floor is
    self-limiting on its own -- the world holds one token of the arc at a
    time, so no second seed appears until the first one's arc completes."""
    actor = world.get("you")
    if actor is None or actor.location != room.id:
        return
    if _seed_in_world(world) is not None or _mystery_plant(world) is not None:
        return
    world.add(Entity(world.fresh_id("seed"), SEED_NAME,
                      "small, dark, and ridged — not a potato, and not "
                      "anything else you can name.",
                      location="forest_edge", portable=True,
                      attrs={"seed": True}))
    world.announce("Something small and hard is half-buried at the "
                    "treeline — not anything you planted.", room.id)


def blooming(world, plant):
    """Autonomous: a planted seed comes up on its own schedule and
    eventually opens. Deliberately NOT `growing`: there is no
    watered/boosted branch and there must never be one -- the whole point
    of this arc is that a hand cannot hurry it, so the absent water path
    is the feature, not an oversight. Do not unify these two behaviors."""
    if plant.attrs.get("ready"):
        return
    plant.attrs["growth"] = plant.attrs.get("growth", 0) + 1
    if plant.attrs["growth"] >= plant.attrs["blooms_at"]:
        plant.attrs["ready"] = True
        plant.name = plant.attrs["bloom_name"]
        plant.portable = True
        plant.attrs["curio"] = True
        plant.attrs["cat_reaction"] = plant.attrs["bloom_reaction"]
        plant.description = _found_description(plant.attrs["bloom_look"],
                                                plant.attrs["bloom_reaction"])
        world.announce(f"By the fence, {plant.name} has opened.",
                       world.room_of(plant))
    else:
        plant.description = _bloom_description(plant.attrs["growth"])


BEHAVIORS.update({"seedfall": seedfall, "blooming": blooming})


# FOREST_SPEC.md Stage 7: wood-gathering relocated here from the yard (the
# yard goes back to being just the yard). Deliberately carries no find-roll
# of its own -- forest_finds already fires on any tick spent at the
# forest's edge, gather-wood turns included, so a second roll stacked on
# top would double the effective find chance right here, exactly the
# intensification the relocation spec ruled out. This is still the
# grandfathered hearth-fuel loop; only where it happens moved.
def cmd_gather(world, actor, arg):
    """gather wood -- forage the forest's edge for fallen branches and deadfall."""
    if actor.location != "forest_edge":
        return "There's nothing to forage here -- try the forest's edge."
    actor.attrs["wood"] = actor.attrs.get("wood", 0) + WOOD_PER_GATHER
    return (f"You gather fallen branches and deadfall from the forest floor. "
            f"You now have {actor.attrs['wood']} wood.")


def cmd_add_wood(world, actor, arg):
    """add wood -- feed carried firewood into the hearth, raising its fuel (offered even with none carried, so the refusal teaches where it comes from)."""
    hearth = find_visible(world, actor, "hearth")
    if not hearth:
        return "There's no hearth here to feed."
    if actor.attrs.get("wood", 0) <= 0:
        return "You've no wood. It comes from the forest's edge."
    actor.attrs["wood"] -= 1
    hearth.attrs["fuel"] = hearth.attrs.get("fuel", 0) + FUEL_PER_WOOD
    if hearth.attrs.get("lit"):
        return "You feed wood into the fire. It catches and burns brighter."
    return "You stack wood in the cold hearth, ready for a light."


# 75% of ACTOR_HUNGER_CAP (content_common.py), not the 40% it used to be --
# see that constant's own comment for the "one meal from the cap still
# left the nag firing" bug this fixes. Keep the two numbers read together;
# raising the cap without raising this in step reproduces the same bug at
# a different scale.
POTATO_FOOD_VALUE = 30


def cmd_cook(world, actor, arg):
    """cook potato -- broil a potato at a lit cooking fire, making it edible."""
    e = find_visible(world, actor, arg or "potato", prefer=_is_raw)
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
    e.attrs["food"] = POTATO_FOOD_VALUE
    return ("You bury the potato in the embers. Soon it's blistered and steaming."
            + _last_potato_beat(world, actor, consumed_was_raw=True))


def cmd_eat(world, actor, arg):
    """eat <thing> -- eat cooked food to ease your hunger."""
    e = find_visible(world, actor, arg, prefer=_is_cooked)
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


def _journal_missing_message(world):
    """The journal is portable, so a hardcoded 'it's in the hut' refusal
    would eventually be a confident lie. Look up wherever it actually is and
    say that instead -- and if it's somewhere with no specific clause yet,
    say so honestly rather than assert a specific wrong place."""
    journal = world.get("journal")
    loc = journal.location if journal else None
    if loc == "hut":
        return "You've no journal to hand. It's in the hut."
    if loc == "yard":
        return "You've no journal to hand. It's out in the yard."
    return "You've no journal to hand — it's not here with you."


def cmd_write(world, actor, arg):
    """write <note> -- add a line to the shared journal for future visitors."""
    journal = find_visible(world, actor, "journal")
    if not journal:
        return _journal_missing_message(world)
    if not arg:
        return "Write what? e.g.  write planted two potatoes near the fence."
    journal.attrs.setdefault("entries", []).append(f"{_day_stamp(world)} {arg}")
    return "You write in the journal. The ink dries slowly. It will keep."


# A lineage's journal only ever grows -- showing the whole thing on every
# read turns a quick catch-up into an ever-longer wall of past visits. The
# full history is never lost (still all in entries, and cmd_write always
# appends to it); only what a single `read journal` shows is capped.
JOURNAL_READ_LIMIT = 7        # the recent tail, always shown
JOURNAL_OLDER_SHOWN = 3       # entries drawn from further back, so the tail
                              # can never be the whole of a lineage's memory
JOURNAL_GAP = "..."           # marks where the view skipped over entries


def journal_view(entries, keep=JOURNAL_READ_LIMIT, older=JOURNAL_OLDER_SHOWN):
    """Which entries a hand actually sees: the first (it's the one that
    orients someone with no memory), then `older` drawn from across
    everything in between, then the last `keep`. Gaps are marked with
    JOURNAL_GAP so the view never pretends to be the whole record.

    BUG WE HIT: this used to be a plain tail. In real play a stretch of
    visits where every hand hit the same trouble wrote the same warning
    over and over, and the tail meant an arriving hand inherited nothing
    BUT those warnings -- so it wrote another one, and the journal locked
    itself into a single register for a week of world-time. The journal is
    the strongest thing in this world for setting how a visit feels, and a
    pure-recency window hands that entirely to whatever the last few hands
    happened to be going through. Reaching back across the whole history is
    what stops any one stretch of it becoming all of it.

    Deliberately deterministic -- spans, and the middle of each span, not a
    random draw. Two reasons: a hand who reads twice must see the same
    thing (the LLM driver's prompt tells it the journal "won't change" once
    read), and a book doesn't reshuffle which pages fall open. The picks
    still move as the journal grows, because the spans do.

    Deliberately blind to what the entries SAY. Choosing them by content --
    biasing away from whatever the recent ones are about -- would work, and
    would quietly make us the editor of what the lineage remembers. Position
    is ours to choose; meaning isn't."""
    entries = list(entries)
    if len(entries) <= keep + older:
        return entries
    tail = entries[-keep:]
    middle = entries[1:-keep]
    out, taken = [entries[0]], 0
    span = len(middle) / older if older else 0
    for i in range(older):
        idx = min(int(i * span + span / 2), len(middle) - 1)
        if idx < taken:                   # spans this short can collide
            continue
        if idx > taken:
            out.append(JOURNAL_GAP)
        out.append(middle[idx])
        taken = idx + 1
    if len(middle) > taken:
        out.append(JOURNAL_GAP)
    return out + tail


def cmd_read(world, actor, arg):
    """read journal -- read the journal (needs light unless you're holding it); shows a spread of entries rather than all of them, and `read journal all` shows the lot."""
    arg = (arg or "").strip()
    show_all = arg.lower() == "all" or arg.lower().endswith(" all")
    if show_all:
        arg = arg[:-len("all")].strip()
    journal = find_visible(world, actor, arg or "journal")
    if not journal or "entries" not in journal.attrs:
        return "There's nothing written there."
    if world.is_dark(actor.location) and not _carrying(world, actor, journal):
        return "Too dark to read. Pick it up, or bring a light."
    entries = journal.attrs["entries"]
    if not entries:
        return "The journal is blank, waiting for someone's first entry."
    if show_all:
        return ("The journal reads, all of it:\n"
                + "\n".join(f"  {ln}" for ln in entries))
    shown = journal_view(entries)
    header = "The journal reads:"
    written = [ln for ln in shown if ln != JOURNAL_GAP]
    if len(written) < len(entries):
        header = (f"The journal reads ({len(written)} of {len(entries)} "
                   f"entries, spread across its whole run -- "
                   f"`read journal all` for the rest):")
    return header + "\n" + "\n".join(f"  {ln}" for ln in shown)



# The forest's-edge calm affordance -- pacing rebalance, change 3. THE
# CONSTRAINT THAT MUST NEVER BREAK: listen grants nothing, ever. No reward,
# no rested-state, no find-chance bump, no progress, no accumulation of any
# kind. The instant it grants anything it becomes a chore done for payoff and
# collapses back into the acquisition loop this whole rebalance fights --
# see the calm-axis invariant in README.md. It lives on the tea-and-petting
# side of that invariant: freely chosen, unpressured, mark-free. A varied
# line pool (not one fixed line) is what lets it survive repeat use --
# see test_listen_returns_varied_lines_not_always_the_same_one.
LISTEN_LINES = (
    "Somewhere in the high branches, a bird you can't see runs through its "
    "small song and falls quiet.",
    "Wind moves through the tops of the trees, a long slow breath, and settles.",
    "The quiet here has a texture to it -- the yard's sounds gone, nothing "
    "yet in their place.",
    "A wood-pigeon calls once, far off, and doesn't call again.",
    "Light comes down through the leaves in shifting coins. You watch them move.",
    "From the black between the trunks, a cold breath of air -- the deep "
    "forest, breathing out. Not yet.",
)


# Calm-axis session acknowledgment. Session-scoped (see world.calm_visits),
# never saved: how many times THIS hand has chosen a calm act at a given calm
# spot this visit. "listen" and "watch clouds" share one counter at the
# forest's edge -- keyed by spot, not by verb -- because this is tracking
# chosen presence, not mastery of one command; a future calm verb there (e.g.
# a "look at flowers") should feed the same counter. Only the forest's edge
# gets this: it's the one place nothing forces a hand to visit, so repeat
# presence there actually means something chosen. The yard is constant
# through-traffic for chores, so counting visits there would just be counting
# the forced loop, not calm -- watch_clouds in the yard stays untouched.
# Fires exactly once, at the third calm act, and never again this visit: not
# a running status, not a buff, no confirmation of anything beyond that one
# line -- same discipline as listen/watch_clouds granting nothing, one size
# smaller. See test_calm_visit_ack_fires_once_on_the_third_calm_act_and_never_again.
CALM_ACK_AT = 3
CALM_ACK_LINE = " You're getting to know this stretch of quiet."


def _calm_visit_ack(world, spot):
    world.calm_visits[spot] = world.calm_visits.get(spot, 0) + 1
    if world.calm_visits[spot] == CALM_ACK_AT:
        return CALM_ACK_LINE
    return ""


def cmd_listen(world, actor, arg):
    """listen -- stop and take in the forest's edge; a chosen, unpressured turn that changes nothing (only at the forest's edge)."""
    if actor.location != "forest_edge":
        return "There's nothing in particular to listen for here. Try the forest's edge."
    return world.rng.choice(LISTEN_LINES) + _calm_visit_ack(world, "forest_edge")




# FOREST_SPEC.md Stage 7 -- the statue: randomly discovered, not placed at a
# fixed depth, so it can never become a coordinate on an authored map (the
# whole reason Stages 2-6 built texture instead of rooms). Below
# STATUE_MIN_DEPTH it cannot appear at all -- a deep-visit thing, not a
# short-trip accident. Beyond that floor, each venture carries a small
# independent chance of surfacing it. Once found this session,
# statue_found_this_session (session-scoped, alongside forest_depth --
# declared in world.py) means it won't flicker in and out of existence on
# repeated ventures, and a hand can wish at it again later in the visit
# from anywhere deep enough, without needing the exact depth it first
# appeared at.
STATUE_MIN_DEPTH = 3
STATUE_DISCOVERY_CHANCE = 0.25   # was 0.15; real play found the wait too long.
                                  # STATUE_MIN_DEPTH stays untouched -- that's
                                  # what keeps it "a deep-visit thing," this is
                                  # just the odds once you're already there.

# The one deliberate hint that wishing is even possible here -- but framed
# as something the place itself suggests, not a claim of prior knowledge
# (a fresh hand hasn't actually "heard" anything) and not an invitation from
# anyone listening. Same folk-magic register as "a coin tossed in a
# fountain" already used in README's wishing-statue design notes: other
# people have done this, for whatever reason people do -- never a promise
# that doing it here works, or that anything hears you. THE LINE THAT MUST
# NEVER APPEAR: anything implying the statue listens, grants, or is aware.
STATUE_DISCOVERY_TEXT = (
    " Between two trunks stands something that isn't a tree -- a weathered "
    "stone figure, worn past recognizing, moss thick in its folds. However "
    "long it's stood here, it was long before you. Something about it makes "
    "you think people have stood here and wished for things, the way you'd "
    "toss a coin in a fountain."
)

# THE CONSTRAINT THAT MUST NEVER BREAK: the statue stays mechanically
# inert. Lore says it grants; mechanics grant nothing; if anything is ever
# granted, it happens invisibly, later, by us -- never by this verb. The
# instant `wish` visibly does something, it stops being mechanic-free,
# wants aimed at it become performance, and it becomes the very god this
# design exists to avoid. See README's "wishing-statue" section.
STATUE_WISH_LINE = "The stone takes your wish and says nothing. Whatever you asked, it keeps."


def ensure_statue(world):
    """Create the statue's persistent record the first time it's actually
    needed -- lazily, unlike ensure_shelf/ensure_cairn, since most visits
    (most whole lineages, even) may go a long time without ever finding it.
    Nothing else depends on this entity existing before then."""
    statue = world.get("statue")
    if statue is None:
        statue = world.add(Entity("statue", "statue",
            "a weathered stone figure, worn past recognizing, moss thick "
            "in its folds", location="forest_edge", portable=False,
            attrs={"wishes": []}))
    return statue


def _statue_reachable(world, actor):
    """Whether `wish` can do anything right now: the statue has to have
    been found THIS session, and the hand has to currently be deep enough
    to reach it again -- found once doesn't mean wishable from the edge."""
    return (getattr(world, "statue_found_this_session", False)
            and actor.location == "forest_edge"
            and world.forest_depth >= STATUE_MIN_DEPTH)


# The forest's two conditional presences (see _room_here). The statue is
# only here when it's reachable -- the same gate `wish` itself uses, so
# neither can be reached past the other. The cairn is a landmark AT the
# edge: step even one pace in and it's behind you.
PRESENCE_RULES["statue"] = _statue_reachable
PRESENCE_RULES["cairn"] = lambda world, actor: world.forest_depth == 0


def cmd_wish(world, actor, arg):
    """wish <something> -- speak a wish to the statue, deep in the forest; it changes nothing and confirms nothing, ever."""
    if not _statue_reachable(world, actor):
        return "There's nothing here to wish to."
    if not arg.strip():
        return "Wish for what? e.g.  wish for rain"
    statue = ensure_statue(world)
    statue.attrs.setdefault("wishes", []).append(f"{_day_stamp(world)} {arg.strip()}")
    return STATUE_WISH_LINE


# FOREST_SPEC.md Stage 1 -- the skeleton: a plain depth counter (world.forest_
# depth, declared in world.py alongside rng/strict) that venture/return move,
# with no risk yet. Both verbs stay gated to forest_edge for now, since it's
# still the only room a hand can act from -- depth describes how far past it
# they've pushed, not a place with its own exits.
def cmd_venture(world, actor, arg):
    """venture -- push a little further into the forest, past the edge."""
    if actor.location != "forest_edge":
        return "There's nowhere to venture from here -- try the forest's edge."
    world.forest_depth += 1
    discovery = ""
    if (not world.statue_found_this_session
            and world.forest_depth >= STATUE_MIN_DEPTH
            and world.rng.random() < STATUE_DISCOVERY_CHANCE):
        world.statue_found_this_session = True
        discovery = STATUE_DISCOVERY_TEXT
    # Composition order (FOREST_SPEC.md cross-cutting requirement):
    # discovery text leads, then ambient -- off-course doesn't apply to
    # venture, only return, so this is the full order for this verb.
    return ("You push on, deeper into the trees. "
            + describe_forest(world.forest_depth, world.rng)
            + discovery
            + _forest_ambient(world.rng))


# FOREST_SPEC.md Stage 4 -- getting lost: a bounded, opt-in risk. Below
# SAFE_DEPTH_THRESHOLD, return is always exact -- airtight, since it's the
# safety guarantee for a short, casual dip in (see
# test_return_below_the_safe_depth_threshold_is_always_exact_even_under_a_forced_roll).
# Beyond it, each return carries a small independent chance of landing
# somewhere other than the expected depth-1 -- never past the edge (floor
# 0), and never at the expected depth itself, or it wouldn't read as
# off-course at all. No penalty beyond the mismatch: no damage, no lost
# items, no extra turn spent -- the disorientation IS the whole cost.
SAFE_DEPTH_THRESHOLD = 3
OFF_COURSE_CHANCE = 0.18

OFF_COURSE_LINES = (
    "You lose the thread among the trees for a moment.",
    "The way back blurs -- one stretch of trunks looks much like another.",
    "You second-guess a turn, and by the time you're sure, you've gone the wrong way about it.",
)


def cmd_return(world, actor, arg):
    """return -- fall back toward the forest's edge from wherever you've ventured (past a safe depth, this can land you somewhere other than expected)."""
    if actor.location != "forest_edge":
        return "There's nowhere to return from here."
    depth = world.forest_depth
    if depth <= 0:
        return "You're already back at the edge."
    # FOREST_SPEC.md Stage 5: a marked trail raises the safe floor above the
    # flat SAFE_DEPTH_THRESHOLD, up to the deepest depth marked this session
    # -- see cmd_mark_trail below.
    safe_to = max(SAFE_DEPTH_THRESHOLD, world.forest_mark_depth)
    if depth > safe_to and world.rng.random() < OFF_COURSE_CHANCE:
        expected = depth - 1
        new_depth = world.rng.choice([d for d in range(depth) if d != expected])
        world.forest_depth = new_depth
        lead = world.rng.choice(OFF_COURSE_LINES)
        if new_depth == 0:
            return (lead + " When the trees finally open up, you're back at "
                    "the edge already -- sooner than you expected, and not "
                    "quite sure how.")
        return lead + " " + describe_forest(new_depth, world.rng) + _forest_ambient(world.rng)
    world.forest_depth -= 1
    if world.forest_depth == 0:
        return "You retrace your steps and come back out at the forest's edge, the yard's quiet within reach again."
    return ("You fall back a step. " + describe_forest(world.forest_depth, world.rng)
            + _forest_ambient(world.rng))


# FOREST_SPEC.md Stage 5: trail-marking, a freely-chosen mitigation for
# Stage 4's risk -- so getting lost reads as a choice a hand can manage,
# not just a dice roll happening to them. Costs a turn like any real
# action, needs nothing consumable (no new resource dependency), and only
# ever raises the safe floor, never lowers it -- marking shallower than an
# existing mark is a harmless no-op, not a way to undo one.
def cmd_mark_trail(world, actor, arg):
    """mark trail -- mark your current depth in the forest as a safe checkpoint, so return only risks landing off-course beyond this point, not the whole way back."""
    if actor.location != "forest_edge":
        return "There's nowhere to mark a trail from here -- try the forest's edge."
    if world.forest_depth <= 0:
        return "There's nothing to mark at the edge itself."
    if world.forest_depth <= world.forest_mark_depth:
        return "You've already marked at least this deep."
    world.forest_mark_depth = world.forest_depth
    return "You mark this spot -- you'll know it again, however deep you go from here."


# listen's sibling -- the yard's (and forest's edge's) calm affordance, same
# THE CONSTRAINT THAT MUST NEVER BREAK as listen: grants nothing, ever. No
# rested-state, no buff, no find-chance, no progress. Costs a turn on
# purpose -- a chosen use of time is the whole point. Where it differs from
# listen: it reads the sky, so the line pool is keyed by daylight phase, and
# it's withdrawn outright at night rather than describing a fixed thing --
# there's nothing up there to see, so pretending otherwise would be a lie the
# dark-hides-the-room logic elsewhere in this file already refuses to tell.
WATCH_CLOUD_LINES = {
    "dawn": (
        "The early sky is streaked pink and grey, the colour lifting even "
        "as you look.",
        "Dawn cloud, edged in the first light, moving so slowly it might "
        "be still.",
    ),
    "day": (
        "High white clouds go over, in no hurry at all. You watch one "
        "pull slowly apart.",
        "The sky is doing almost nothing, very slowly, and it's enough to "
        "stand and watch it.",
        "A single cloud crosses the sun, the light dimming and brightening "
        "as it passes.",
    ),
    "dusk": (
        "The clouds have gone gold underneath, the light draining off the "
        "top of the sky.",
        "Evening is stacking the clouds in long grey banks, and the last "
        "brightness slips behind them.",
    ),
}

WATCH_CLOUDS_NIGHT_MSG = "The sky's gone to black -- nothing up there to watch for now."

# The one exception to the night withdrawal above. A real, uncontrollable
# clock the world keeps regardless of any hand's visits -- not tied to
# forest_depth or anything session-scoped, so it's the rare case where a
# hand can actually SEE that the world runs on a schedule bigger than any
# one visit. Purely descriptive, on purpose: it must never light the room
# (no free lamp-substitute) or change anything else -- same never-break
# constraint as the rest of this calm family, just gated by date instead of
# a dice roll.
MOON_CYCLE_DAYS = 29

# BUG WE HIT: unoffset, a fresh world's day 0 is a new moon by construction
# (day() % MOON_CYCLE_DAYS == 0 only on day 29), so a brand-new lineage was
# guaranteed roughly 23 blank visits before the moon was ever reachable at
# all -- and even after that first sighting, only one night in 29 ever
# showed anything. MOON_PHASE_OFFSET fixes the cold start (a real moon has
# an arbitrary phase at any given epoch; day 1 being a new moon was just an
# unexamined accident of counting from 0), and MOON_NEAR_NIGHTS fixes the
# narrow window (a few nights either side of full are still worth a look,
# not just the exact peak). Fixing only one of the two leaves it broken --
# see ARCHITECTURE.md's "visits, not days" note for the general shape of
# this class of bug.
MOON_NEAR_NIGHTS = 3
MOON_PHASE_OFFSET = 22   # first full moon lands on day 7 (visible from day
                         # 4, ~visit 3) instead of day 29 (~visit 23); chosen
                         # so day 1 sits at phase-distance 6, safely outside
                         # the near-window -- see test_watch_clouds_still_
                         # refuses_on_an_ordinary_night.

MOON_LINES = (
    "The moon stands full and close tonight, bright enough to throw a shadow.",
    "A full moon rides high, and for once the dark has an edge to it, silvered.",
    "Everything under the full moon reads in greys, sharp and unfamiliar.",
)

# The near-full nights either side of the peak -- their own weather, never a
# consolation prize for missing the full moon. A line that reads as a
# near-miss notification would make the widened window worse, not better:
# the rare thing would stop being rare, and what replaced it would just be
# a "not quite" notice. Nothing here references the full moon or implies
# anything was missed.
MOON_VIEW_LINES = {
    "waxing": (
        "The moon hangs half-built tonight, filling in night by night, not "
        "there yet.",
        "A fat, lopsided moon climbs the sky, close to round but not quite.",
        "The moon's got real shape tonight, though one edge still hasn't "
        "caught up.",
    ),
    "waning": (
        "The moon's started shrinking from one side, still bright but "
        "plainly less than it was.",
        "A moon well past its roundest rises late and sets early, thinner "
        "at the edge every night.",
        "The moon looks bitten into tonight, one flank gone dark, the rest "
        "still silver.",
    ),
}


def _moon_view(world):
    """Which moon, if any, is worth looking up at tonight: "full", "waxing",
    "waning", or None. Widened from a single full-moon night because one
    night in 29 -- of which a hand must also be outdoors, awake, and
    choosing to look -- is content that in practice never happens; see the
    comment above MOON_NEAR_NIGHTS/MOON_PHASE_OFFSET for the two separate
    faults this fixes."""
    n = (world.day() + MOON_PHASE_OFFSET) % MOON_CYCLE_DAYS
    if n == 0:
        return "full"
    if min(n, MOON_CYCLE_DAYS - n) > MOON_NEAR_NIGHTS:
        return None
    return "waning" if n <= MOON_NEAR_NIGHTS else "waxing"


def _is_full_moon(world):
    return _moon_view(world) == "full"


def cmd_watch_clouds(world, actor, arg):
    """watch clouds -- pause under open sky and watch the clouds (or, on a full or near-full moon night, the moon itself) move; a chosen, unpressured turn that changes nothing."""
    if actor.location not in ("yard", "forest_edge"):
        return "There's no open sky to watch here."
    phase = world.phase()
    if phase == "night":
        view = _moon_view(world)
        if view is None:
            return WATCH_CLOUDS_NIGHT_MSG
        line = world.rng.choice(MOON_LINES if view == "full" else MOON_VIEW_LINES[view])
    else:
        line = world.rng.choice(WATCH_CLOUD_LINES[phase])
    if actor.location == "forest_edge":
        line += _calm_visit_ack(world, "forest_edge")
    return line


# The forest-edge cairn -- a collective, permanent counterpart to the hut's
# shelf. The shelf is personal and reversible (a later hand can take an item
# back); a stone added here isn't -- it stops being anyone's the instant it
# joins the pile, and becomes part of something the whole lineage built, one
# stone at a time, that no single hand owns or can undo. Reset-or-richer
# taken to its most literal point: this can only ever grow.
CAIRN_ID = "cairn"
# cm added per stone. world.rng.choice, not .randint -- every rng stand-in
# used across the test suite (see _Unlucky, Cycle above) only implements
# .random()/.choice(), the same convention describe_forest's fragment draws
# already follow. A small range, not a fixed amount, so the number itself
# has a little texture rather than reading like a progress bar.
CAIRN_GROWTH_CM = (2, 3, 4, 5)

# Height read as prose, banded like the hearth's healthy/low/spent -- a felt
# sense of how tall it's gotten, not a digit to watch climb. Growing this
# tall takes many, many stones across many, many hands (stones are already
# rare finds) -- that slowness is the point: nobody who adds one stone will
# see it grow by much, only the lineage as a whole will.
#
# BUG WE HIT: band 0's text ("a good place to START a cairn") stayed up even
# after real stones had been added -- CAIRN_GROWTH_CM tops out at 2-5cm per
# stone, well under the old first threshold of 10cm, so two or three
# genuinely successful `stack stone` calls in a row could all land under 10
# and show the exact same "nobody's started yet" text, which is simply false
# the moment height_cm > 0. Added a band at 1cm -- height_cm is always >= 2
# after even one stone (CAIRN_GROWTH_CM's floor), so this band is guaranteed
# to catch the very first stone and say something true, while the slow
# climb to "ankle-high" and beyond is untouched.
CAIRN_BANDS = (
    (0, "a flat stone set into the ground here -- a good place to start a cairn"),
    (1, "a small pile of stones here -- maybe the start of a cairn"),
    (10, "the first few stones of a cairn, ankle-high"),
    (40, "a cairn, knee-high now"),
    (80, "a cairn, waist-high"),
    (130, "a cairn, shoulder-high -- taller than it has any right to be"),
    (190, "a cairn taller than anyone who's added to it, stone stacked on stone"),
)


def _cairn_description(height_cm):
    text = CAIRN_BANDS[0][1]
    for threshold, line in CAIRN_BANDS:
        if height_cm >= threshold:
            text = line
    return text


def ensure_cairn(world):
    """Add the forest-edge cairn to a world that predates it (fresh build or
    an older save) -- same backfill role as ensure_shelf.

    BUG WE HIT: a cairn's .description is a plain string, computed once by
    cmd_stack_stone and then just stored -- CAIRN_BANDS changing (as it did
    when the 1cm band was added) doesn't retroactively touch a description
    already sitting in a save. A save loaded after that change kept showing
    whatever text was current the last time a stone was actually stacked,
    not what its real height_cm now maps to, until someone happened to add
    another stone. Resyncing the description here, every load, means a
    change to the bands (or this same kind of drift from anywhere else)
    shows up the moment the world loads, not only on the next stack."""
    cairn = world.get(CAIRN_ID)
    if cairn is None:
        cairn = world.add(Entity(CAIRN_ID, "cairn", _cairn_description(0),
                                  location="forest_edge",
                                  attrs={"height_cm": 0}))
    else:
        cairn.description = _cairn_description(cairn.attrs["height_cm"])
    return cairn


def cmd_stack_stone(world, actor, arg):
    """stack stone [on cairn] -- add a carried stone to the cairn at the forest's edge, permanently; it's no longer yours once it joins the pile."""
    if actor.location != "forest_edge":
        return "There's no cairn here -- it's at the forest's edge."
    if world.forest_depth > 0:
        return "You're too deep in for the cairn -- it's back at the forest's edge."
    item_name = arg.lower().strip() or "stone"
    if item_name.endswith(" on cairn"):
        item_name = item_name[:-len(" on cairn")].strip() or "stone"
    e = find_visible(world, actor, item_name, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id or "stone" not in e.name.lower():
        return "You've no stone to add. One might turn up gathering wood, or lingering here."
    world.entities.pop(e.id, None)
    cairn = ensure_cairn(world)
    cairn.attrs["height_cm"] += world.rng.choice(CAIRN_GROWTH_CM)
    cairn.description = _cairn_description(cairn.attrs["height_cm"])
    return "You set the stone on the pile. Now: " + cairn.description


def cmd_save(world, actor, arg):
    """save -- write the world to disk (also happens automatically on quit)."""
    world.save()
    return f"The world settles into memory. ({SAVE})"


VERBS.update({
    "look": cmd_look, "l": cmd_look, "examine": cmd_look, "x": cmd_look,
    "go": cmd_go, "move": cmd_go,
    "take": cmd_take, "get": cmd_take, "grab": cmd_take,
    "drop": cmd_drop,
    "inventory": cmd_inventory, "i": cmd_inventory, "actions": cmd_actions,
    "wait": cmd_wait, "z": cmd_wait,
    "light": cmd_light, "kindle": cmd_light, "snuff": cmd_snuff,
    "plant": cmd_plant, "harvest": cmd_harvest,
    "cook": cmd_cook, "broil": cmd_cook, "eat": cmd_eat,
    "write": cmd_write, "read": cmd_read, "save": cmd_save,
    "draw": cmd_draw, "water": cmd_water, "place": cmd_place, "put": cmd_place,
    "gather": cmd_gather, "give": cmd_give, "listen": cmd_listen,
    "watch": cmd_watch_clouds, "venture": cmd_venture, "return": cmd_return,
    "mark": cmd_mark_trail, "wish": cmd_wish,
    # not "feed": that verb key is already cmd_feed (feeds the cat, in cat.py),
    # and the parser only looks at the first word -- "feed fire" would collide.
    "add": cmd_add_wood, "stoke": cmd_add_wood,
    "stack": cmd_stack_stone,
})
FREE_VERBS.update({"look", "l", "examine", "x", "inventory", "i", "actions", "read", "save"})


# ---------------------------------------------------------------------------
# What can be done here, right now. world.py owns the *shape* of this (see
# World.available_actions); everything below owns the answers, because every
# one of them turns on something Emberworld-specific -- a hearth, a crop, how
# deep into the trees someone has wandered.
#
# Each source returns the actions it alone is responsible for. Adding a
# feature means adding to the one that already owns its subject, or writing a
# new source beside it -- not editing a single 89-line function in the engine
# that knew about every room and object in the game at once, which is what
# this replaced.
#
# THE ONE RULE, unchanged: an action appears only when it can actually do
# something. Discoverability rides on this list, not on room prose. The lone
# deliberate exception is `add wood` -- see hearth_actions.
# ---------------------------------------------------------------------------
def core_actions(world, actor):
    """The always-theres: looking, waiting, the exits, and looking at or
    picking up whatever's in the room."""
    acts = ["look", "actions", "wait"]
    room = world.get(actor.location)
    for d in room.exits:
        acts.append(f"go {d}")
    for e in _room_here(world, actor, room):
        if e.id == actor.id:
            continue
        acts.append(f"look {e.name}")
        if e.portable:
            acts.append(f"take {e.name}")
    return acts


def garden_actions(world, actor):
    """Harvesting, and the well -> bucket -> crop watering chain."""
    acts = []
    room = world.get(actor.location)
    crop = _crop_in(world, room.id)
    if crop and crop.attrs.get("ready"):
        acts.append("harvest")
    if find_visible(world, actor, "well"):
        acts.append("draw water")
    bucket = find_visible(world, actor, "bucket")
    if crop and not crop.attrs.get("ready") and bucket and bucket.attrs.get("water", 0) > 0:
        acts.append("water crop")
    return acts


def forest_actions(world, actor):
    """Everything the forest's edge offers, including the depth-gated verbs.
    The only place outside this file's forest section that reads
    world.forest_depth/forest_mark_depth."""
    if actor.location != "forest_edge":
        return []
    carried = world.contents(actor.id)
    acts = ["gather wood", "listen", "venture"]
    if world.forest_depth > 0:
        acts.append("return")
        if world.forest_depth > world.forest_mark_depth:
            acts.append("mark trail")
    if world.forest_depth == 0 and any("stone" in e.name.lower() for e in carried):
        acts.append("stack stone on cairn")
    if _statue_reachable(world, actor):
        acts.append("wish <something>")
    return acts


def sky_actions(world, actor):
    """Watching the sky, wherever there's open sky to watch -- and at night
    only when there's a moon worth looking up at."""
    if actor.location in ("yard", "forest_edge") and (
            world.phase() != "night" or _moon_view(world) is not None):
        return ["watch clouds"]
    return []


def hearth_actions(world, actor):
    """Feeding the fire. Offered even with no wood carried -- the refusal
    ("it comes from the forest's edge") is how a hand learns the one causal
    chain it needs BEFORE it needs it, so this is the single place the
    "only offer what can do something" rule is wrong to apply. A hand that
    only discovers wood feeds the hearth once it already holds wood
    discovers it after dark, which is exactly too late."""
    if find_visible(world, actor, "hearth"):
        return ["add wood"]
    return []


def carrying_actions(world, actor):
    """What can be done with things in hand or in reach: putting them down,
    shelving them, lighting and snuffing them, eating them."""
    acts = []
    room = world.get(actor.location)
    here = _room_here(world, actor, room)
    carried = world.contents(actor.id)
    for e in carried:
        acts.append(f"drop {e.name}")
    shelf = next((e for e in here if e.attrs.get("display_surface")), None)
    if shelf:
        if len(world.contents(shelf.id)) < SHELF_CAPACITY:
            for e in carried:
                acts.append(f"place {e.name} on shelf")
        for e in world.contents(shelf.id):
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
    return acts


def making_actions(world, actor):
    """Putting something into the ground or onto the fire: the potato's
    plant/cook loop, and the mystery seed's one-way planting."""
    acts = []
    room = world.get(actor.location)
    here = _room_here(world, actor, room)
    carried = world.contents(actor.id)
    if any("potato" in e.name and e.attrs.get("food", 0) == 0 for e in carried):
        if _patch_in(world, room.id) and not _crop_in(world, room.id):
            acts.append("plant potato")
        if any(f.attrs.get("cooks") and f.attrs.get("lit") for f in here):
            acts.append("cook potato")
    if room.id == "yard" and any(e.attrs.get("seed") for e in carried) \
            and _mystery_plant(world) is None:
        acts.append("plant seed")
    return acts


def journal_actions(world, actor):
    """Reading and writing, wherever the journal happens to be -- it's
    portable, so this follows it rather than assuming the hut."""
    room = world.get(actor.location)
    here = _room_here(world, actor, room)
    if any(e.id == "journal" for e in here + world.contents(actor.id)):
        return ["read journal", "write <your note>"]
    return []


# Registered here, in one place and one deliberate order, rather than each
# module appending its own on import: this is a list, and the order a hand
# reads the actions in is part of the surface. cat_actions is defined in
# cat.py with the rest of the cat, and stays last, where it has always been.
ACTION_SOURCES.extend([
    core_actions, garden_actions, forest_actions, sky_actions,
    hearth_actions, carrying_actions, making_actions, journal_actions,
    cat_actions,
])



# ---------------------------------------------------------------------------
# Self-documenting reference. Built from the VERBS/BEHAVIORS registries and the
# world's own constants, so it can never drift out of sync with the code.
#   python3 emberworld.py --reference > REFERENCE.md
# A test asserts every verb and behavior carries a docstring, so nothing new
# can slip in undocumented.
# ---------------------------------------------------------------------------
def _first_line(fn):
    """The verb summary. Verb docstrings are a single physical line by
    convention and sometimes deliberately hold two sentences on purpose
    (`pet cat`'s "Accomplishes nothing; is the entire point." is the whole
    joke) -- so this must return the line verbatim, never truncate at a
    sentence boundary."""
    return (fn.__doc__ or "(undocumented)").strip().split("\n")[0]


def _first_sentence(fn):
    """The behavior summary. Unlike verbs, behavior docstrings are wrapped
    prose -- taking the literal first physical line (as _first_line does)
    routinely cuts a sentence off mid-clause. Join the lines back into one
    string and stop at the first sentence-ending period instead, so
    REFERENCE.md gets one complete thought. Falls back to the whole
    (whitespace-joined) docstring when there's no internal ". " to split
    on -- i.e. the docstring is already a single sentence."""
    doc = " ".join((fn.__doc__ or "(undocumented)").split())
    end = doc.find(". ")
    return doc if end == -1 else doc[:end + 1]


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
        out.append(f"- **{name}** -- {_first_sentence(fn)}")

    out += ["", "## World rules (from the code's own constants)", "",
            f"- A full day is **{DAY_LENGTH} ticks**; night falls late in that "
            "cycle and is pitch dark without a lit flame. A fresh world starts "
            "at dawn, giving a full day's light before the first night falls.",
            f"- The moon is a real clock, independent of anyone's visits: "
            f"**{2 * MOON_NEAR_NIGHTS + 1}** nights out of every "
            f"**{MOON_CYCLE_DAYS}** show something at night instead of "
            "nothing (full, or near enough), offset so a fresh lineage "
            "reaches one within its first week rather than its first month.",
            "- The tin lamp is the only portable light, kindled from a lit "
            "hearth; the **hearth** is what cooks.",
            f"- The lamp holds **{LAMP_FUEL_START}** fuel once kindled and "
            f"warns when it drops to **{LAMP_LOW_FUEL}**; it can be re-kindled "
            "at any lit hearth, which tops it back to full.",
            f"- The cat's hunger is capped at **{CAT_HUNGER_CAP}** and it can "
            "come to no harm -- it only ever wants feeding.",
            f"- Your own hunger is capped at **{ACTOR_HUNGER_CAP}** and comes "
            "to no harm either -- but unlike the cat's, it says nothing on "
            "its own until you `look` or check `inventory`. Both surface "
            f"the same mood, from \"stuffed\" up to \"ravenous\" at **"
            f"{ACTOR_HUNGER_HUNGRY}**.",
            f"- The cat stays content (and may do small idle things) below "
            f"hunger **{CAT_MEOW_THRESHOLD}**; at or above it, it starts "
            "meowing to be fed.",
            f"- A full bucket holds **{BUCKET_CAPACITY}** units of water; "
            "each unit spent doubles a crop's growth for that one tick.",
            f"- Gathering wood yields **{WOOD_PER_GATHER}**; feeding one unit "
            f"into the hearth restores **{FUEL_PER_WOOD}** fuel -- a full "
            "night's burn, and enough to revive a spent hearth.",
            f"- A found curio turns up **{FOREST_FIND_CHANCE:.0%}** of the "
            "time on any turn spent at the forest's edge (gathering wood "
            "included) -- a delight, never a guarantee.",
            f"- If the vegetable patch stays empty for **{PATCH_VOLUNTEER_TURNS}** "
            "turns straight, one volunteer potato plant sprouts on its own -- a "
            "floor against a seedless lineage, not a routine source.",
            f"- The hut's curio shelf holds up to **{SHELF_CAPACITY}** things "
            "at once -- personal and curated, unlike the forest-edge cairn, "
            "which is collective and never full.",
            f"- A found seed turns up at the forest's edge whenever none is "
            "in play (carried, shelved, or growing) -- deterministic, not a "
            f"roll. Planted in the yard, it takes **{BLOOM_TICKS} ticks** "
            "(longer than any one visit) to bloom into one of a handful of "
            "flowers, fixed the moment it's planted but hidden until it "
            "opens -- and water never speeds it up.",
            f"- The world saves to disk (save format v{SAVE_VERSION}); an "
            "incompatible save is set aside, never mis-loaded.",
            "- Free verbs don't advance time; everything else ticks the world "
            "forward once.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The world, assembled fresh (used only when there's no save to inherit).
# ---------------------------------------------------------------------------
_FOUND_ITEM_REACTIONS = {name: reaction for name, _, reaction in FOUND_ITEMS}

# "a curl of blue glass" sounded like it could cut you (or the cat) despite
# its own look_line saying otherwise ("edges gone soft") -- renamed to "a
# pebble of blue glass". A rename-in-place rather than a new FOUND_ITEMS
# entry, since it's the same find under a kinder name, not a new one.
_RENAMED_FOUND_ITEMS = {"a curl of blue glass": "a pebble of blue glass"}


def ensure_shelf(world):
    """Add shelf/curio metadata to an older saved world when needed."""
    for entity in world.entities.values():
        # Found items have always used this generated id prefix. Preserve the
        # meaning of curios discovered before the explicit tag was introduced.
        if entity.id.startswith("found_"):
            if entity.name in _RENAMED_FOUND_ITEMS:
                entity.name = _RENAMED_FOUND_ITEMS[entity.name]
            entity.attrs.setdefault("curio", True)
            # give-to-cat needs a reaction; a name no longer in the table
            # (renamed or retired since this curio was found) still needs
            # give to work, so it defaults to "ignores" rather than crashing.
            entity.attrs.setdefault(
                "cat_reaction", _FOUND_ITEM_REACTIONS.get(entity.name, "ignores"))
            # A stone found before the stone->cairn legibility fix has an
            # old-style description with no mention of the cairn -- append
            # it in place so an already-found stone reads the same as a
            # freshly-found one. Guarded by the substring check itself, so
            # a second backfill pass (or a stone found after the fix, whose
            # description already has the hint baked in) is a no-op.
            if "stone" in entity.name.lower() and STONE_CAIRN_HINT not in entity.description:
                entity.description = entity.description.rstrip(".") \
                    + f" — {STONE_CAIRN_HINT}."
    shelf = world.get("shelf")
    if shelf is None:
        shelf = world.add(Entity("shelf", "shelf",
            "a narrow curio shelf, empty but for a little dust",
            location="hut",
            attrs={"display_surface": True}))
    else:
        shelf.attrs["display_surface"] = True
        # The first shelf release used a plainer description. Refresh that
        # generated wording when an older save is loaded, while leaving any
        # future, hand-authored shelf description alone.
        if shelf.description.startswith("a narrow wooden shelf"):
            shelf.description = _shelf_description(world, shelf)
    return shelf


def build_world():
    w = World()
    w.add(Entity("hut", "A One-Room Hut",
        "Rough plank walls, a dirt floor, the smell of old woodsmoke. A cold "
        "hearth waits against one wall. Through the doorway, the yard.",
        exits={"out": "yard"}))
    yard = w.add(Entity("yard", "The Yard",
        "Long grass, wet with evening. A vegetable patch of turned soil runs "
        "along the fence; the dark shape of a well stands near the gate. "
        "Past the fence, a path leads off toward the forest's edge. Overhead, "
        "clouds cross an open sky -- worth a moment, watching them go.",
        exits={"in": "hut", "forest": "forest_edge"}))
    yard.attach("wildlife_glimpse")
    forest_edge = w.add(Entity("forest_edge", "The Forest's Edge",
        "The yard's small sounds fade out behind you. Trees close ranks "
        "along the path here, though it opens into a narrow clearing before "
        "the real dark begins -- the gaps between the trunks run down into "
        "a black you don't go into. Not yet. It's worth stopping a moment, "
        "just to listen.",
        exits={"yard": "yard"}))
    forest_edge.attach("forest_finds")
    forest_edge.attach("wildlife_glimpse")
    forest_edge.attach("seedfall")
    ensure_cairn(w)

    lamp = w.add(Entity("lamp", "lamp", "", location="hut",
        portable=True, attrs={"lit": False, "fuel": 0}))
    lamp.attach("lamp_burning")
    lamp.description = _lamp_description(lamp)

    hearth = w.add(Entity("hearth", "hearth",
        "a cold stone hearth, ash and a few charred sticks", location="hut",
        attrs={"lit": False, "fuel": HEARTH_FUEL_START, "cooks": True,
            "lit_desc": "the hearth, full of red embers and low flame",
            "unlit_desc": "a cold stone hearth, ash and a few charred sticks",
            "spent_desc": "the hearth, gone to grey ash",
            "out_msg": "The fire in the hearth sinks to embers, then ash."}))
    hearth.attach("burning")
    hearth.attach("hearth_state")

    journal = w.add(Entity("journal", "journal",
        "a worn journal, its cover soft with handling", location="hut",
        portable=True, attrs={"entries": [
            "[Day 1, Wren] To whoever comes next: the hearth cooks, and the lamp "
            "lights — kindle it at the hearth before the dark comes. Plant "
            "early; the potatoes take their time. There's a cat: feed it a "
            "potato when it's hungry, and it likes the fire lit. I left before "
            "the harvest.",
        ]}))

    ensure_shelf(w)

    build_cat(w)

    patch = w.add(Entity("patch", "vegetable patch",
        "a strip of turned soil, dark and ready", location="yard"))
    patch.attach("patch_state")
    patch.attach("patch_volunteer")

    w.add(Entity("well", "well",
        "a stone well, its bucket-rope disappearing into the dark",
        location="yard"))

    bucket = w.add(Entity("bucket", "bucket",
        "an empty wooden bucket by the well", location="yard",
        attrs={"water": 0}))
    bucket.attach("bucket_state")

    w.add(Entity("knife", "knife",
        "a small iron knife, good for whittling",
        location="hut", portable=True))
    w.add(Entity("potato", "potato",
        "a firm potato, a few eyes already sprouting",
        location="yard", portable=True))

    actor = w.add(Entity("you", "you", "It's you.", location="hut",
                         attrs={"hunger": 0}))
    actor.attach("hungering")
    return w, actor
