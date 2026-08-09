"""
test_lineage_memory.py -- tests for the Lineage Memory Observatory:
LLM-based extraction from the shared journal, triggered manually
(`--lineage-rebuild`), surfaced to the developer via `--lineage-report`.
See docs/LINEAGE_MEMORY_OBSERVATORY.md for the full design, and
docs/ARCHITECTURE.md's "Lineage Memory" section for the landed shape and
its history (an earlier rule-based, automatically-syncing version existed
and was fully replaced -- see ARCHITECTURE.md for why).

No real network calls: llm_rebuild takes an injectable `client`, and
every test here supplies a fake one, the same pattern test_drivers.py's
LLM sign-off tests already use.

Run it either way:
    python3 -m pytest test_lineage_memory.py -v      # if you have pytest
    python3 test_lineage_memory.py                    # if you don't
"""

import json
import os
import tempfile

from lineage_memory import (
    KNOWN_ENTITIES, ENTITY_HINTS, EVIDENCE_TYPES, CONFIDENCE_WEAK_BELOW,
    new_memory, llm_rebuild, format_report,
    save, load, _parse_stamp, _SYSTEM_PROMPT,
)


# ===========================================================================
# 1. CONSTANTS -- hand-authored, not derived (same discipline as
#    content.py's FOUND_ITEMS): a small, deliberate, closed entity list so
#    the LLM can't invent arbitrary nouns to track
#    (docs/LINEAGE_MEMORY_OBSERVATORY.md section 13's own caution).
# ===========================================================================
def test_known_entities_are_lowercase_and_unique():
    assert len(KNOWN_ENTITIES) == len(set(KNOWN_ENTITIES))
    for e in KNOWN_ENTITIES:
        assert e == e.lower()


def test_evidence_types_are_the_four_the_doc_asks_for():
    assert set(EVIDENCE_TYPES) == {"observation", "interpretation", "behaviour", "association"}


def test_every_known_entity_has_exactly_one_disambiguating_hint():
    """BUG WE HIT, found in real use: a stone left "on the flat ground at
    the forest's edge" (the cairn) got tagged to "patch" instead -- bare
    entity names carried no disambiguation, and "patch" is ordinary
    English for any patch of ground, not obviously the yard's vegetable
    patch specifically. Every entity now needs a hint, and no orphaned
    hint should exist for an entity that's been removed."""
    assert set(ENTITY_HINTS) == set(KNOWN_ENTITIES)
    for e in KNOWN_ENTITIES:
        assert ENTITY_HINTS[e].strip(), f"empty hint for {e!r}"


def test_system_prompt_carries_every_entity_hint():
    for e in KNOWN_ENTITIES:
        assert ENTITY_HINTS[e] in _SYSTEM_PROMPT, \
            f"hint for {e!r} not reaching the model"


def test_patch_hint_specifically_rules_out_ground_elsewhere():
    """The exact confusion from real use: ground/a stone at the forest's
    edge is the cairn's territory, not the vegetable patch's."""
    assert "vegetable patch" in ENTITY_HINTS["patch"]
    assert "not" in ENTITY_HINTS["patch"]


# ===========================================================================
# 2. STAMP PARSING -- entries are already stamped by day_stamp
#    (content_common.py): "[Day N]" or "[Day N, Name]". Parsed locally
#    rather than trusted to the model, since it's exact, free information
#    already sitting in the text.
# ===========================================================================
def test_parse_stamp_reads_a_plain_stamp():
    assert _parse_stamp("[Day 6] Planted a potato.") == (6, None)


def test_parse_stamp_reads_a_named_stamp():
    assert _parse_stamp("[Day 14, Marrow] Fed the cat.") == (14, "Marrow")


def test_parse_stamp_returns_none_for_unstamped_text():
    assert _parse_stamp("no stamp here") == (None, None)


# ===========================================================================
# 3. LLM_REBUILD -- fakes an Anthropic client so no network/key is needed.
#    Mirrors test_drivers.py's _FakeClient/_SequencedClient pattern for
#    the LLM sign-off tests: content is a list of blocks, here a single
#    forced tool_use block per call (tool_choice forces exactly this
#    shape in the real API too).
# ===========================================================================
class _FakeToolBlock:
    def __init__(self, items):
        self.type = "tool_use"
        self.name = "record_evidence"
        self.input = {"items": items}


class _FakeToolMsg:
    def __init__(self, items):
        self.content = [_FakeToolBlock(items)]


