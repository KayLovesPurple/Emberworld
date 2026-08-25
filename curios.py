"""
curios.py -- the found-curio economy: what a hand does with a small found
thing once it's in hand. Split out of content.py once this had grown into
a coherent slice on its own (shelf, cairn, charm-string, give-to-cat,
tuck-in-journal, plus the visual-compression that keeps a well-visited room
readable) -- same reasoning as cat.py/chicken.py's own splits. See
docs/ARCHITECTURE.md for the as-built history of each fate below.

What stays in content.py on purpose: cmd_look itself (a general verb that
happens to call into _group_look_summary/_charm_string_ascii here), the
journal's own write/read/entry-indexing (cmd_tuck reaches into it via a
deferred import, same pattern as cat.py's cmd_feed reaching for
cmd_add_wood), and find_visible/_carrying/_room_here themselves -- those
moved to content_common.py, since every verb in the game needs them, not
just this file.
"""

from world import Entity, VERBS
from content_common import _the, find_visible, _carrying
from cat import _cat_cap


# ---------------------------------------------------------------------------
# Curio visual compression -- curios are intentionally persistent (nothing
# decays or auto-clears), so a well-visited hut accumulates loose pinecones
# and feathers without bound. That's fine for the world; it's noisy for the
# room description. This is a presentation-only pass: it changes what the
# room LISTING shows, never any entity's own data, so find_visible/take/
# give/place keep resolving to one real entity exactly as they always have.
# See docs/CURIO_VISUAL_COMPRESSION.md. content.py's _room_lines calls into
# this; the grouping logic itself lives here, next to the curios it groups.
# ---------------------------------------------------------------------------
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def _spell(n):
    """A small count in words -- "three pinecones" reads as prose; "3
    pinecones" reads as a stat line. Falls back to the digit past the
    table, which a curio's real-world rarity should make unreachable."""
    return _NUMBER_WORDS.get(n, str(n))


CURIO_GROUP_EXACT_MAX = 4    # group sizes 2..this: spell out the exact count
CURIO_GROUP_SEVERAL_AT = 5   # at/above this: "several X" instead of a number


def _curio_groups(entities):
    """Partition the curios among `entities` into groups keyed by (name,
    description), in first-seen order. A curio only groups with another
    that matches on BOTH -- name alone isn't enough, because a curio with
    different text (a distinct, persistent state -- see
    CURIO_VISUAL_COMPRESSION.md's "compress repetition, not character")
    must always keep its own line, however small the group.

    BUG WE HIT (real observed output): the first version of this only
    considered still-portable curios eligible, on the reasoning that a
    trace left by `give <curio> to cat` reads as permanent room scenery,
    not accumulating clutter. It clutters just as visibly -- two pinecones
    separately given to the cat produced two identical "a pinecone,
    well-battered after a game with the cat" bullets, exactly the noise
    this feature exists to fix. Traces are included now; see
    _group_count_line for how a trace group keeps its text instead of
    collapsing to a bare count the way an ordinary find does.

    Returns an ordered list of (name, description, [entities])."""
    order, groups = [], {}
    for e in entities:
        if not e.attrs.get("curio"):
            continue
        key = (e.name, e.description)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(e)
    return [(name, desc, groups[(name, desc)]) for name, desc in order]


def _drop_self_naming_prefix(name, description):
    """A cat-given trace's description is self-naming -- "{name}, {suffix}"
    (see _CAT_GIVE_TRACES) -- because on its own (count==1) it's rendered
    as-is by _room_listing_line with no separate name prefix. Once it's
    folded into a count line or a group summary, the name is already
    spoken there, so repeating it verbatim reads as "There are two
    pinecones here. a pinecone, well-battered..." -- the name twice.
    Strips the "{name}, " open when present; returns `description`
    unchanged for an ordinary find's bare look_line (which never has it).
    Shared by _group_count_line and _group_look_summary so both render a
    trace group the same way."""
    prefix = f"{name}, "
    return description[len(prefix):] if description.startswith(prefix) else description


