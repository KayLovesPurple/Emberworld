"""
lineage_memory.py -- the Lineage Memory Observatory: what recurring
patterns are showing up in the shared journal, surfaced for the developer
via `--lineage-report`, never fed back into the game. See
docs/LINEAGE_MEMORY_OBSERVATORY.md for the full design and
docs/ARCHITECTURE.md's "Lineage Memory" section for what actually landed.

Rebuilt on demand (`--lineage-rebuild`), never automatically. An earlier
version ran a rule-based keyword extractor incrementally after every
session; that's gone now, replaced entirely by LLM-based extraction
(`llm_rebuild`) the developer triggers explicitly -- see ARCHITECTURE.md
for why both changes happened together (cost/latency landing on ordinary
play, and not wanting two parallel lineages to keep in sync).

Deliberately one-way and (mostly) self-contained: this module still
imports nothing from world.py/content.py/drivers.py -- `llm_rebuild`
takes a plain list of journal entry strings, so the CLI layer owns
loading the world and the game never has to know this module exists.
`anthropic` itself is lazily imported inside `llm_rebuild`, so nothing
else here needs it installed.
"""

import json
import os
import re

LINEAGE_MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "lineage_memory.json")

# Cheap and fast is enough here -- this is structured extraction, not
# creative writing, and it runs only when the developer explicitly asks.
LLM_MODEL = "claude-haiku-4-5-20251001"

# Only ever tag evidence to one of these -- keeps the tracked-entity list
# small and deliberate rather than letting the LLM invent arbitrary nouns
# (docs/LINEAGE_MEMORY_OBSERVATORY.md section 13's own caution).
KNOWN_ENTITIES = ("well", "cairn", "forest", "hearth", "lamp", "shelf", "statue", "cat")

EVIDENCE_TYPES = ("behaviour", "interpretation", "association", "observation")

# Entries per API call. A balance: small enough that one batch's prompt
# stays easy for the model to attend to fully, large enough that a full
# rebuild over a real lineage (dozens of entries) doesn't need dozens of
# round trips.
BATCH_SIZE = 12

# Evidence below this confidence still gets kept (never silently dropped
# -- "prefer false negatives over confidently inventing meaning" cuts the
# other way too: don't invent CERTAINTY either), but the report groups it
# under "WEAK / DERIVED" instead of its named evidence type, so a
# developer reading it isn't given more confidence in a pattern than the
# extractor itself has.
CONFIDENCE_WEAK_BELOW = 0.5

_STAMP_RE = re.compile(r"^\[Day (\d+)(?:, ([^\]]+))?\]\s*")


def _parse_stamp(entry_text):
    """(day, hand_name_or_None) from an entry's own stamp
    (content_common.py's day_stamp: "[Day N]" or "[Day N, Name]")."""
    m = _STAMP_RE.match(entry_text)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


_EXTRACTION_TOOL = {
    "name": "record_evidence",
    "description": ("Record structured evidence extracted from a persistent "
                     "text-adventure game's shared journal."),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entry_index": {
                            "type": "integer",
                            "description": "The [N] index of the entry this evidence came from.",
                        },
                        "entity": {
                            "type": "string",
                            "enum": list(KNOWN_ENTITIES),
                        },
                        "evidence_type": {
                            "type": "string",
                            "enum": list(EVIDENCE_TYPES),
                            "description": (
                                "observation: a plain, literal, factual description. "
                                "interpretation: something inferred, believed, or "
                                "attributed -- especially treating an inanimate thing "
                                "as if it perceives, remembers, or intends. "
                                "behaviour: something the hand actually DID, not said. "
                                "association: a recurring conceptual link (a feeling, "
                                "an object, a symbolic act) that isn't cleanly an "
                                "observation or interpretation."
                            ),
                        },
                        "concept": {
                            "type": "string",
                            "description": ("A short, lowercase, snake_case label: "
                                             "mystery, comfort, watchful, stone_added, "
                                             "good_omen, etc."),
                        },
                        "excerpt": {
                            "type": "string",
                            "description": "The specific phrase this came from, not the whole entry.",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0 to 1: how sure you are this is really evidence of the stated type.",
                        },
                    },
                    "required": ["entry_index", "entity", "evidence_type",
                                 "concept", "excerpt", "confidence"],
                },
            },
        },
        "required": ["items"],
    },
}

_SYSTEM_PROMPT = f"""You extract structured evidence from a text-adventure game's shared journal, for a developer tool that observes recurring patterns in how independent hands describe and interact with the world. It never changes the game or is shown to any hand.

Known entities -- only ever tag evidence to one of these, and only when an entry genuinely refers to it: {", ".join(KNOWN_ENTITIES)}.

For each journal entry, extract zero or more evidence items using the record_evidence tool. Be conservative: most entries have zero, one, or two pieces of evidence, not many. Prefer skipping a stretch over confidently inventing meaning -- reflect real uncertainty in the confidence score rather than omitting a genuine but weak signal. Do not extract anything about potatoes, weather, or other routine chores unless it specifically characterizes one of the known entities."""


def new_memory():
    """An empty Lineage Memory."""
    return {"entry_count": 0, "entities": {}}