class _FakeExtractionClient:
    """Returns `responses` in order, one per batch call. `calls` records
    every kwargs dict passed to .create, so a test can inspect exactly
    what was sent (which entries, in which batch)."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        items = self.responses.pop(0) if self.responses else []
        return _FakeToolMsg(items)


def _item(entry_index, entity, evidence_type, concept, excerpt, confidence=0.9):
    return {"entry_index": entry_index, "entity": entity, "evidence_type": evidence_type,
            "concept": concept, "excerpt": excerpt, "confidence": confidence}


def test_llm_rebuild_records_evidence_from_the_tool_response():
    entries = ["[Day 21, Wick] Stacked one more stone on the cairn."]
    client = _FakeExtractionClient([[
        _item(0, "cairn", "behaviour", "stone_added",
              "Stacked one more stone on the cairn.", confidence=0.95),
    ]])
    memory = llm_rebuild(entries, client=client)
    rec = memory["entities"]["cairn"]["behaviour"]["stone_added"][0]
    assert rec["index"] == 0
    assert rec["day"] == 21
    assert rec["hand"] == "Wick"
    assert rec["text"] == "Stacked one more stone on the cairn."
    assert rec["confidence"] == 0.95
    assert memory["entry_count"] == 1


def test_llm_rebuild_batches_entries_and_makes_one_call_per_batch():
    from lineage_memory import BATCH_SIZE
    entries = [f"[Day {i}] Entry {i}." for i in range(BATCH_SIZE * 2 + 1)]
    client = _FakeExtractionClient([[], [], []])
    llm_rebuild(entries, client=client)
    assert len(client.calls) == 3, "should be one call per batch (12, 12, 1)"
    first_prompt = client.calls[0]["messages"][0]["content"]
    assert "[0]" in first_prompt and f"[{BATCH_SIZE - 1}]" in first_prompt
    assert f"[{BATCH_SIZE}]" not in first_prompt, "batch 1 must not leak into batch 0's prompt"


def test_llm_rebuild_reports_progress_once_per_batch_before_the_call():
    """A growing journal means a growing number of batches, and a silent
    multi-batch rebuild reads as hung rather than working -- on_batch must
    fire before each API call (not after), so a stuck or slow request still
    shows up as progress rather than silence."""
    from lineage_memory import BATCH_SIZE
    entries = [f"[Day {i}] Entry {i}." for i in range(BATCH_SIZE * 2 + 1)]
    client = _FakeExtractionClient([[], [], []])
    seen = []

    def on_batch(batch_num, total_batches):
        seen.append((batch_num, total_batches, len(client.calls)))

    llm_rebuild(entries, client=client, on_batch=on_batch)
    assert seen == [(1, 3, 0), (2, 3, 1), (3, 3, 2)], \
        "each on_batch call must land before that batch's own API call"


def test_llm_rebuild_never_calls_on_batch_for_an_empty_journal():
    calls = []
    llm_rebuild([], client=_FakeExtractionClient([]), on_batch=lambda *a: calls.append(a))
    assert calls == []


def test_llm_rebuild_works_without_an_on_batch_callback():
    """on_batch is optional -- every other test already relies on this,
    but pin it explicitly so it can't regress into a required arg."""
    entries = ["[Day 1] Fed the cat."]
    memory = llm_rebuild(entries, client=_FakeExtractionClient([[]]))
    assert memory["entry_count"] == 1


def test_llm_rebuild_skips_a_batch_that_raises_rather_than_aborting():
    class _Boom:
        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("no network")

    entries = ["[Day 1] Fed the cat."]
    memory = llm_rebuild(entries, client=_Boom())
    assert memory["entities"] == {}
    assert memory["entry_count"] == 1, "entry_count still reflects the real journal length"


def test_llm_rebuild_ignores_an_item_with_an_out_of_range_entry_index():
    """A hallucinated index must not crash the rebuild or corrupt data --
    dropped silently, same "prefer a gap over inventing" spirit as the
    rest of this module."""
    entries = ["[Day 1] Fed the cat."]
    client = _FakeExtractionClient([[
        _item(7, "cat", "association", "comfort", "Fed the cat."),
    ]])
    memory = llm_rebuild(entries, client=client)
    assert memory["entities"] == {}


def test_llm_rebuild_is_a_full_rebuild_not_incremental():
    """Two separate rebuilds from the same entries produce independent
    results -- there's no processed_through/resume state left over from
    the old incremental design."""
    entries = ["[Day 1] Fed the cat."]
    client = _FakeExtractionClient([[
        _item(0, "cat", "association", "comfort", "Fed the cat."),
    ]])
    first = llm_rebuild(entries, client=client)
    client2 = _FakeExtractionClient([[]])
    second = llm_rebuild(entries, client=client2)
    assert first["entities"] != {}
    assert second["entities"] == {}, "a fresh rebuild must not inherit the previous one's data"