def _group_count_line(name, description, count):
    """The room-listing line for a compressed group. An ordinary find's
    description is just flavor text (a bare look_line) -- dropping it is
    the whole point of compression, so the line is just the count and the
    plural name ("three pinecones"). A cat-given trace's description is
    self-naming and the suffix IS the point (`give`'s whole invariant is
    that the gesture always leaves its mark), so a trace group keeps it:
    "two pinecones, well-battered after a game with the cat" reads
    naturally even though "a game" stays grammatically singular -- no
    attempt to conjugate the suffix, which would need real NLG for no
    real gain here."""
    plural = _plural_of(name)
    prefix = f"{_spell(count)} {plural}" if count <= CURIO_GROUP_EXACT_MAX \
        else f"several {plural}"
    tail = _drop_self_naming_prefix(name, description)
    if tail != description:
        return prefix + ", " + tail
    return prefix


def _group_look_summary(name, entities):
    """What `look <name>` shows when 2+ compressible curios sharing `name`
    are loose among `entities` -- reveals the exact total (an approximate
    "several" is for the passive standing description; a hand who
    deliberately asks always gets the real count, the exact underlying
    count is never lost) and, when they don't all share one description,
    names the distinctive one(s) rather than folding them in silently.
    Returns None when 0 or 1 curio actually matches, so the caller falls
    back to that single entity's own .description, unchanged from before
    this feature existed."""
    subgroups = [(desc, es) for n, desc, es in _curio_groups(entities) if n == name]
    total = sum(len(es) for _, es in subgroups)
    if total <= 1:
        return None
    head = f"There are {_spell(total)} {_plural_of(name)} here."
    if len(subgroups) == 1:
        return head + " " + _drop_self_naming_prefix(name, subgroups[0][0])
    subgroups.sort(key=lambda kv: -len(kv[1]))
    parts = []
    for i, (desc, es) in enumerate(subgroups):
        label = "ordinary" if i == 0 else "different"
        count = len(es)
        verb = "is" if count == 1 else "are"
        parts.append(f"{_spell(count)} {verb} {label}: {_drop_self_naming_prefix(name, desc)}")
    return head + " " + " ".join(parts)


# ---------------------------------------------------------------------------
# Found items -- what the forest's find-roll (content.py) can turn up, and
# the descriptions/hints built from them. Small, purely cosmetic finds:
# each is (name, look_line, cat_reaction); look_line is a bare, odd,
# specific fragment -- not a summary sentence -- assembled into a full
# description by _found_description below. cat_reaction ("plays"/"ignores")
# drives both the look-line's optional cat hint and what `give <thing> to
# cat` does with it; see the invariant at cmd_give: this shelf/give pairing
# is the world's calm axis, and neither affordance may touch a maintenance
# resource (fire, food, water) -- only ever leave the world one durable
# thing richer.
# ---------------------------------------------------------------------------
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

# English pluralization of arbitrary noun phrases isn't reliable to derive
# ("a pebble of blue glass" -> "pebbles of blue glass" needs the FIRST word
# inflected, not the last) -- so, same discipline as FOUND_ITEMS itself,
# these are hand-authored rather than guessed. Used by curio visual
# compression (see _plural_of) to render a grouped room-listing line
# ("three pinecones") without ever showing a mangled plural.
_CURIO_PLURALS = {
    "a pinecone": "pinecones",
    "a small brown feather": "small brown feathers",
    "a smooth grey stone": "smooth grey stones",
    "a pebble of blue glass": "pebbles of blue glass",
    "a bone button": "bone buttons",
    "a jay's feather": "jay's feathers",
    "a knot of bleached twine": "knots of bleached twine",
    "a curl of birch bark": "curls of birch bark",
    "a sprig of dried moss": "sprigs of dried moss",
}


