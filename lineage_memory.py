"""
lineage_memory.py -- the Lineage Memory Observatory (v1, rule-based): what
recurring patterns are showing up in the shared journal, surfaced for the
developer via `--lineage-report`, never fed back into the game. See
docs/LINEAGE_MEMORY_OBSERVATORY.md for the full design and
docs/ARCHITECTURE.md's "Lineage Memory" section for what actually landed
and what's still deliberately deferred.

Deliberately one-way and self-contained: this module imports nothing from
world.py/content.py/drivers.py, and nothing it produces is ever read back
into a prompt, a description, or any world state. The game reaches out to
sync it (see sync_lineage_memory); it never reaches back in.
"""

import json
import os
import re

LINEAGE_MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lineage_memory.json")

# Hand-authored, not derived -- same discipline as content.py's FOUND_ITEMS
# and _CURIO_PLURALS. A word list that tried to guess synonyms or stem
# inflections automatically would drift into false positives no one chose;
# every trigger word here is a deliberate inclusion, in a small enough
# table to read in full and adjust once a real report shows it's off.
#
# KNOWN IMPRECISION, accepted rather than engineered around: "well" is
# also an ordinary English discourse word ("Well, I planted the potato").
# Matching it will occasionally count a sentence-opener as a mention of
# the entity. Rule-based extraction can't tell the two apart without
# either fragile heuristics or the LLM step this v1 deliberately defers --
# see docs/LINEAGE_MEMORY_OBSERVATORY.md's Status note.
CANDIDATE_ENTITIES = {
    "well": ["well"],
    "cairn": ["cairn"],
    "forest": ["forest", "trees", "woods"],
    "hearth": ["hearth", "fire", "fireplace"],
    "lamp": ["lamp"],
    "shelf": ["shelf"],
    "statue": ["statue"],
    "cat": ["cat"],
}

# Broad categories (docs/LINEAGE_MEMORY_OBSERVATORY.md section 14), not an
# attempt to classify every sentence -- "the purpose is to surface
# patterns, not perfectly classify every sentence" is the doc's own words.
CANDIDATE_CONCEPTS = {
    "mystery": ["mysterious", "mystery", "secret", "unknown", "unknowable",
                "strange", "odd", "eerie"],
    "comfort": ["cozy", "comfort", "comforting", "warm", "safe", "calm",
                "gentle", "peaceful"],
    "danger": ["danger", "dangerous", "threat", "threatening", "ominous",
               "scary", "afraid", "fear", "unsettling"],
    "beauty": ["beautiful", "beauty", "lovely", "pretty", "striking",
               "stunning"],
    "usefulness": ["useful", "handy", "practical", "helps", "helpful"],
    "memory": ["remembers", "remember", "remembered", "memory", "memories",
               "recalls", "keeps"],
    "affection": ["affection", "love", "loves", "dear", "fond", "cherish",
                  "cherished"],
    "curiosity": ["curious", "curiosity", "wonder", "wondered", "intriguing",
                  "fascinating", "fascinated"],
}


def _matches(text, table):
    """Which keys of `table` (CANDIDATE_ENTITIES or CANDIDATE_CONCEPTS) have
    at least one trigger word present in `text`, on a real word boundary --
    never a bare substring check, so "cat" doesn't fire on "cattle" and
    "hearth" doesn't fire on "hearthside"."""
    lowered = text.lower()
    found = set()
    for key, words in table.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", lowered):
                found.add(key)
                break
    return found


def find_entities(text):
    """Candidate entities mentioned in one journal entry's text."""
    return _matches(text, CANDIDATE_ENTITIES)


def find_concepts(text):
    """Candidate concepts present in one journal entry's text."""
    return _matches(text, CANDIDATE_CONCEPTS)


