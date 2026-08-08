"""
content_common.py -- helpers shared by content.py, cat.py, and drivers.py
without importing either module (breaks the cat<->content import cycle).

Keep this file free of verb handlers and build_world knowledge except what
can be expressed as pure functions on World/Entity.
"""

# Actor hunger rises 1/tick via content.py's hungering behavior; cap matches
# that behavior so thresholds here cannot drift from the simulation.
ACTOR_HUNGER_CAP = 20
# Bands shared by inventory, look, and the LLM tending note (drivers.py).
ACTOR_HUNGER_STUFFED = 3
ACTOR_HUNGER_FINE = 10
ACTOR_HUNGER_HUNGRY = 16


def actor_hunger_mood(hunger):
    """One word mood label for the actor's current hunger level."""
    if hunger < ACTOR_HUNGER_STUFFED:
        return "stuffed"
    if hunger < ACTOR_HUNGER_FINE:
        return "fine"
    if hunger < ACTOR_HUNGER_HUNGRY:
        return "hungry"
    return "ravenous"


def actor_hunger_line(actor):
    """Standing body-state line for look and inventory."""
    hunger = actor.attrs.get("hunger", 0)
    return f"You feel {actor_hunger_mood(hunger)}."


def actor_self_care_note(actor):
    """Short phrase for the LLM tending note when self-care needs attention."""
    hunger = actor.attrs.get("hunger", 0)
    if hunger >= ACTOR_HUNGER_HUNGRY:
        return "you're ravenous"
    if hunger >= ACTOR_HUNGER_FINE:
        return "you're getting hungry"
    return ""


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