def _plural_of(name):
    """The plural noun phrase for a curio name, e.g. "a pinecone" ->
    "pinecones". Looks up _CURIO_PLURALS first; the naive "strip the
    article, add an s" fallback exists only so a future curio added without
    a plural entry degrades to something readable instead of crashing --
    test_every_found_item_has_a_hand_authored_plural pins that every real
    FOUND_ITEMS entry uses the real table, not the fallback."""
    if name in _CURIO_PLURALS:
        return _CURIO_PLURALS[name]
    for article in ("a ", "an "):
        if name.lower().startswith(article):
            return name[len(article):] + "s"
    return name + "s"


# `stack stone on cairn` has worked since Stage 7, but the cairn was only
# ever named in the forest-edge room text -- a cue a hand loses the moment
# they carry a stone anywhere else. Observed in play: the shelf filled with
# duplicate stones while the cairn barely grew. The fix is to put the cue on
# the stone itself, the same way the shelf always describes its own held
# capacity regardless of where a hand stands -- see ARCHITECTURE.md's
# "Stone -> cairn legibility" note. Named directly: unlike the statue, the
# cairn is a real mechanic, so there's no reason to euphemize it.
STONE_CAIRN_HINT = "it could go on the cairn at the forest's edge"

# Same legibility fix, same reasoning, for the hut's charm-string (see the
# CHARM_STRING_ID block below): round/dimensional curios with a hole or a
# natural hangable quality have a second fate beyond give-to-cat, and the
# cue belongs on the item itself, not just in the room it's usable in.
# Deliberately narrow -- a button's hole and a pebble's easy-to-knot shape
# both plausibly thread. A pinecone qualifies too: its own look_line above
# ("one scale broken") is exactly the kind of gap a knot can catch in, the
# same physical logic as a button's hole -- not just "round like a button".
# A feather still doesn't qualify; it already has its own fate (the
# journal-tuck). Extend only once the forest generates more qualifying finds.
CHARM_ELIGIBLE_ITEMS = ("a bone button", "a pebble of blue glass", "a pinecone")
CHARM_STRING_HINT = "it could be threaded onto the charm-string in the hut"

# Twine is the OTHER half of the threading recipe (cmd_thread consumes one),
# found through the same FOUND_ITEMS roll as everything else and just as
# giveable to the cat on paper -- but a real session (Marrow, day 59) found
# every eligible curio AND both knots of twine already given away by earlier
# hands, leaving the charm-string permanently stuck for that visit with no
# hint pointing anywhere, since the missing-twine hint only fires once an
# eligible curio is already in hand. Rather than try to hint a hand out of a
# fully-empty state, refuse the give itself: twine is a means (the knot that
# attaches something), not a decorative end the way a button or pebble is,
# so it never enters the give-to-cat economy in the first place. Guards both
# ends the same way the map-discoverability bug did -- cat_actions (cat.py)
# must not offer `give ... to cat` for twine either, or the refusal below
# would just be a second copy of that same "offered but doesn't work" bug.
GIVE_TWINE_REFUSAL = "You hold the twine back -- it's too useful for the charm-string to give away."


def _found_description(look_line, reaction, name=""):
    """Assemble a curio's full description from its bare look_line -- adding
    the cat hint only for a cat_reaction of "plays" (only those finds are
    worth a cat's attention), the cairn hint for anything named a stone
    (only found stones have one), and the charm-string hint for anything in
    CHARM_ELIGIBLE_ITEMS. `name` defaults to "" so existing call sites that
    never mention a stone or a threadable curio see byte-identical output to
    before either hint existed."""
    text = look_line
    if reaction == "plays":
        text += " — the cat might bat at it"
    if "stone" in name.lower():
        text += f" — {STONE_CAIRN_HINT}"
    if name in CHARM_ELIGIBLE_ITEMS:
        text += f" — {CHARM_STRING_HINT}"
    return text + "."