_STAMP_RE = re.compile(r"^(\[Day \d+(?:, [^\]]+)?\])\s*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text):
    """Split one journal entry into its own sentences, each with the
    entry's own [Day N] / [Day N, Name] stamp reattached -- a later
    sentence in a multi-sentence entry would otherwise carry no day/name
    context of its own, unlike when the whole entry was the unit. A naive
    period/question/exclamation-mark split; the game's journal entries are
    short, casual, first-person prose, not text with abbreviations or
    decimals a smarter splitter would need to guard against."""
    m = _STAMP_RE.match(text)
    stamp, body = (m.group(1), text[m.end():]) if m else (None, text)
    parts = [s.strip() for s in _SENTENCE_SPLIT_RE.split(body) if s.strip()]
    if not parts:
        parts = [body.strip()] if body.strip() else []
    return [f"{stamp} {s}" for s in parts] if stamp else parts


def extract_associations(text):
    """The (entity, concept, excerpt) triples one entry is evidence for.

    Matching is scoped to a single SENTENCE, not the whole entry -- every
    entity mentioned in a sentence cross-products with every concept
    mentioned in that SAME sentence, `excerpt` being that sentence (stamp
    reattached, see _sentences). This is narrower than the entry-wide
    matching the first version shipped with: a real report showed one
    entry mentioning both the cat, in one sentence, and (in a LATER
    sentence) "the forest is dangerous after dark" cross-producting into
    (cat, danger) even though the danger was only ever about the forest.
    Sentence-scoping fixes this at the source rather than just making it
    auditable after the fact.

    This is deliberately the seam a future LLM-based extraction step
    replaces (see docs/LINEAGE_MEMORY_OBSERVATORY.md's Status note):
    everything that calls this function hands it a whole entry and gets
    (entity, concept, excerpt) triples back, and neither the caller nor
    the return shape needs to change when the sentence-splitting here is
    eventually replaced by something that actually understands the text --
    an LLM step can judge relatedness across a sentence boundary a regex
    never will, and should return the same shape doing it.

    A pair appearing more than once in the same entry (across two
    sentences, say) still counts once -- the unit of evidence is the
    entry, not the raw sentence or word count. The FIRST matching
    sentence wins as the representative excerpt."""
    seen = set()
    triples = []
    for sentence in _sentences(text):
        entities, concepts = find_entities(sentence), find_concepts(sentence)
        for e in sorted(entities):
            for c in sorted(concepts):
                if (e, c) in seen:
                    continue
                seen.add((e, c))
                triples.append((e, c, sentence))
    return triples


def new_memory():
    """An empty Lineage Memory. `processed_through` is bookkeeping (how
    many journal entries have been folded in so far), kept in its own
    envelope key rather than mixed in among entity data -- entity keys
    only ever come from CANDIDATE_ENTITIES, but keeping the shapes
    separate (matches World.to_data()'s own envelope-plus-payload shape)
    means a future bookkeeping field never risks colliding with one."""
    return {"processed_through": 0, "entities": {}}


def record_entry(memory, index, text):
    """Fold one journal entry (at list position `index`, its own permanent
    identity -- see docs/LINEAGE_MEMORY_OBSERVATORY.md's Status note on why
    this is the entry itself, not a derived "visit": two different hands
    sharing a name on the same day is a real, observed occurrence, and
    trying to merge same-(day,name) entries into one visit would silently
    conflate them) into `memory`, in place. A no-op for an entry with no
    entity/concept match at all.

    Each association keeps its own excerpt (the specific sentence it came
    from -- see extract_associations) alongside the entry's index, not
    just a day number. Before sentence-scoped matching existed, a real
    report showed CAT, HEARTH, LAMP, SHELF, and FOREST all sharing an
    identical "danger" hit from ONE entry that was actually only ever
    talking about the forest being dangerous after dark -- the excerpt is
    what made that checkable at a glance (`--lineage-report` is a
    developer-facing microscope, not a black box to be trusted
    uncritically), and sentence-scoping is what stopped it happening at
    all."""
    for entity, concept, excerpt in extract_associations(text):
        memory["entities"].setdefault(entity, {}).setdefault(
            concept, []).append({"index": index, "text": excerpt})


def rebuild(entries):
    """A fresh Lineage Memory built from scratch by replaying every journal
    entry in order -- the doc's own escape hatch: extraction logic can
    improve later without making earlier processing irreversible, since
    the journal itself (the real source of truth) is untouched by any of
    this and can always be replayed again."""
    memory = new_memory()
    for i, text in enumerate(entries):
        record_entry(memory, i, text)
    memory["processed_through"] = len(entries)
    return memory


def format_report(memory):
    """The developer-facing surface -- the one place a human is meant to
    actually read this data (`--lineage-report`); never read by the game
    itself. Entities are ordered by how many entries reference them at
    all (most-referenced first, on the theory that's the most likely
    place a real pattern is emerging), concepts within an entity the same
    way. Omits any entity with zero associations entirely, rather than
    padding the report with "0 entries" noise.

    Every association prints its own excerpts, not just a count or a day
    range -- shown in full, not truncated, since the entire point is
    catching a false positive (a cross-product association from an entry
    that was actually about something else) by eye. No excerpt means no
    way to tell a real pattern from an artifact of the extraction being
    coarse (see record_entry's own docstring for the real example that
    made this necessary)."""
    entities = memory["entities"]
    rows = []
    for entity, concepts in entities.items():
        total = len({r["index"] for recs in concepts.values() for r in recs})
        if total:
            rows.append((total, entity, concepts))
    if not rows:
        return "LINEAGE MEMORY\n\nNo patterns yet -- nothing in the journal matched a candidate entity and concept together."
    rows.sort(key=lambda r: (-r[0], r[1]))
    lines = [f"LINEAGE MEMORY -- {memory['processed_through']} journal entries processed", ""]
    for total, entity, concepts in rows:
        lines.append(f"{entity.upper()} -- {total} {'entry' if total == 1 else 'entries'}")
        for concept, recs in sorted(concepts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            n = len(recs)
            lines.append(f"  {concept}: {n} {'entry' if n == 1 else 'entries'}")
            for r in recs:
                lines.append(f"    {r['text']}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def save(memory, path=None):
    path = path or LINEAGE_MEMORY_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)


def load(path=None):
    path = path or LINEAGE_MEMORY_PATH
    if not os.path.exists(path):
        return new_memory()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sync_lineage_memory(world, path=None):
    """The incremental hook: catch Lineage Memory up on any journal entries
    written since it last looked, and persist the result. Takes a
    world-like object -- only .get("journal") and that entity's .attrs are
    touched, so this never has to import World itself. Safe to call after
    every save, in every driver (human play, the dumb agent, the LLM
    agent): a no-op whenever nothing new was written, and it never touches
    disk at all if there's no journal yet (a world that hasn't been built,
    or a duck-typed stand-in without one)."""
    journal = world.get("journal")
    if journal is None:
        return
    entries = journal.attrs.get("entries", [])
    memory = load(path)
    for i in range(memory["processed_through"], len(entries)):
        record_entry(memory, i, entries[i])
    memory["processed_through"] = len(entries)
    save(memory, path)
