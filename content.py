"""
content.py -- Emberworld itself: the verbs, the autonomous behaviors, and the
world as assembled fresh. world.py's engine is generic; this is where
anything specific to hearths, potatoes, and journals lives. The cat is its
own self-contained subsystem -- see cat.py.

Growing the game = adding entries here. New verbs go in VERBS with a
one-line docstring; new autonomy goes in BEHAVIORS; new content goes in
build_world(). See ARCHITECTURE.md for the full recipe.
"""

from world import World, Entity, VERBS, FREE_VERBS, BEHAVIORS, SAVE, SAVE_VERSION, DAY_LENGTH
from cat import CAT_HUNGER_CAP, CAT_MEOW_THRESHOLD, build_cat


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


HEARTH_FUEL_START = 40      # the hearth's starting fuel, in build_world
HEARTH_LOW_FUEL = HEARTH_FUEL_START // 4    # below this, it reads as dying


def hearth_state(world, hearth):
    """Autonomous: while lit, the hearth's description shows whether it's
    dying low on fuel or burning steady, so a hand can see it needs wood
    before it goes dark, not just be told after the fact."""
    if not hearth.attrs.get("lit"):
        return          # burning() already owns the unlit/spent description
    if hearth.attrs.get("fuel", 0) <= HEARTH_LOW_FUEL:
        hearth.description = "the hearth, embers dying low -- it wants more wood"
    else:
        hearth.description = hearth.attrs.get(
            "lit_desc", "the hearth, full of red embers and low flame")


def hungering(world, actor):
    """Autonomous: the actor slowly gets hungrier over time (capped, harmless)."""
    actor.attrs["hunger"] = min(actor.attrs.get("hunger", 0) + 1, 20)


LAMP_FUEL_START = 16       # comfortably outlasts one night (5 ticks), with margin
LAMP_LOW_FUEL = 4          # warns with enough runway left to reach the hearth


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


BEHAVIORS.update({"burning": burning, "growing": growing, "patch_state": patch_state,
                   "patch_volunteer": patch_volunteer,
                   "bucket_state": bucket_state, "hearth_state": hearth_state,
                   "hungering": hungering, "lamp_burning": lamp_burning})


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
    here = world.contents(actor.location)
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


def _is_raw(e):
    return e.attrs.get("food", 0) <= 0


def _is_cooked(e):
    return e.attrs.get("food", 0) > 0


LAST_POTATO_BEAT = "That was the last potato — the patch lies bare behind you now."


def _patch_has_crop(world):
    patch = world.get("patch")
    return patch is not None and bool(world.contents(patch.id))


def _last_potato_beat(world, actor, consumed_was_raw):
    """A one-shot pang, not a standing warning: fires only at the exact
    moment a hand spends its LAST raw (plantable) potato with nothing
    growing in the patch. Cooked food was never seed, so it never counts
    toward "raw potatoes remaining" -- and since the trigger is "now holds
    zero," there's no state left to re-announce on a later turn."""
    if not consumed_was_raw:
        return ""
    still_have_raw = any(_is_raw(e) and "potato" in e.name
                         for e in world.contents(actor.id))
    if still_have_raw or _patch_has_crop(world):
        return ""
    return "\n" + LAST_POTATO_BEAT


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
    names = _carried_names(world, actor)
    if not names:
        return "Your hands are empty."
    return "You are carrying: " + ", ".join(names) + "."


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
                f"light — a lamp kindled at the hearth would do, or you could "
                f"wait for dawn. Somewhere out there the world goes on "
                f"regardless.\n\n{_carried_line(world, actor)}")
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


def _the(name):
    """'the ' + name, minus a leading indefinite article. Found curios bake
    one into their name (so the discovery and carried-item lines read
    naturally as-is), but a message that prepends its own 'the' would
    otherwise double up into 'the a smooth grey stone'."""
    for article in ("a ", "an "):
        if name.lower().startswith(article):
            return "the " + name[len(article):]
    return "the " + name