# ===========================================================================
# 4. REPORT -- the developer-facing surface (`--lineage-report`). Never
#    read by the game itself.
# ===========================================================================
def test_report_on_an_empty_memory_says_so_plainly():
    assert "no patterns" in format_report(new_memory()).lower()


def test_report_shows_entity_count_and_excerpt_with_day():
    memory = llm_rebuild(
        ["[Day 21, Wick] Stacked one more stone on the cairn."],
        client=_FakeExtractionClient([[
            _item(0, "cairn", "behaviour", "stone_added",
                  "Stacked one more stone on the cairn."),
        ]]))
    report = format_report(memory)
    assert "CAIRN -- 1 entry" in report
    assert "BEHAVIOUR" in report
    assert "stone_added" in report
    assert "Day 21: Stacked one more stone on the cairn." in report


def test_report_orders_entities_by_distinct_entry_count_descending():
    """All three entries fit in one batch (well under BATCH_SIZE), so the
    fake client needs exactly one queued response covering all of them --
    one call per BATCH, not one per entry."""
    entries = ["[Day 1] The well.", "[Day 2] The cairn.", "[Day 3] The cairn again."]
    client = _FakeExtractionClient([[
        _item(0, "well", "association", "mystery", "The well."),
        _item(1, "cairn", "association", "beauty", "The cairn."),
        _item(2, "cairn", "association", "beauty", "The cairn again."),
    ]])
    memory = llm_rebuild(entries, client=client)
    report = format_report(memory)
    assert report.index("CAIRN") < report.index("WELL")


def test_report_groups_by_evidence_type_with_behaviour_first():
    memory = llm_rebuild(
        ["[Day 1] one.", "[Day 2] two."],
        client=_FakeExtractionClient([[
            _item(0, "cairn", "association", "memory", "one."),
            _item(1, "cairn", "behaviour", "stone_added", "two."),
        ]]))
    report = format_report(memory)
    assert report.index("BEHAVIOUR") < report.index("ASSOCIATION")


def test_report_moves_low_confidence_evidence_to_weak_and_derived():
    memory = llm_rebuild(
        ["[Day 22] marked the trail past the cairn."],
        client=_FakeExtractionClient([[
            _item(0, "cairn", "association", "mystery",
                  "marked the trail past the cairn", confidence=0.3),
        ]]))
    report = format_report(memory)
    assert "WEAK / DERIVED" in report
    assert "mystery" in report
    # the weak item must not ALSO appear under its named heading
    lines = report.splitlines()
    assoc_idx = lines.index("ASSOCIATION") if "ASSOCIATION" in lines else None
    assert assoc_idx is None, "a purely-weak concept shouldn't leave an empty ASSOCIATION heading"


def test_report_keeps_a_confident_and_a_weak_item_in_separate_sections():
    memory = llm_rebuild(
        ["[Day 1] a.", "[Day 2] b."],
        client=_FakeExtractionClient([[
            _item(0, "well", "association", "comfort", "a.", confidence=0.9),
            _item(1, "well", "association", "mystery", "b.", confidence=0.2),
        ]]))
    report = format_report(memory)
    assert "ASSOCIATION" in report
    assert "comfort" in report
    assert "WEAK / DERIVED" in report
    assert "mystery" in report


# ===========================================================================
# 5. PERSISTENCE -- a separate file from emberworld_save.json, gitignored:
#    derived, regenerable (llm_rebuild always starts fresh), and specific
#    to one local lineage's actual play history.
# ===========================================================================
def test_save_and_load_roundtrip():
    memory = llm_rebuild(
        ["[Day 1] Fed the cat."],
        client=_FakeExtractionClient([[
            _item(0, "cat", "association", "comfort", "Fed the cat."),
        ]]))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        save(memory, path)
        assert load(path) == memory


def test_load_returns_a_fresh_memory_when_no_file_exists_yet():
    with tempfile.TemporaryDirectory() as d:
        assert load(os.path.join(d, "does_not_exist.json")) == new_memory()


def test_saved_file_is_plain_readable_json():
    memory = llm_rebuild(
        ["[Day 1] Fed the cat."],
        client=_FakeExtractionClient([[
            _item(0, "cat", "association", "comfort", "Fed the cat."),
        ]]))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        save(memory, path)
        with open(path) as f:
            assert json.load(f) == memory


# ---------------------------------------------------------------------------
# Built-in runner, so you don't need pytest installed.
# ---------------------------------------------------------------------------
def _main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