def _entity_record():
    return {t: {} for t in EVIDENCE_TYPES}


def _record_item(memory, entity, evidence_type, concept, item):
    rec = memory["entities"].setdefault(entity, _entity_record())
    rec[evidence_type].setdefault(concept, []).append(item)


def _call_llm(client, model, batch, offset):
    """One API call for one batch of (already-offset) journal entries.
    Returns the raw list of evidence-item dicts the model produced, `[]`
    on anything unexpected rather than raising -- one bad or empty batch
    should not sink an entire rebuild."""
    listing = "\n".join(f"[{offset + i}] {text}" for i, text in enumerate(batch))
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_evidence"},
        messages=[{"role": "user", "content": f"Journal entries:\n\n{listing}"}],
    )
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_evidence":
            return block.input.get("items", [])
    return []


def llm_rebuild(entries, client=None, model=LLM_MODEL):
    """Rebuild Lineage Memory from scratch using an LLM for extraction --
    manually triggered (`--lineage-rebuild`) only, never incremental and
    never automatic. `entries` is the plain list of journal entry strings
    (day/hand-stamped, as content_common.py's day_stamp already produces);
    the day and hand name are parsed locally, not trusted to the model,
    since that's exact, free information already sitting in the text.

    `client` is injectable for testing (a fake client, same pattern
    test_drivers.py's LLM sign-off tests already use) -- when omitted,
    lazily imports the real anthropic package so nothing else in this
    module needs it installed. A batch that raises (network error, bad
    response) is skipped rather than aborting the whole rebuild -- a
    partial result developers can see and re-run is better than losing
    everything to one bad batch."""
    if client is None:
        from anthropic import Anthropic
        client = Anthropic()
    memory = new_memory()
    for offset in range(0, len(entries), BATCH_SIZE):
        batch = entries[offset:offset + BATCH_SIZE]
        try:
            items = _call_llm(client, model, batch, offset)
        except Exception:
            continue
        for item in items:
            idx = item.get("entry_index")
            if idx is None or not (0 <= idx < len(entries)):
                continue
            day, hand = _parse_stamp(entries[idx])
            evidence = {"index": idx, "day": day, "hand": hand,
                        "text": item.get("excerpt", ""),
                        "confidence": item.get("confidence", 0.0)}
            _record_item(memory, item["entity"], item["evidence_type"],
                         item["concept"], evidence)
    memory["entry_count"] = len(entries)
    return memory


def _report_line(item):
    day = f"Day {item['day']}" if item["day"] is not None else "day unknown"
    return f"    {day}: {item['text']}"


def _report_group(lines, heading, group):
    """One EVIDENCE_TYPE heading (e.g. "BEHAVIOUR") and its concepts,
    confident items only -- weak ones are collected separately and shown
    under their own "WEAK / DERIVED" heading instead, see format_report."""
    strong = {c: [i for i in items if i["confidence"] >= CONFIDENCE_WEAK_BELOW]
              for c, items in group.items()}
    strong = {c: items for c, items in strong.items() if items}
    if not strong:
        return
    lines.append(heading)
    for concept, items in sorted(strong.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"  {concept}")
        for item in sorted(items, key=lambda i: i["index"]):
            lines.append(_report_line(item))
    lines.append("")


def format_report(memory):
    """The developer-facing surface (`--lineage-report`) -- never read by
    the game itself. Entities ordered by how many distinct entries
    reference them at all; within an entity, BEHAVIOUR leads (the doc's
    own framing: it "may be stronger evidence... even if the journal
    language is sparse"), then INTERPRETATION, ASSOCIATION, OBSERVATION,
    with anything below CONFIDENCE_WEAK_BELOW pulled out into its own
    "WEAK / DERIVED" section regardless of type, rather than reported
    with the same weight as a confident hit."""
    entities = memory["entities"]
    rows = []
    for entity, rec in entities.items():
        indices = {i["index"] for t in EVIDENCE_TYPES for items in rec[t].values() for i in items}
        if indices:
            rows.append((len(indices), entity, rec))
    if not rows:
        return ("LINEAGE MEMORY\n\nNo patterns yet -- run --lineage-rebuild "
                 "to extract from the journal.")
    rows.sort(key=lambda r: (-r[0], r[1]))
    lines = [f"LINEAGE MEMORY -- {memory['entry_count']} journal entries", ""]
    for total, entity, rec in rows:
        lines.append(f"{entity.upper()} -- {total} {'entry' if total == 1 else 'entries'}")
        lines.append("")
        weak = {}
        for t in EVIDENCE_TYPES:
            _report_group(lines, t.upper(), rec[t])
            for concept, items in rec[t].items():
                soft = [i for i in items if i["confidence"] < CONFIDENCE_WEAK_BELOW]
                if soft:
                    weak.setdefault(concept, []).extend(soft)
        if weak:
            lines.append("WEAK / DERIVED")
            for concept, items in sorted(weak.items(), key=lambda kv: (-len(kv[1]), kv[0])):
                lines.append(f"  {concept}")
                for item in sorted(items, key=lambda i: i["index"]):
                    lines.append(_report_line(item))
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