def cmd_take(world, actor, arg):
    """take <thing> -- pick up a portable object."""
    e = find_visible(world, actor, arg)
    if not e:
        return f"There's no '{arg}' here to take."
    if e.location == actor.id:
        return f"You're already carrying {_the(e.name)}."
    if not e.portable:
        return f"The {e.name} won't budge."
    e.location = actor.id
    return f"You take {_the(e.name)}."


def cmd_drop(world, actor, arg):
    """drop <thing> -- set down something you're carrying."""
    e = find_visible(world, actor, arg)
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    e.location = actor.location
    return f"You set down {_the(e.name)}."


def _shelf_description(world, shelf):
    """Describe the shelf as a small, visible record of what hands kept."""
    items = world.contents(shelf.id)
    if not items:
        return "a narrow curio shelf, empty but for a little dust"
    return ("a narrow curio shelf, holding: "
            + ", ".join(e.name for e in items))


def cmd_place(world, actor, arg):
    """place <thing> [on shelf] -- set a carried object on the hut's curio shelf."""
    shelf = next((e for e in world.contents(actor.location)
                  if e.attrs.get("display_surface")), None)
    if not shelf:
        return "There's nowhere here to set that out. The shelf is in the hut."
    item_name = arg.lower().strip()
    if item_name.endswith(" on shelf"):
        item_name = item_name[:-len(" on shelf")].strip()
    e = find_visible(world, actor, item_name)
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    e.location = shelf.id
    shelf.description = _shelf_description(world, shelf)
    return f"You set {_the(e.name)} on the shelf."


def cmd_inventory(world, actor, arg):
    """inventory -- list what you're carrying and how hungry you feel."""
    names = _carried_names(world, actor)
    hunger = actor.attrs.get("hunger", 0)
    mood = ("stuffed" if hunger < 3 else "fine" if hunger < 10
            else "hungry" if hunger < 16 else "ravenous")
    head = f"You feel {mood}."
    if not names:
        return head + "\nYour hands are empty."
    return head + "\nYou are carrying:\n" + "\n".join(f"  - {n}" for n in names)


def cmd_actions(world, actor, arg):
    """actions -- list the things you can do from here right now."""
    return "Available actions:\n" + "\n".join(
        f"  - {action}" for action in world.available_actions(actor))


def cmd_wait(world, actor, arg):
    """wait -- let one tick pass while you do nothing."""
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
    """plant potato -- press a raw potato into the vegetable patch to grow it."""
    e = find_visible(world, actor, arg or "potato", prefer=_is_raw)
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

# Small, purely cosmetic finds a lucky gather can turn up alongside the wood.
# No mechanics attached -- they're just there to reward the "worth
# experimenting" nudge in the system prompt with something concrete to find.
FOUND_ITEMS = (
    ("a smooth grey stone", "a stone worn smooth and round, cool in your palm"),
    ("a jay's feather", "a jay's feather, blue-black and sharply barred"),
    ("a curl of birch bark", "a curl of birch bark, pale and papery"),
    ("a knot of bleached twine", "a bit of old twine, sun-bleached and knotted"),
    ("a sprig of dried moss", "a sprig of moss, dried to a soft green-grey"),
)
FOUND_ITEM_CHANCE = 0.15


def cmd_gather(world, actor, arg):
    """gather wood -- forage the yard's long grass and fallen branches for firewood (and, sometimes, something else)."""
    if actor.location != "yard":
        return "There's nothing to forage here -- try the yard."
    actor.attrs["wood"] = actor.attrs.get("wood", 0) + WOOD_PER_GATHER
    result = (f"You push through the long grass and gather fallen branches. "
              f"You now have {actor.attrs['wood']} wood.")
    if world.rng.random() < FOUND_ITEM_CHANCE:
        name, desc = world.rng.choice(FOUND_ITEMS)
        world.add(Entity(world.fresh_id("found"), name, desc,
                          location=actor.id, portable=True,
                          attrs={"curio": True}))
        result += f"\nSomething catches your eye in the grass: {name}."
    return result


