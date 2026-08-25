"""
journal.py -- the shared journal as its own self-contained subsystem:
writing an entry, reading the capped/spread view a hand actually sees,
and the entry-indexing bookkeeping curios.py's tuck-in-journal reaches
for. Split out of content.py once it grew into a coherent slice on its
own, the same way cat.py/chicken.py/curios.py did -- see
docs/ARCHITECTURE.md's note on this split.
"""

import random

from world import VERBS, FREE_VERBS
from content_common import day_stamp as _day_stamp, find_visible, _carrying


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
    entries = journal.attrs.setdefault("entries", [])
    idx = world.journal_entry_index
    # A tuck earlier this visit with nothing written yet left a placeholder
    # entry ("nothing written, just left something pressed here.") -- upgrade
    # it in place instead of appending a second entry, so the write and the
    # tucked item's note end up on the same line rather than split across two.
    if (world.journal_entry_is_placeholder and idx is not None
            and idx < len(entries)):
        entries[idx] = f"{_day_stamp(world)} {arg}"
    else:
        entries.append(f"{_day_stamp(world)} {arg}")
        idx = len(entries) - 1
    # the entry a same-visit `tuck` attaches to -- see _journal_entry_index.
    world.journal_entry_index = idx
    world.journal_entry_is_placeholder = False
    return "You write in the journal. The ink dries slowly. It will keep."


# A lineage's journal only ever grows -- showing the whole thing on every
# read turns a quick catch-up into an ever-longer wall of past visits. The
# full history is never lost (still all in entries, and cmd_write always
# appends to it); only what a single `read journal` shows is capped.
JOURNAL_READ_LIMIT = 5        # the recent tail, always shown
JOURNAL_OLDER_SHOWN = 6       # entries drawn from further back, so the tail
                              # can never be the whole of a lineage's memory
                              # -- weighted toward history over recency on
                              # purpose (see journal_view), so a one-off
                              # entry (the statue's discovery, say) keeps
                              # getting real odds of being read long after
                              # it scrolls out of anyone's recent tail
JOURNAL_GAP = "..."           # marks where the view skipped over entries


def journal_view(entries, keep=JOURNAL_READ_LIMIT, older=JOURNAL_OLDER_SHOWN):
    """Which entries a hand actually sees: the first (it's the one that
    orients someone with no memory), then `older` drawn from across
    everything in between, then the last `keep`. Gaps are marked with
    JOURNAL_GAP so the view never pretends to be the whole record.

    BUG WE HIT: this used to be a plain tail. In real play a stretch of
    visits where every hand hit the same trouble wrote the same warning
    over and over, and the tail meant an arriving hand inherited nothing
    BUT those warnings -- so it wrote another one, and the journal locked
    itself into a single register for a week of world-time. The journal is
    the strongest thing in this world for setting how a visit feels, and a
    pure-recency window hands that entirely to whatever the last few hands
    happened to be going through. Reaching back across the whole history is
    what stops any one stretch of it becoming all of it.

    The `older` picks are seeded, not truly random and not fixed evenly-
    spaced positions either -- a real-play ask, wanting a one-off entry
    (a hand's only mention of finding the statue, say) to keep getting a
    real chance of being read by later hands as the journal grows, not a
    single lucky window. The original evenly-spaced version moved its
    sample points smoothly as the journal grew, which meant a given entry
    was only ever included while a span happened to be sweeping past it,
    then lost it for good once the span moved on. Seeding by `len(entries)`
    instead means every new entry changes which middle entries get sampled,
    so a specific entry gets an independent fresh chance each time the
    journal grows further, rather than a one-time window it can permanently
    fall outside of. Still deterministic for a GIVEN journal length, for
    the same two reasons as before: a hand who reads twice must see the
    same thing (the LLM driver's prompt tells it the journal "won't change"
    once read), and a book doesn't reshuffle which pages fall open on a
    second look -- seeded by length, never by world.rng, which would break
    exactly that.

    Deliberately blind to what the entries SAY. Choosing them by content --
    biasing away from whatever the recent ones are about -- would work, and
    would quietly make us the editor of what the lineage remembers. Position
    is ours to choose; meaning isn't."""
    entries = list(entries)
    indices = _journal_view_indices(len(entries), keep, older)
    return [entries[i] if i is not None else JOURNAL_GAP for i in indices]