# ---------------------------------------------------------------------------
# The shelf -- personal and reversible (a later hand can take an item
# back). Deliberately capped, unlike the cairn: the cairn already is the
# "everything, forever, anonymous" answer to what to do with a found
# curio -- a second unlimited container doing the same job would be
# redundant. Capping the shelf turns it into the cairn's opposite: personal
# and curated rather than collective and boundless. Nothing decays and
# nothing's punished for being full -- a hand just has to decide whether a
# new find is worth a spot, the same kind of small, real, freely-chosen
# choice as everything else on the calm axis. `take` (already existing,
# no new mechanic) is how a hand makes room.
# ---------------------------------------------------------------------------
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
        from content import cmd_add_wood   # deferred: cmd_add_wood is hearth-owned, stays in content.py
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


# _FOUND_ITEM_REACTIONS/_RENAMED_FOUND_ITEMS/ensure_shelf live down here,
# after cmd_place, rather than up with FOUND_ITEMS: they're the shelf's own
# backfill (called from build_world and drivers.load_or_build, same role as
# ensure_cairn/ensure_charm_string below), not part of the found-item
# taxonomy itself.
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
            #
            # BUG WE HIT: this ran against every found_* entity matching the
            # name, with no check for whether it was still an actual, reachable
            # curio. A stone (or, once CHARM_STRING_HINT existed, a button/
            # pebble) already given to the cat is non-portable and its
            # description already rewritten to a cat-trace by cmd_give -- but
            # this loop still appended the hint on top, reading as "given to
            # the cat and roundly ignored -- it could go on the cairn", which
            # is false: that curio can never reach the cairn or the
            # charm-string again, it's stuck in the room forever. `portable`
            # is the one flag cmd_give flips to False and never flips back, so
            # it's the correct discriminator -- deliberately not "is this
            # entity still a live curio a hand could carry", which would need
            # touching cmd_give itself and would reopen a rescue path from
            # cat-given items that was explicitly ruled out (see the
            # charm-string's own design notes).
            if entity.portable and "stone" in entity.name.lower() \
                    and STONE_CAIRN_HINT not in entity.description:
                entity.description = entity.description.rstrip(".") \
                    + f" — {STONE_CAIRN_HINT}."
            # Same backfill, same reasoning, same guard, for a button or
            # pebble found before the charm-string existed -- see CHARM_STRING_HINT.
            if entity.portable and entity.name in CHARM_ELIGIBLE_ITEMS \
                    and CHARM_STRING_HINT not in entity.description:
                entity.description = entity.description.rstrip(".") \
                    + f" — {CHARM_STRING_HINT}."
            # BUG WE HIT (real save file): the two guards above only stop a
            # hint from being ADDED to a cat trace going forward -- a world
            # saved before either guard shipped already has the wrong text
            # baked directly into the trace's own .description ("given to
            # the cat and roundly ignored -- it could go on the cairn"). The
            # guard alone never heals that, so it has to be actively
            # stripped here too, every load, same as the addition above is.
            if not entity.portable:
                for hint in (STONE_CAIRN_HINT, CHARM_STRING_HINT):
                    entity.description = entity.description.replace(
                        f" — {hint}.", ".")
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


# ---------------------------------------------------------------------------
# Give-to-cat -- the reaction and the durable trace it leaves behind, keyed
# by the curio's own cat_reaction. The gesture matters regardless of which
# fires -- see cmd_give's docstring and the reset-or-richer invariant it
# guards: either way the thing is gone from the pack and the world is one
# thing richer, never reset.
# ---------------------------------------------------------------------------
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
    if "twine" in e.name.lower():
        return GIVE_TWINE_REFUSAL
    reaction = e.attrs.get("cat_reaction", "ignores")
    cap, thing, name = _cat_cap(cat), _the(e.name), e.name
    e.location = actor.location
    e.portable = False
    e.description = _CAT_GIVE_TRACES[reaction].format(name=name)
    return _CAT_GIVE_REACTIONS[reaction].format(cap=cap, thing=thing)


