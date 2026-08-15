"""
map.py -- a hand-drawn ASCII layout of the outer world (hut/yard/forest's
edge/riverbank), rendered by `map` (cmd_map in content.py). Pure
presentation, the same shape as forest_text.py: nothing here knows about a
World or an Entity -- render_map takes nothing and returns the whole map as
a single, static string.

Deliberately hand-drawn, not laid out algorithmically from the room graph --
with four rooms in one simple hub shape (yard, with hut/forest edge/
riverbank as spokes off it), a general graph-layout algorithm would be
solving a much harder problem than the one that actually exists. If the
outer world ever grows past a simple hub, this is the file to revisit.

Deliberately no "you are here" marker. This reads as a hand-drawn map the
hero carries, not a live GPS overlay -- a drawn map doesn't know where you
are standing, and this game already says so every single turn anyway,
through `look`'s own room header. A version of this file briefly did mark
the current room; dropped once it was pointed out that the marker was
solving a problem `look` had already solved, at the cost of making the map
read like a device instead of an object.

Deliberately NOT a map of the forest's interior. See docs/FOREST_SPEC.md's
"No forest map, ever": the forest's depth is meant to feel unauthored, and a
map of it would undo that on purpose. What IS drawn -- a hazy, dotted,
oversized shape past Forest's Edge, just labeled "the forest" -- is not a
room and never becomes one: no exits, no coordinates, no entry in
ROOM_LABELS, never touched by test_map.py's completeness check. It exists
on the page for the same reason it exists in the room's own description
("the real dark begins... you don't go into. Not yet.") -- to say the
forest is there, while saying nothing at all about its shape.

Hand-drawn means the real four rooms can drift from the picture if one is
ever added without updating ROOM_LABELS/render_map to match -- test_map.py's
completeness test guards against exactly that silently happening, the same
self-checking role REFERENCE.md's docstring-coverage test plays for verbs
and behaviors.
"""

ROOM_LABELS = {
    "hut": "Hut",
    "yard": "Yard",
    "forest_edge": "Forest's Edge",
    "riverbank": "Riverbank",
}

# Width of "the forest"'s hazy shape, in characters of its dotted border
# (not counting the border itself). Oversized relative to the real rooms'
# tightly-fitted boxes on purpose -- the point is that it dwarfs them, the
# only thing on the page whose extent isn't precisely known.
_FOREST_SHAPE_WIDTH = 30


def _box(room_id):
    """A bordered ASCII box for one room, sized to fit its label exactly --
    no position marker, see module docstring."""
    label = ROOM_LABELS[room_id]
    top = "+" + "-" * (len(label) + 2) + "+"
    mid = "| " + label + " |"
    return top, mid, top


def _forest_shape():
    """A dotted-border, label-only shape for the unmapped forest beyond the
    edge -- deliberately rougher and bigger than the real rooms' crisp
    boxes, so it reads as known-to-exist but unknown-in-shape rather than
    claiming the same surveyed precision as a real room."""
    inner = _FOREST_SHAPE_WIDTH
    dotted = " ." * (inner // 2)
    border = "." + dotted + " ."
    blank = "." + " " * inner + " ."
    label = "." + "the forest".center(inner) + " ."
    return [border, blank, blank, label, blank, blank, border]


def render_map():
    """Return the outer-world ASCII map as a single static string."""
    hut_top, hut_mid, hut_bot = _box("hut")
    yard_top, yard_mid, yard_bot = _box("yard")
    forest_top, forest_mid, forest_bot = _box("forest_edge")
    river_top, river_mid, river_bot = _box("riverbank")

    # Center Forest's Edge (and its connector) over the yard box below it --
    # the yard is the hub every other room hangs off -- then center the
    # forest's hazy shape over Forest's Edge in turn.
    yard_offset = len(hut_top) + 2
    yard_center = yard_offset + len(yard_top) // 2
    forest_offset = max(0, yard_center - len(forest_top) // 2)
    forest_center = forest_offset + len(forest_top) // 2

    shape_lines = _forest_shape()
    shape_width = len(shape_lines[0])
    shape_offset = max(0, forest_center - shape_width // 2)
    shape_indent = " " * shape_offset
    findent = " " * forest_offset

    lines = [shape_indent + line for line in shape_lines]
    lines += [
        " " * forest_center + ":",
        findent + forest_top,
        findent + forest_mid,
        findent + forest_bot,
        " " * yard_center + "|",
        hut_top + "  " + yard_top + "  " + river_top,
        hut_mid + "--" + yard_mid + "--" + river_mid,
        hut_bot + "  " + yard_bot + "  " + river_bot,
    ]
    return "\n".join(lines)
