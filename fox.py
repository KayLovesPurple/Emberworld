"""
fox.py -- the fox, per docs/FOX_SPEC.md. The cat's wild counterpart: a
relationship on lineage-time rather than visit-time, built one offering
at a time across many hands, texture that deepens in stages, and --
past a trust ceiling -- rare gifts on her own clock, hard-decoupled from
any single offering (see FOX_SPEC.md's "trap explicitly not being
built": a legible offering->gift link turns her into a vending machine).

THE CONSTRAINT THAT MUST NEVER BREAK: the fox can never come to harm and
can never do harm -- no hunger, no need, trust never decreases. She is
not an entity, ever: there is no fox object anywhere in the world for
any of that to happen TO. All her state lives in attrs on the yard
(trust, given name, gift-suppression window); the only entities this
file ever creates are the sign of her (a trace, same idea as a
cat-given trace -- not the fox herself) and, rarely, a gift.
"""

from world import Entity, VERBS, BEHAVIORS
from content_common import banded, find_visible, _carrying

FOX_SIGN_ID = "fox_sign"

# Trust is a one-way lifetime ratchet -- one offering resolved, forever
# +1, never decreasing (see fox_tending; nothing in this file ever
# subtracts from it). Thresholds are tuning, like every pacing number in
# this game -- a first guess, easy to retune once a real lineage has
# actually lived with it a while. Picked so an attentive lineage reaches
# the ceiling in a modest number of visits, not a single one and not
# never: eggs lay often enough (chicken.CHICKEN_LAY_CHANCE) that offering
# one every so often is a real, repeatable choice, not a rare fluke.
FOX_TRUST_GLIMPSE = 3
FOX_TRUST_SEEN = 6       # naming unlocks here -- see content.py's cmd_name
FOX_TRUST_LINGERS = 10
FOX_TRUST_CEILING = 15   # gifts become possible, on her own clock, forever after

# Count-based tiers, same shape as the cairn's height bands and the
# charm-string's count bands (see content_common.banded) -- deliberately
# capped at "lingers": trust keeps counting past the ceiling, but nothing
# further gates on it, so there's no fifth line to write. No band at 0 --
# fox_sign_text/the sign entity are never touched until the first
# offering actually resolves (trust becomes 1), so trust is never 0 by
# the time this is called.
FOX_SIGN_BANDS = (
    (1, "small prints in the dew, gone at the gate"),
    (FOX_TRUST_GLIMPSE, "something russet at the treeline at dusk, gone before you're sure"),
    (FOX_TRUST_SEEN, "she was seen, once, taking the egg"),
    (FOX_TRUST_LINGERS, "she paused a beat before the dark took her, egg and all"),
)


def _fox_sign_text(trust, given_name):
    """The current stage's texture, with her name folded in once a hand's
    decided one -- "prints in the dew again; Sorrel, someone decided" is
    how a memoryless hand inherits both her existence and her name in one
    line, the same trick the cat's given name already pulls."""
    from content_common import banded
    text = banded(FOX_SIGN_BANDS, trust)
    if given_name:
        text += f"; {given_name}, someone decided"
    return text


def ensure_fox(world):
    """Attach the fox's tending behavior to the yard -- same backfill role
    as ensure_shelf/ensure_cairn, except there's no fox entity to create,
    just a behavior to make sure is attached.

    BUG WE HIT (caught before it shipped): Entity.attach() doesn't dedupe
    -- calling it twice on an already-fox-aware yard would attach
    fox_tending a second time, running it twice per tick. Guarded by
    checking behavior_names first, the same way a fresh build's yard
    (attached once in build_world) and an older save's yard (missing it
    entirely) both end up in exactly one attached copy either way."""
    yard = world.get("yard")
    if yard is None:
        return
    if "fox_tending" not in yard.behavior_names:
        yard.attach("fox_tending")


def cmd_leave_egg_out(world, actor, arg):
    """leave egg out -- leave a carried egg (raw or cooked, she's not fussy) by the fence overnight for whoever the night brings; one-way, and at most one offering out at a time."""
    if actor.location != "yard":
        return "There's nowhere to leave that out here -- try the yard."
    if any(e.attrs.get("fox_offering") for e in world.contents("yard")):
        return "There's already an offering out -- best wait and see what becomes of it."
    egg = find_visible(world, actor, "egg", prefer=lambda x: _carrying(world, actor, x))
    if not egg or egg.location != actor.id:
        return "You've no egg to leave out."
    egg.location = "yard"
    egg.portable = False
    egg.attrs["fox_offering"] = True
    egg.description = "an egg left by the fence, for whoever the night brings."
    return "You set the egg down by the fence and step back. Whatever finds it, finds it."


