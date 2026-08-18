"""
content_common.py -- helpers shared by content.py, cat.py, and drivers.py
without importing either module (breaks the cat<->content import cycle).

Keep this file free of verb handlers and build_world knowledge except what
can be expressed as pure functions on World/Entity.
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