# ---------------------------------------------------------------------------
# The forest-edge cairn -- a collective, permanent counterpart to the hut's
# shelf. The shelf is personal and reversible (a later hand can take an item
# back); a stone added here isn't -- it stops being anyone's the instant it
# joins the pile, and becomes part of something the whole lineage built, one
# stone at a time, that no single hand owns or can undo. Reset-or-richer
# taken to its most literal point: this can only ever grow.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# The charm-string -- a fourth fate for found things, alongside the shelf
# (personal, capped, take-backable), the cairn (collective, stone-only,
# infinite, one-way), and the journal-tuck (flat things, attached to
# entries). Round curios -- a button, a glass pebble -- had exactly one
# fate before this: give-to-cat, a one-shot verdict that leaves the item on
# the floor forever either way (see FOUND_ITEMS: both are hardcoded
# "ignores", so today they have no positive fate at all). This is that
# fate: a wall-mounted, collective object hands can add to over the
# lineage's whole life. Unlike the cairn (grows taller, same texture every
# stone), it reads differently as it fills -- sparse to rich -- since the
# appeal here is decorative variety, not monument height. Lives in the hut,
# next to the shelf: there's nowhere else in the game that reads as the
# lineage's own fixed architecture the way the hut does.
# ---------------------------------------------------------------------------
CHARM_STRING_ID = "charm_string"

# A "big decoration," not a resource to manage -- large enough that no
# normal lineage will ever feel the ceiling (a curio is already a rare
# find, and threading one spends a second rare find, the twine, right
# alongside it), but a real cap exists so nothing grows truly infinite.
CHARM_CAPACITY = 100

# Count-based tiers, not item-specific -- same approach as the forest's
# depth bands and the cairn's height bands, for the same reason: tracking
# flavor text per possible mix of item types doesn't scale, and isn't the
# point (naming which items are visible is an explicit stretch goal, not
# this pass). Exact boundaries are a writing-pass call, not an
# architectural one -- these are a first guess, easy to retune once real
# lineages have actually used it a while.
CHARM_BANDS = (
    (0, "a bare length of twine hangs on the wall, waiting."),
    (1, "a single found thing hangs from the twine -- a start, not yet a decoration."),
    (2, "a few found things hang from the twine -- still a start, not yet a decoration."),
    (5, "a small scatter of found things hangs from the twine, starting to gather."),
    (20, "a charm-string clatters gently, crowded with found things."),
)


def _charm_string_description(count):
    text = CHARM_BANDS[0][1]
    for threshold, line in CHARM_BANDS:
        if count >= threshold:
            text = line
    return text


# BUG WE HIT: a hand carrying an eligible curio but no twine had no way to
# discover that twine was the missing half of the recipe -- carrying_actions
# only lists "thread ..." once BOTH ingredients are in hand, so with just
# the curio the affordance was simply absent, indistinguishable from "there's
# nothing to do here." A real session (Tallow, day 55) hit exactly this:
# looked at the charm-string twice, never tried `thread` blind, and ended up
# giving its only curio to the cat on the theory that might help instead.
# Surfaced here on `look charm-string`, reusing cmd_thread's own refusal
# wording so there's only one place that sentence is authored.
CHARM_MISSING_TWINE_HINT = (
    "You have something that could go on it, but you'll need a knot of "
    "twine in hand to thread it."
)


def _charm_string_missing_twine_hint(world, actor, charm):
    if charm.attrs["count"] >= CHARM_CAPACITY:
        return ""
    carried = world.contents(actor.id)
    if any("twine" in e.name.lower() for e in carried):
        return ""
    if not any(e.name in CHARM_ELIGIBLE_ITEMS for e in carried):
        return ""
    return CHARM_MISSING_TWINE_HINT


