"""
forest_text.py -- the forest's generated texture: the fragment pools the
near/mid/deep bands draw from, and the independent ambient lines layered on
top. FOREST_SPEC.md Stages 2 and 6.

Pure prose and the two small functions that compose it. Nothing here knows
about a World, an Entity, or a verb -- describe_forest and _forest_ambient
take an rng and return a string, which is why this lifted out of content.py
cleanly when the rest of the forest could not.

Split out because it's the largest single block of writing in the game and
it's read and edited as writing -- adding a fragment means weighing it
against its neighbours in the same pool, not against the mechanics that call
it. The mechanics (venture/return, depth, the statue, the cairn) stay in
content.py with the design notes that justify them; those notes and their
code are one unit and shouldn't be prised apart.
"""

# FOREST_SPEC.md Stage 2 -- texture generation: fragments, not rooms. Each
# band (near/mid/deep, keyed by depth -- see _forest_band) holds four
# independent pools of bare, lowercase clauses -- light, sound, undergrowth,
# smell -- composed into one line by describe_forest below, so no two visits
# (or two steps running) read quite the same. Depth 0 is the edge itself,
# already covered by forest_edge's own fixed room description, so bands only
# start at depth 1 -- there's nothing here to describe once you're back out.
FOREST_FRAGMENTS = {
    "near": {
        "light": (
            "grey daylight still finds its way down between the trunks",
            "the sun still reaches you here, broken into moving coins on the ground",
            "shade is thicker now, but never quite full dark",
            "light comes down at a slant, catching dust and midges in it",
            "the canopy is patchy enough yet to let the sky show through in places",
        ),
        "sound": (
            "the yard's small sounds have thinned to almost nothing",
            "a twig cracks somewhere behind you, and nothing follows it",
            "birdsong carries from a little further off than before",
            "the quiet here still has an edge of the yard in it",
            "leaves stir overhead in a breeze that never quite reaches you down here",
        ),
        "undergrowth": (
            "bracken brushes at your knees on either side of the path",
            "the ground is soft with old leaves, the path still easy to follow",
            "a fallen branch blocks half the way, easy enough to step around",
            "moss creeps up the near trunks in a green tide",
            "the path is still a path here, worn if narrow",
        ),
        "smell": (
            "the air smells faintly of woodsmoke, carried from the yard behind you",
            "damp earth and green growing things",
            "a cold, clean smell, like the inside of a held breath",
            "leaf-mould, and something sweet underneath it, unplaceable",
            "the smell of rain that fell here yesterday and hasn't quite left",
        ),
    },
    "mid": {
        "light": (
            "the canopy has closed overhead; what light there is comes in patches",
            "the trees stand closer together here, closer to the dark between them",
            "what daylight reaches this far is old and green by the time it lands",
            "shadow pools in the hollows between the roots",
            "the light here doesn't seem to come from any one direction",
        ),
        "sound": (
            "the quiet is heavier here -- not empty, just unwilling to explain itself",
            "something moves, once, well off to one side, and doesn't move again",
            "your own footsteps sound louder than they should",
            "no birds reach this far in -- just the trees, working at something slow",
            "a sound like breathing that isn't yours settles and is gone",
        ),
        "undergrowth": (
            "the path has thinned to a suggestion between the roots",
            "brambles close ranks and have to be pushed through, not stepped around",
            "fallen trunks lie half-sunk in their own moss, going soft",
            "the ground gives more than it should underfoot, spongy with old growth",
            "roots cross the ground like something laid down on purpose",
        ),
        "smell": (
            "the smell of rot and green growth in equal measure",
            "wet bark, and something faintly sweet turning to something else",
            "a cold stone-smell, though no stone is in sight",
            "everything smells a little like rain that hasn't fallen yet",
            "the air is close and smells of things breaking down slowly",
        ),
    },
    "deep": {
        "light": (
            "what light there is here doesn't feel like it started at the sun",
            "the dark presses close even at midday -- this is what the edge warned you about",
            "the trees have stopped admitting daylight at all in places",
            "you can make shapes out, barely, in a green-black gloom",
            "there is no real light here, only degrees of dark",
        ),
        "sound": (
            "the silence here has a weight to it, like something listening back",
            "far off, something large enough to matter moves, and then is gone",
            "your own breathing is the loudest thing for a long moment",
            "nothing sings this deep. nothing needs to",
            "the quiet doesn't feel empty so much as occupied",
        ),
        "undergrowth": (
            "there is no path here, only the gaps between trunks that happen to fit you",
            "the ground is uneven, root and hollow, easy to lose your footing on",
            "everything underfoot is soft with rot, sinking a little at each step",
            "old growth has folded in on itself here, tangled past reading",
            "the trees stand closer than they have any reason to",
        ),
        "smell": (
            "the air is cold and still and tastes faintly of iron",
            "a smell like a held breath let go all at once",
            "everything smells of old water, standing somewhere out of sight",
            "green, and beneath it something that isn't",
            "the smell of a place that doesn't get visited",
        ),
    },
}


def _forest_band(depth):
    """Which fragment band a given forest depth falls into -- contiguous and
    gapless from depth 1 upward. Depth 0 is the edge itself and isn't banded;
    only venturing past it draws from these pools."""
    if depth <= 2:
        return "near"
    if depth <= 5:
        return "mid"
    return "deep"


def describe_forest(depth, rng):
    """Build one line of texture for the current forest depth: pick a
    fragment from each pool (light, sound, undergrowth, smell) in the
    matching band and join them, so two visits at the same depth -- or two
    steps in a row -- rarely read alike. Always draws through the passed-in
    `rng` (world.rng at the call sites below) so --fuzz stays reproducible
    under a fixed seed."""
    band = FOREST_FRAGMENTS[_forest_band(depth)]
    parts = [rng.choice(pool) for pool in band.values()]
    text = "; ".join(parts) + "."
    return text[0].upper() + text[1:]


# FOREST_SPEC.md Stage 6 -- ambient, unscripted texture: the actual "crack
# in the closedness." Unlike FOREST_FRAGMENTS (which always fires, banded
# by depth, describing what's *there*), this is a small independent chance
# of something happening that isn't tied to depth or to any verb -- no
# "investigate" option references it, and it explains nothing, same
# restraint as the statue. Layered on top of whatever describe_forest
# already returned that step, never in place of it.
FOREST_AMBIENT_CHANCE = 0.12

FOREST_AMBIENT = (
    "somewhere off to the side, a branch cracks, and nothing follows it",
    "a smell drifts past, unplaceable, and then it's gone",
    "an unseen bird runs through a few notes and stops",
    "something rustles low in the undergrowth, gone by the time you look",
    "a cold thread of air crosses your path and is gone",
    "the light shifts, just slightly, though nothing overhead moved",
)


def _forest_ambient(rng):
    """Rolls FOREST_AMBIENT_CHANCE and returns "" most of the time, or a
    leading-space-prefixed line so call sites can just append the result
    (`+ _forest_ambient(world.rng)`) without an if-statement of their own.
    Draws through the same passed-in rng as describe_forest, for the same
    --fuzz-reproducibility reason."""
    if rng.random() < FOREST_AMBIENT_CHANCE:
        return " " + rng.choice(FOREST_AMBIENT)
    return ""
