# pots.py -- clay storage pots. A shaped-clay object named "a clay ... pot"
# can hold a batch of one kind of thing (7 at a time), the first item
# stored locking what kind it accepts from then on -- "a pot of potatoes"
# and "a pot of glass pebbles" are different pots, never mixed. Declutters
# the room the same way the shelf already does: a stored item's `location`
# moves onto the pot, so it drops out of the room's own flat listing and is
# only ever mentioned through the pot's own description.
#
# See docs/ARCHITECTURE.md's "Clay storage pots" section for the design
# reasoning and the bugs this was built to avoid.

from content_common import find_visible, _the, _carrying, FOOD_KINDS

CONTAINER_CAPACITY = 7


def _is_storage_pot(name):
    """Any shaped clay object whose given name ends in "pot" -- deliberately
    NOT the hut's own fixture "tin pot" (used only for cook-flavor text),
    which doesn't start with "a clay " and so never matches this."""
    name = (name or "").lower()
    return name.startswith("a clay ") and name.endswith("pot")


def _item_kind(name):
    """The kind a pot locks to: a food's base kind (stable across cooking,
    since "an egg" and "a boiled egg" should share one pot), or the exact
    name for anything else -- a curio's name never changes once found."""
    name = (name or "").lower()
    for kind in FOOD_KINDS:
        if kind in name:
            return kind
    return name


def _strip_article(name):
    for article in ("a ", "an "):
        if name.lower().startswith(article):
            return name[len(article):]
    return name


def _kind_plural(kind):
    from curios import _plural_of   # deferred: pluralization lives in curios.py
    if kind == "potato":
        return _plural_of("a potato")
    if kind == "egg":
        return _plural_of("an egg")
    return _plural_of(kind)


def _pot_description(world, pot):
    held = world.contents(pot.id)
    if not held:
        return f"{pot.name}, empty, waiting to hold something."
    count = len(held)
    noun = _strip_article(held[0].name) if count == 1 else _kind_plural(pot.attrs.get("kind", ""))
    full = ", full up" if count >= CONTAINER_CAPACITY else ""
    return f"{pot.name}, holding {count} {noun}{full}."


def _try_store(world, actor, arg):
    """Handles "<item> in <pot>" for cmd_place (curios.py), which tries
    this first and falls through to its own shelf logic if it returns
    None -- that's "arg doesn't name a real storage pot at all", not a
    failed store, so cmd_place's "on shelf" handling still gets a chance."""
    if " in " not in arg.lower():
        return None
    item_part, _, pot_part = arg.rpartition(" in ")
    item_part, pot_part = item_part.strip(), pot_part.strip()
    if not item_part or not pot_part:
        return None
    # prefer=_is_storage_pot: the hut's own "tin pot" fixture (cook flavor
    # text, unrelated to this system) also matches a bare "pot" search --
    # without this, a real carried clay pot could lose to it by ordering
    # alone whenever both are visible at once.
    pot = find_visible(world, actor, pot_part, prefer=lambda x: _is_storage_pot(x.name))
    if not pot or not _is_storage_pot(pot.name):
        return None
    # BUG WE HIT: a pot named to describe its own contents ("a clay egg
    # pot") matches the item search too -- "egg" is a substring of both "an
    # egg" and "a clay egg pot" -- so a bare `find_visible(..., "egg")`
    # could resolve to the pot itself depending on entity order. Exclude
    # the target pot and any other storage pot from the item search.
    item = find_visible(world, actor, item_part,
                         prefer=lambda x: _carrying(world, actor, x)
                         and x.id != pot.id and not _is_storage_pot(x.name))
    if item is not None and (item.id == pot.id or _is_storage_pot(item.name)):
        item = None
    if not item or item.location != actor.id:
        return f"You aren't carrying any '{item_part}'."
    held = world.contents(pot.id)
    kind = _item_kind(item.name)
    if held and pot.attrs.get("kind") != kind:
        return f"{pot.name} already holds {_kind_plural(pot.attrs['kind'])} -- one kind per pot."
    if len(held) >= CONTAINER_CAPACITY:
        return f"{pot.name} is full -- {CONTAINER_CAPACITY} is all it holds."
    pot.attrs["kind"] = kind
    pot.attrs["display_surface"] = True
    item.location = pot.id
    pot.description = _pot_description(world, pot)
    return f"You set {_the(item.name)} in {_the(pot.name)}."


# pots.py registers no verb of its own -- cmd_place (curios.py) dispatches
# here (a deferred import) for "put/store <item> in <pot>" before falling
# back to its own "on shelf" handling, the same "one dispatch key" shape
# journal.py's tuck reach-in and content.py's wood-alias already use.