# Phase 2 of the charm-string, deferred at Phase 1's original ship (see
# README's "Someday" entry for the original design this was built from,
# preserved there since it never got its own spec file). `look
# charm`/`look charm-string` -- a dedicated, richer view distinct from the
# room's own standing description above, which stays count-based prose
# only. One glyph per eligible item type; the pinecone's glyph is new
# here, added after the original spec (button/pebble only) since
# CHARM_ELIGIBLE_ITEMS grew a third member in the meantime.
CHARM_ITEM_GLYPHS = {
    "a bone button": "o",
    "a pebble of blue glass": "•",  # a plain round dot, not a bullet-point
    "a pinecone": "*",
}

# What an item threaded before item-tracking existed (see ensure_charm_string's
# backfill below) renders as -- honest about not knowing, rather than either
# guessing or quietly losing the accounting.
CHARM_UNKNOWN_GLYPH = "?"

CHARM_ASCII_ROW_WIDTH = 5
CHARM_ASCII_SEP = "~~~"


def _charm_string_ascii(charm):
    """look charm/look charm-string's dedicated view: a small ASCII strip,
    one glyph per threaded item in strict insertion order (oldest first),
    wrapped CHARM_ASCII_ROW_WIDTH per row and separated/framed by
    CHARM_ASCII_SEP, e.g. two buttons and a pebble: "~~~o~~~o~~~•~~~".
    Not sorted or grouped by type -- unattributed, unlike the journal, but
    the same spirit: a small, honest history of who-added-what-when.

    At zero items there's nothing to render, so this returns the exact same
    empty-prose-tier line the room's own standing description already uses
    for count 0 -- no empty ASCII block."""
    items = charm.attrs.get("items", [])
    if not items:
        return charm.description
    glyphs = [CHARM_ITEM_GLYPHS.get(name, CHARM_UNKNOWN_GLYPH) for name in items]
    rows = []
    for i in range(0, len(glyphs), CHARM_ASCII_ROW_WIDTH):
        row = glyphs[i:i + CHARM_ASCII_ROW_WIDTH]
        rows.append(CHARM_ASCII_SEP + CHARM_ASCII_SEP.join(row) + CHARM_ASCII_SEP)
    return "\n".join(rows)


def ensure_charm_string(world):
    """Add the hut's charm-string to a world that predates it (fresh build
    or an older save) -- same backfill role, and same resync-on-load fix
    for a description CHARM_BANDS may have changed underneath, as
    ensure_cairn (see its own docstring for the bug that guards against).

    Present-but-empty from world creation, unlike the lazily-created statue
    -- a bare length of twine on the wall is visible before anyone's added
    to it, the same way the cairn's flat stone is visible before any
    stone's been stacked.

    Also backfills `items` (Phase 2's insertion-ordered glyph list) to
    match `count` -- a charm-string threaded before item-tracking existed
    has a real count with no matching history. Padding the FRONT with
    `None` (rendered as CHARM_UNKNOWN_GLYPH) rather than the back is
    deliberate: new items are always appended to the end, so any untracked
    ones must be the oldest, not the newest. Idempotent -- once padded,
    len(items) == count, so a later load pads nothing further."""
    charm = world.get(CHARM_STRING_ID)
    if charm is None:
        charm = world.add(Entity(CHARM_STRING_ID, "charm-string",
                                  _charm_string_description(0),
                                  location="hut", attrs={"count": 0, "items": []}))
    else:
        charm.description = _charm_string_description(charm.attrs["count"])
        items = charm.attrs.setdefault("items", [])
        missing = charm.attrs["count"] - len(items)
        if missing > 0:
            charm.attrs["items"] = [None] * missing + items
    return charm