def cmd_add_wood(world, actor, arg):
    """add wood -- feed carried firewood into the hearth, raising its fuel."""
    hearth = find_visible(world, actor, "hearth")
    if not hearth:
        return "There's no hearth here to feed."
    if actor.attrs.get("wood", 0) <= 0:
        return "You've no wood to add. Gather some in the yard first."
    actor.attrs["wood"] -= 1
    hearth.attrs["fuel"] = hearth.attrs.get("fuel", 0) + FUEL_PER_WOOD
    if hearth.attrs.get("lit"):
        return "You feed wood into the fire. It catches and burns brighter."
    hearth.description = "a stone hearth, freshly stacked with wood, ready for a light"
    return "You stack wood in the cold hearth, ready for a light."


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
    e.attrs["food"] = 8
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
    "draw": cmd_draw, "water": cmd_water, "place": cmd_place,
    "gather": cmd_gather,
    # not "feed": that verb key is already cmd_feed (feeds the cat, in cat.py),
    # and the parser only looks at the first word -- "feed fire" would collide.
    "add": cmd_add_wood, "stoke": cmd_add_wood,
})
FREE_VERBS.update({"look", "l", "examine", "x", "inventory", "i", "actions", "read", "save"})


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
            "cycle and is pitch dark without a lit flame. A fresh world starts "
            "at dawn, giving a full day's light before the first night falls.",
            "- The tin lamp is the only portable light, kindled from a lit "
            "hearth; the **hearth** is what cooks.",
            f"- The lamp holds **{LAMP_FUEL_START}** fuel once kindled and "
            f"warns when it drops to **{LAMP_LOW_FUEL}**; it can be re-kindled "
            "at any lit hearth, which tops it back to full.",
            f"- The cat's hunger is capped at **{CAT_HUNGER_CAP}** and it can "
            "come to no harm -- it only ever wants feeding.",
            f"- The cat stays content (and may do small idle things) below "
            f"hunger **{CAT_MEOW_THRESHOLD}**; at or above it, it starts "
            "meowing to be fed.",
            f"- A full bucket holds **{BUCKET_CAPACITY}** units of water; "
            "each unit spent doubles a crop's growth for that one tick.",
            f"- Gathering wood yields **{WOOD_PER_GATHER}**; feeding one unit "
            f"into the hearth restores **{FUEL_PER_WOOD}** fuel -- a full "
            "night's burn, and enough to revive a spent hearth.",
            f"- If the vegetable patch stays empty for **{PATCH_VOLUNTEER_TURNS}** "
            "turns straight, one volunteer potato plant sprouts on its own -- a "
            "floor against a seedless lineage, not a routine source.",
            f"- The world saves to disk (save format v{SAVE_VERSION}); an "
            "incompatible save is set aside, never mis-loaded.",
            "- Free verbs don't advance time; everything else ticks the world "
            "forward once.", ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The world, assembled fresh (used only when there's no save to inherit).
# ---------------------------------------------------------------------------
def ensure_shelf(world):
    """Add shelf/curio metadata to an older saved world when needed."""
    for entity in world.entities.values():
        # Found items have always used this generated id prefix. Preserve the
        # meaning of curios discovered before the explicit tag was introduced.
        if entity.id.startswith("found_"):
            entity.attrs.setdefault("curio", True)
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
    w.add(Entity("yard", "The Yard",
        "Long grass, wet with evening. A vegetable patch of turned soil runs "
        "along the fence; the dark shape of a well stands near the gate.",
        exits={"in": "hut"}))

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
            "[a while ago] To whoever comes next: the hearth cooks, and the lamp "
            "lights — kindle it at the hearth before the dark comes. Plant "
            "early; the potatoes take their time. There's a cat: feed it a "
            "potato when it's hungry, and it likes the fire lit.",
            "[some days later] Fed the cat, kept a potato in the ground, "
            "planted another before I left. Carry the rhythm on.",
            "[Day 1] Kept the fire fed and the cat fed — in that order, or the "
            "cat will let you know. Quiet few days, and I grew unexpectedly fond "
            "of the cat. Once or twice of an evening I caught myself wishing for "
            "a bit of company that wasn't four-legged; but you're a kind of "
            "company, reading this, even if we never share the room. I left "
            "before the harvest. — someone before you",
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
