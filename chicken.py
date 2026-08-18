"""
chicken.py -- the chicken, as its own self-contained subsystem: a gentle
producer, the deliberate opposite of the cat. Its constants, its two
autonomous behaviors (idle, laying), and how it's added to a fresh world.
See docs/CHICKEN_SPEC.md for the full design, and cat.py for the sibling
subsystem this mirrors.

THE CONSTRAINT THAT MUST NEVER BREAK: the chicken has no hunger, no
feeding verb, and no state it can be neglected in. It can never come to
harm because there is nothing about it to neglect. Do not add a hunger
attr, ever -- see docs/CHICKEN_SPEC.md's "A trap explicitly not being
built."
"""

from world import Entity, BEHAVIORS


def _chicken_cap(chicken):
    # for the start of a sentence: "Henrietta ..." if named, else "The chicken ..."
    return chicken.attrs.get("given_name") or "The chicken"


def _chicken_description(chicken):
    name = chicken.attrs.get("given_name")
    if name:
        return f"{name}, a brown hen, pecking about the yard"
    return "a brown hen, pecking about the yard, feathers ruffled by the wind"


CHICKEN_IDLE_CHANCE = 0.12   # mirrors cat_idle's own chance

CHICKEN_IDLE_LINES = (
    "{chicken} scratches at the dirt, then loses interest.",
    "{chicken} freezes, head cocked, at nothing in particular.",
    "{chicken} settles into a shallow dust-bath by the fence.",
    "{chicken} struts a tight circle and clucks once, satisfied.",
    "{chicken} preens a wing, feather by feather.",
)


def chicken_idle(world, chicken):
    """Autonomous: ambient yard-life, purely cosmetic. No hunger gate, unlike
    cat_idle -- the chicken has no hunger to gate on; see this file's own
    THE CONSTRAINT THAT MUST NEVER BREAK note."""
    if world.rng.random() < CHICKEN_IDLE_CHANCE:
        line = world.rng.choice(CHICKEN_IDLE_LINES).format(chicken=_chicken_cap(chicken))
        world.announce(line, chicken.location)


# Small and independent, on the chicken's own schedule -- NOT a found-roll
# layered onto another action (unlike forest_finds riding on gather wood).
# An egg is discoverable by being in the room, the same way a low hearth
# just is, not by a roll on a deliberate forage action. See
# docs/CHICKEN_SPEC.md's "The chicken itself".
CHICKEN_LAY_CHANCE = 0.06

CHICKEN_LAY_LINES = (
    "{chicken} clucks once, pleased with itself -- there's a fresh egg in the straw.",
    "{chicken} steps back from a fresh egg, ruffling her feathers.",
)


def chicken_lay(world, chicken):
    """Autonomous: now and then, an egg. See CHICKEN_LAY_CHANCE's comment
    for why this never rides on another action's roll."""
    if world.rng.random() >= CHICKEN_LAY_CHANCE:
        return
    world.add(Entity(world.fresh_id("egg"), "an egg",
                      "a small brown egg, still warm", location=chicken.location,
                      portable=True))
    line = world.rng.choice(CHICKEN_LAY_LINES).format(chicken=_chicken_cap(chicken))
    world.announce(line, chicken.location)


BEHAVIORS.update({"chicken_idle": chicken_idle, "chicken_lay": chicken_lay})


def chicken_actions(world, actor):
    """What the chicken offers a hand sharing its room -- just naming it,
    for now, if it hasn't been named yet. No petting, no feeding: see
    docs/CHICKEN_SPEC.md's explicit scope.

    Lives here rather than in the engine's action list for the same reason
    cat_actions does in cat.py -- registered into ACTION_SOURCES by
    content.py, which owns the order the whole list is read in."""
    chicken = world.get("chicken")
    if chicken is None or chicken.location != actor.location:
        return []
    if chicken.attrs.get("given_name"):
        return []
    return ["name chicken <name>"]


def build_chicken(world):
    """Add the chicken to a freshly-assembled world, in the yard, with its
    two autonomous behaviors attached. Yard-only, permanently -- no
    wandering behavior exists to attach; see docs/CHICKEN_SPEC.md's design
    goal #5. Do not add one without revisiting that doc first."""
    chicken = world.add(Entity("chicken", "chicken",
        "a brown hen, pecking about the yard, feathers ruffled by the wind",
        location="yard"))
    chicken.attach("chicken_idle")
    chicken.attach("chicken_lay")
    return chicken


def ensure_chicken(world):
    """Add the chicken to a world that predates it (fresh build or an
    older save) -- same backfill role as ensure_riverbank/ensure_shelf."""
    if world.get("chicken") is None:
        build_chicken(world)
    return world.get("chicken")
