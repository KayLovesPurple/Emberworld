"""
content_common.py -- helpers shared by content.py, cat.py, curios.py, and
drivers.py without importing any of them (breaks the import cycles a
subject module would otherwise create with content.py, the hub).

Keep this file free of verb handlers and build_world knowledge except what
can be expressed as pure functions on World/Entity. find_visible/_carrying/
_room_here moved here from content.py when curios.py needed them too --
they're name-resolution infrastructure every verb in the game reaches
through, not curio-specific, so they belong at this shared layer rather
than in either subject module.
"""

# Actor hunger rises 1/tick via content.py's hungering behavior; cap matches
# that behavior so thresholds here cannot drift from the simulation.
#
# BUG WE HIT (see sessions/20260808-113503_*, once the hunger line went
# live): a hand at or near the cap ate one cooked potato and was STILL
# flagged "getting hungry" a turn later, because the old numbers (cap 20,
# nag at 10, one meal worth 8 -- 40% of the cap) meant a single meal from
# the cap only ever reached 12, still above the nag threshold. The hand
# chased the note across three more cook-and-eat cycles in one 20-turn
# visit. Doubling the cap alone would have reproduced the exact same
# problem at a different scale (the nag-to-cap RATIO is what matters, not
# the absolute numbers) -- so alongside doubling the cap and its bands
# (same proportions as before: nag at 50%, ravenous at 80%), `cmd_cook`'s
# food value went from 40% of the old cap to 75% of the new one, so one
# meal clears the nag with real margin, from anywhere, in one bite. See
# test_one_meal_from_the_hunger_cap_clears_the_getting_hungry_note, which
# pins the relationship directly rather than any one constant alone.
#
# THE RETUNE (see sessions/20260817-213212_thistlewick_day-56_35-turns.md):
# even with that fix, a real 35-turn visit went fine -> hungry by turn 3 and
# hungry -> ravenous by turn 18 -- nearly half a visit's budget spent
# escalating before the hand even reached a ripe potato, let alone cooked
# and ate one. Same lever as before (the ratio, doubled again: cap 40 -> 80,
# stuffed and the one remaining threshold doubled in step, food value
# doubled too so "one meal clears with real margin" still holds exactly).
# But timing wasn't the only problem: "ravenous" is a strong word, and a
# hand narrating its OWN body as ravenous tends to treat that as something
# to resolve above nearly everything else, independent of whether the game
# mechanically punishes waiting -- unlike the cat's hunger, which is an
# external creature's need, not the hand's own stated condition. The top
# tier is dropped entirely rather than just delayed: hunger now has exactly
# one elevated mood ("hungry") that persists once reached rather than
# escalating further, so the language itself stops adding urgency the
# design (zero mechanical stakes) never intended. See docs/ARCHITECTURE.md's
# "Player-hunger pacing" section for the full reasoning.
ACTOR_HUNGER_CAP = 80
# Bands shared by inventory, look, and the LLM tending note (drivers.py).
ACTOR_HUNGER_STUFFED = 12
ACTOR_HUNGER_FINE = 40


def actor_hunger_mood(hunger):
    """One word mood label for the actor's current hunger level. Only three
    bands on purpose -- see the RETUNE comment above ACTOR_HUNGER_CAP for why
    a fourth, escalating tier ("ravenous") was removed rather than just
    delayed: "hungry" persists at the top instead of building toward a
    stronger word, so the language stops overstating stakes the game itself
    never had."""
    if hunger < ACTOR_HUNGER_STUFFED:
        return "stuffed"
    if hunger < ACTOR_HUNGER_FINE:
        return "fine"
    return "hungry"


def actor_hunger_line(actor):
    """Standing body-state line for look and inventory."""
    hunger = actor.attrs.get("hunger", 0)
    return f"You feel {actor_hunger_mood(hunger)}."


def actor_self_care_note(actor):
    """Short phrase for the LLM tending note when self-care needs attention.
    One tier, matching actor_hunger_mood -- see its docstring."""
    hunger = actor.attrs.get("hunger", 0)
    if hunger >= ACTOR_HUNGER_FINE:
        return "you're hungry"
    return ""


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


def _the(name):
    """'the ' + name, minus a leading indefinite article. Found curios bake
    one into their name (so the discovery and carried-item lines read
    naturally as-is), but a message that prepends its own 'the' would
    otherwise double up into 'the a smooth grey stone'."""
    for article in ("a ", "an "):
        if name.lower().startswith(article):
            return "the " + name[len(article):]
    return "the " + name


def _is_raw(e):
    return e.attrs.get("food", 0) <= 0


def _is_cooked(e):
    return e.attrs.get("food", 0) > 0


LAST_POTATO_BEAT = (
    "That was the last potato — the patch lies bare behind you now."
)


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
    still_have_raw = any(
        _is_raw(e) and "potato" in e.name for e in world.contents(actor.id)
    )
    if still_have_raw or _patch_has_crop(world):
        return ""
    return "\n" + LAST_POTATO_BEAT


def day_stamp(world):
    """The auto-prepended journal stamp: '[Day N]', or '[Day N, Name]' when
    the current hand has named itself (see drivers.py's llm_agent, which
    sets world.hand_name once at session start). Shared by cmd_write and the
    LLM sign-off so the format can't drift between the two paths -- and so
    attribution lives in the stamp itself, with nothing for a hand to sign."""
    name = getattr(world, "hand_name", None)
    return f"[Day {world.day()}, {name}]" if name else f"[Day {world.day()}]"