# A small, fox-specific pool, not reused forest curios -- she travels
# where no hand can ever go, so her gifts read as postcards from off the
# map. Shaped exactly like curios.FOUND_ITEMS (name, look_line,
# cat_reaction) for the same reason: cat_reaction drives what
# `give <thing> to cat` does with it, same as any other curio -- "there
# is something right about giving Ember a fox's gift."
FOX_GIFT_POOL = (
    ("a feather from no bird the yard knows",
     "barred in colors nothing local wears", "plays"),
    ("a pebble smoothed by some upstream water",
     "cool, rounder than anything the riverbank offers", "ignores"),
    ("a scrap of faded ribbon",
     "sun-bleached and frayed, from nowhere anyone here has been", "ignores"),
    ("a tiny blue eggshell",
     "no bird here lays anything like it", "ignores"),
)

# Rarer than a forest find (content.FOREST_FIND_CHANCE, 0.08) -- a gift
# should be an event a journal entry gets written about, not a faucet.
FOX_GIFT_CHANCE = 0.03

# Two full days (DAY_LENGTH ticks each) -- long enough that the
# correlation between any one offering and a later gift can never be
# observed, even by accident. See FOX_SPEC.md's "trap explicitly not
# being built."
FOX_GIFT_SUPPRESSION_TICKS = 48


def _fox_gift_description(look_line, reaction):
    text = look_line
    if reaction == "plays":
        text += " -- the cat might bat at it"
    return text + "; it smells faintly of fox, and of somewhere else."


def fox_tending(world, yard):
    """Autonomous, attached to the yard itself (there being no fox entity
    to attach it to): resolves a waiting offering the moment night falls
    -- always, from the first offering onward, since an untouched
    offering would just rebuild the egg clutter one room over -- and,
    entirely independently, rolls a rare gift once trust has crossed its
    ceiling. The two are deliberately never in the same conditional: an
    offering resolving never itself triggers or blocks this tick's gift
    roll beyond setting the suppression window, so a gift's timing can
    never be read as a response to any specific offering."""
    offering = next((e for e in world.contents(yard.id) if e.attrs.get("fox_offering")), None)
    if offering is not None and world.phase() == "night":
        world.entities.pop(offering.id, None)
        trust = yard.attrs.get("fox_trust", 0) + 1
        yard.attrs["fox_trust"] = trust
        yard.attrs["fox_suppress_until"] = world.time + FOX_GIFT_SUPPRESSION_TICKS
        sign = world.get(FOX_SIGN_ID)
        if sign is None:
            sign = world.add(Entity(FOX_SIGN_ID, "sign of the fox", "", location=yard.id))
        sign.description = _fox_sign_text(trust, yard.attrs.get("fox_given_name"))

    trust = yard.attrs.get("fox_trust", 0)
    if trust < FOX_TRUST_CEILING:
        return
    if any(e.attrs.get("fox_gift") for e in world.contents(yard.id)):
        return
    if world.time < yard.attrs.get("fox_suppress_until", 0):
        return
    if world.rng.random() < FOX_GIFT_CHANCE:
        name, look_line, reaction = world.rng.choice(FOX_GIFT_POOL)
        world.add(Entity(world.fresh_id("foxgift"), name,
                          _fox_gift_description(look_line, reaction),
                          location=yard.id, portable=True,
                          attrs={"curio": True, "cat_reaction": reaction, "fox_gift": True}))


BEHAVIORS.update({"fox_tending": fox_tending})


def fox_actions(world, actor):
    """What the fox offers, wherever a hand happens to be: leaving an egg
    out (yard only, an egg in hand, no offering already waiting) and
    naming her once she's been seen -- unconditioned on location, unlike
    the cat/chicken's own naming, since she's never present anywhere to
    require standing near; a hand names what it's heard of, not what it
    sees in front of it."""
    yard = world.get("yard")
    acts = []
    if actor.location == "yard":
        has_egg = any("egg" in e.name.lower() and not e.attrs.get("fox_offering")
                       for e in world.contents(actor.id))
        offering_out = any(e.attrs.get("fox_offering") for e in world.contents("yard"))
        if has_egg and not offering_out:
            acts.append("leave egg out")
    if yard is not None and yard.attrs.get("fox_trust", 0) >= FOX_TRUST_SEEN \
            and not yard.attrs.get("fox_given_name"):
        acts.append("name fox <name>")
    return acts


VERBS.update({"leave": cmd_leave_egg_out})