def cmd_thread(world, actor, arg):
    """thread <item> on charm-string -- add a carried button, pebble, or other threadable curio to the hut's charm-string, permanently, using up one twine to do it."""
    if not arg:
        return "Thread what onto the charm-string? e.g.  thread button on charm-string"
    charm = find_visible(world, actor, "charm-string")
    if not charm:
        return "There's no charm-string here -- it's on the wall of the hut."
    item_name = arg.lower().strip()
    for suffix in (" on charm-string", " on the charm-string", " on the wall"):
        if item_name.endswith(suffix):
            item_name = item_name[:-len(suffix)].strip()
            break
    e = find_visible(world, actor, item_name, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id or e.name not in CHARM_ELIGIBLE_ITEMS:
        return "That's not something you can thread onto the charm-string."
    if charm.attrs["count"] >= CHARM_CAPACITY:
        return "The string's full to hanging -- there's no room left for another thing."
    twine = find_visible(world, actor, "twine", prefer=lambda x: _carrying(world, actor, x))
    if not twine or twine.location != actor.id:
        return "You need a knot of twine in hand to thread anything onto the charm-string."
    world.entities.pop(e.id, None)
    world.entities.pop(twine.id, None)
    charm.attrs["count"] += 1
    charm.attrs.setdefault("items", []).append(e.name)
    charm.description = _charm_string_description(charm.attrs["count"])
    return f"You knot {_the(e.name)} onto the charm-string. Now: {charm.description}"


# ---------------------------------------------------------------------------
# Tuck in journal -- the flat-and-pressable counterpart to the cairn: a
# second, physically honest fate for curios the shelf's "displayed object"
# logic doesn't suit. Scoped narrowly on purpose: a feather (or the mystery
# seed's bloom) has an obvious real home pressed into a book; a pinecone or
# button never plausibly would, so round/dimensional curios are NOT part of
# this. Do not generalize to a catch-all "tuck any curio" verb -- see the
# tuck-in-journal spec's "Explicitly NOT in scope."
# ---------------------------------------------------------------------------
def _is_tuckable(e):
    """Feathers, by name; the mystery seed's bloom, by its blooms_at attr
    rather than by name -- BLOOM_KINDS includes names like "a single black
    bloom" that don't even contain the word "flower", so name-matching
    would miss some of them. No other curio type qualifies this pass."""
    return "feather" in e.name.lower() or "blooms_at" in e.attrs


TUCK_REFUSAL = "That won't press flat between the pages -- try the shelf, or the cairn if it's a stone."


def cmd_tuck(world, actor, arg):
    """tuck <thing> in journal -- press a flat curio (a feather, or the mystery seed's bloom) into this visit's journal entry; permanent, like a stone on the cairn."""
    # deferred: the journal's own entry-indexing/missing-message helpers
    # stay in content.py, alongside cmd_write/cmd_read that also use them.
    from content import _journal_entry_index, _journal_missing_message
    arg = (arg or "").strip()
    item_name = arg.lower()
    for suffix in (" in journal", " in the journal", " journal"):
        if item_name.endswith(suffix):
            item_name = item_name[:-len(suffix)].strip()
            break
    if not item_name:
        return "Tuck what in the journal? e.g.  tuck feather in journal"
    journal = find_visible(world, actor, "journal")
    if not journal:
        return _journal_missing_message(world)
    e = find_visible(world, actor, item_name, prefer=lambda x: _carrying(world, actor, x))
    if not e or e.location != actor.id:
        return f"You aren't carrying any '{arg}'."
    if not _is_tuckable(e):
        return TUCK_REFUSAL
    idx = _journal_entry_index(world, journal)
    name = e.name
    world.entities.pop(e.id, None)
    journal.attrs.setdefault("tucked", {}).setdefault(str(idx), []).append(name)
    return f"You press {_the(name)} flat between the pages. It will keep."


VERBS.update({
    "give": cmd_give,
    "place": cmd_place, "put": cmd_place,
    "stack": cmd_stack_stone,
    "thread": cmd_thread,
    "tuck": cmd_tuck,
})