def _journal_view_indices(n, keep=JOURNAL_READ_LIMIT, older=JOURNAL_OLDER_SHOWN):
    """journal_view's exact selection, as indices into the entries list
    (None where it shows a gap) instead of the entries themselves -- so a
    caller that needs to know WHICH entry is on screen (cmd_read, to look up
    anything tucked into it) can reuse the identical picks rather than
    re-deriving them and risking drift from journal_view's own algorithm."""
    if n <= keep + older:
        return list(range(n))
    tail_start = n - keep
    middle = list(range(1, tail_start))
    take = min(older, len(middle))
    # A fresh, locally-seeded Random -- never world.rng, whose shared
    # stream would make a second read (or any other roll that happens to
    # fall between two reads) change what's shown. Seeded by `n` alone,
    # so it depends only on how long the journal is, not on anything it
    # says (see journal_view's own note on staying content-blind).
    positions = sorted(random.Random(n).sample(range(len(middle)), take))
    out, prev = [0], -1
    for pos in positions:
        if pos > prev + 1:
            out.append(None)
        out.append(middle[pos])
        prev = pos
    if len(middle) - 1 > prev:
        out.append(None)
    return out + list(range(tail_start, n))


def _tucked_line(journal, idx):
    """The parenthetical naming whatever a hand pressed into entry `idx` --
    "" if nothing was. Uses the item's own found-name as-is ("a jay's
    feather"), the same register as a room listing, not "the jay's
    feather" -- there's no antecedent to shorten it against here."""
    names = journal.attrs.get("tucked", {}).get(str(idx))
    if not names:
        return ""
    if len(names) == 1:
        return f" ({names[0]} is pressed into this page.)"
    return f" ({', '.join(names)} are pressed into this page.)"


def cmd_read(world, actor, arg):
    """read journal -- read the journal (needs light unless you're holding it); shows a spread of entries rather than all of them, and `read journal all` shows the lot; anything tucked into a shown entry (see `tuck`) is named alongside it."""
    arg = (arg or "").strip()
    show_all = arg.lower() == "all" or arg.lower().endswith(" all")
    if show_all:
        arg = arg[:-len("all")].strip()
    journal = find_visible(world, actor, arg or "journal")
    if not journal or "entries" not in journal.attrs:
        return "There's nothing written there."
    if world.is_dark(actor.location) and not _carrying(world, actor, journal):
        return "Too dark to read. Pick it up, or bring a light."
    entries = journal.attrs["entries"]
    if not entries:
        return "The journal is blank, waiting for someone's first entry."
    if show_all:
        lines = [f"  {ln}{_tucked_line(journal, i)}" for i, ln in enumerate(entries)]
        return "The journal reads, all of it:\n" + "\n".join(lines)
    indices = _journal_view_indices(len(entries))
    shown = [entries[i] if i is not None else JOURNAL_GAP for i in indices]
    header = "The journal reads:"
    written = [ln for ln in shown if ln != JOURNAL_GAP]
    if len(written) < len(entries):
        header = (f"The journal reads ({len(written)} of {len(entries)} "
                   f"entries, spread across its whole run -- "
                   f"`read journal all` for the rest):")
    lines = [f"  {ln}{'' if i is None else _tucked_line(journal, i)}"
             for i, ln in zip(indices, shown)]
    return header + "\n" + "\n".join(lines)


# _journal_entry_index -- the entry-indexing bookkeeping cmd_tuck reaches
# for (curios.py, via a deferred import, same pattern as cat.py's cmd_feed
# reaching for content.py's cmd_add_wood). Stays here, next to cmd_write
# and cmd_read which are its other two callers.
def _journal_entry_index(world, journal):
    """The entry a tuck belongs to: whatever's already active this visit --
    a prior write, or an earlier tuck's own placeholder -- or, if nothing's
    touched the journal yet this visit, a fresh placeholder entry, so a
    visit that only tucks and writes nothing still works. Session-scoped
    (world.journal_entry_index, aliasing VisitState) -- resets every visit,
    same as forest_depth and the rest."""
    idx = world.journal_entry_index
    entries = journal.attrs.setdefault("entries", [])
    if idx is not None and idx < len(entries):
        return idx
    # No mention of "pressed" here -- _tucked_line's own parenthetical,
    # which always follows a placeholder entry (this is only ever called
    # from cmd_tuck, right before it records the tuck), already says that.
    entries.append(f"{_day_stamp(world)} — nothing written this visit.")
    idx = len(entries) - 1
    world.journal_entry_index = idx
    world.journal_entry_is_placeholder = True
    return idx


VERBS.update({"write": cmd_write, "read": cmd_read})
FREE_VERBS.update({"read"})
