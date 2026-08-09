"""
test_lineage_memory.py -- tests for the Lineage Memory Observatory (v1,
rule-based): what recurring patterns are showing up in the shared journal,
surfaced for the developer, never fed back into the game. See
docs/LINEAGE_MEMORY_OBSERVATORY.md for the full design, and
docs/ARCHITECTURE.md's "Lineage Memory" section for the landed shape.

Run it either way:
    python3 -m pytest test_lineage_memory.py -v      # if you have pytest
    python3 test_lineage_memory.py                    # if you don't
"""

import json
import os
import tempfile

from lineage_memory import (
    CANDIDATE_ENTITIES, CANDIDATE_CONCEPTS,
    find_entities, find_concepts, extract_associations,
    new_memory, record_entry, rebuild,
    save, load, sync_lineage_memory, format_report,
)


# ===========================================================================
# 1. THE WORD TABLES -- hand-authored, not derived (same discipline as
#    FOUND_ITEMS): guard the data itself before anything reads it.
# ===========================================================================
def test_entity_and_concept_tables_are_well_formed():
    for table in (CANDIDATE_ENTITIES, CANDIDATE_CONCEPTS):
        for key, words in table.items():
            assert key == key.lower(), f"{key!r} should be lowercase"
            assert words, f"{key!r} has no trigger words"
            for w in words:
                assert w == w.lower(), f"{w!r} (under {key!r}) should be lowercase"
                assert w.strip() == w, f"{w!r} (under {key!r}) has stray whitespace"


def test_no_trigger_word_is_reused_across_different_entities():
    """Two entities sharing a trigger word would make a mention ambiguous
    between them -- each word should point at exactly one entity."""
    seen = {}
    for key, words in CANDIDATE_ENTITIES.items():
        for w in words:
            assert w not in seen, f"{w!r} claimed by both {seen.get(w)!r} and {key!r}"
            seen[w] = key


def test_no_trigger_word_is_reused_across_different_concepts():
    seen = {}
    for key, words in CANDIDATE_CONCEPTS.items():
        for w in words:
            assert w not in seen, f"{w!r} claimed by both {seen.get(w)!r} and {key!r}"
            seen[w] = key


# ===========================================================================
# 2. EXTRACTION -- pure functions over one entry's text. Word-boundary
#    matching throughout (never a bare substring check): "cat" must not
#    fire on "cattle", and a plural/inflected form only counts if it's
#    explicitly in the table (no stemming -- same "hand-authored, not
#    guessed" discipline as _plural_of).
# ===========================================================================
def test_find_entities_matches_a_known_word():
    assert find_entities("The cairn is taller than I remember.") == {"cairn"}


def test_find_entities_is_case_insensitive():
    assert find_entities("THE WELL is deep.") == {"well"}


def test_find_entities_respects_word_boundaries():
    assert find_entities("The cattle wandered off.") == set()
    assert find_entities("Ember stretched by the hearthside.") == set(), \
        "\"hearthside\" contains \"hearth\" but isn't the word \"hearth\""


def test_find_entities_can_return_several():
    result = find_entities("Fed the cat, then admired the statue by the forest.")
    assert result == {"cat", "statue", "forest"}


def test_find_concepts_matches_a_known_word():
    assert find_concepts("The well felt mysterious tonight.") == {"mystery"}


def test_find_concepts_returns_empty_for_plain_text():
    assert find_concepts("Planted a potato and fed the cat.") == set()


def test_extract_associations_is_the_cross_product_within_one_sentence():
    """Matching is scoped to a single SENTENCE, not the whole entry --
    narrower than v1's original same-entry granularity. Two entities in
    one sentence still cross-product against a shared concept."""
    triples = extract_associations("The well and the cairn both felt mysterious.")
    pairs = {(e, c) for e, c, _ in triples}
    assert pairs == {("well", "mystery"), ("cairn", "mystery")}


def test_extract_associations_does_not_cross_sentence_boundaries():
    """BUG WE HIT (real observed output): one entry mentioning both the cat
    and, in a LATER sentence, "the forest is dangerous after dark" cross-
    producted into (cat, danger) under the old same-entry-wide matching,
    even though the danger was only ever about the forest. Splitting by
    sentence before matching fixes this at the source, rather than just
    making the false positive auditable after the fact."""
    triples = extract_associations(
        "Ember the cat needs feeding. The forest is dangerous after dark.")
    pairs = {(e, c) for e, c, _ in triples}
    assert ("cat", "danger") not in pairs
    assert ("forest", "danger") in pairs


def test_extract_associations_excerpt_is_the_matching_sentence_not_the_whole_entry():
    triples = extract_associations(
        "Fed the cat and lit the lamp. The well felt mysterious tonight.")
    excerpt = next(x for e, c, x in triples if (e, c) == ("well", "mystery"))
    assert excerpt == "The well felt mysterious tonight."
    assert "cat" not in excerpt and "lamp" not in excerpt


def test_extract_associations_reattaches_the_entrys_stamp_to_every_sentence():
    """A later sentence in a multi-sentence entry doesn't carry its own
    [Day N, Name] stamp -- reattached to each sentence's excerpt so a
    report reader still sees when/who it's from, the same as when the
    whole entry was the excerpt."""
    triples = extract_associations(
        "[Day 18, Moss] Ember the cat needs feeding. "
        "The forest is dangerous after dark.")
    excerpt = next(x for e, c, x in triples if (e, c) == ("forest", "danger"))
    assert excerpt == "[Day 18, Moss] The forest is dangerous after dark."


def test_extract_associations_is_empty_when_nothing_matches():
    assert extract_associations("Just a quiet day, nothing much to report.") == []


def test_extract_associations_never_duplicates_a_pair_across_two_sentences():
    """The same pair showing up in two different sentences of one entry
    ("The well felt mysterious" / "the well remains mysterious") is still
    one piece of evidence, not two -- the unit of evidence is the entry,
    not the raw sentence or word count. The FIRST matching sentence wins
    as the representative excerpt."""
    triples = extract_associations(
        "The well felt mysterious tonight. The well remains mysterious.")
    assert len(triples) == 1
    entity, concept, excerpt = triples[0]
    assert (entity, concept) == ("well", "mystery")
    assert excerpt == "The well felt mysterious tonight."


# ===========================================================================
# 3. RECORDING -- the unit of evidence is the journal ENTRY (its own list
#    index), not a derived "visit" grouping. Two hands sharing a name on
#    the same day (a real, observed occurrence) must not silently merge --
#    see docs/LINEAGE_MEMORY_OBSERVATORY.md's Status note. Each association
#    keeps the entry's own text alongside its index, not just a day range:
#    a real report showed CAT and HEARTH and FOREST all sharing an
#    identical "danger" hit from one entry that was actually only about
#    the forest -- a bare day number can't tell you that, the excerpt can.
# ===========================================================================
def test_recording_one_entry_populates_its_associations_with_the_excerpt():
    memory = new_memory()
    record_entry(memory, 0, "[Day 6, Marrow] The well felt mysterious tonight.")
    rec = memory["entities"]["well"]["mystery"]
    assert rec == [{"index": 0, "text": "[Day 6, Marrow] The well felt mysterious tonight."}]


def test_recording_two_entries_appends_both_excerpts_in_order():
    memory = new_memory()
    record_entry(memory, 0, "[Day 6, Marrow] The well felt mysterious tonight.")
    record_entry(memory, 5, "[Day 20, Wren] Still mysterious, that well.")
    rec = memory["entities"]["well"]["mystery"]
    assert [r["index"] for r in rec] == [0, 5]
    assert rec[1]["text"] == "[Day 20, Wren] Still mysterious, that well."


def test_recording_touches_nothing_for_an_entry_with_no_match():
    memory = new_memory()
    record_entry(memory, 0, "[Day 1] Planted a potato, fed the cat.")
    assert memory["entities"].get("cat", {}) == {} or "mystery" not in memory["entities"].get("cat", {})


def test_same_day_same_name_entries_are_recorded_as_separate_evidence():
    """The exact case that ruled out (day, name) as the unit of evidence:
    two different hands can share a name on the same day. Each entry still
    counts as its own piece of evidence."""
    memory = new_memory()
    record_entry(memory, 0, "[Day 6, Marrow] The well felt mysterious.")
    record_entry(memory, 1, "[Day 6, Marrow] The well still feels mysterious.")
    assert [r["index"] for r in memory["entities"]["well"]["mystery"]] == [0, 1]


def test_recording_does_not_cross_products_cat_and_danger_from_different_sentences():
    """The real case that prompted per-sentence matching: one entry
    mentioning both the cat and, in a separate sentence, "the forest is
    dangerous after dark" used to cross-product into (cat, danger) even
    though the danger was only ever about the forest. Recording now
    inherits extract_associations' sentence-scoped matching, so the false
    positive never reaches storage at all."""
    memory = new_memory()
    record_entry(memory, 0, "[Day 18] Ember the cat needs feeding. "
                            "The forest is dangerous after dark.")
    assert "danger" not in memory["entities"].get("cat", {})
    excerpt = memory["entities"]["forest"]["danger"][0]["text"]
    assert excerpt == "[Day 18] The forest is dangerous after dark."


def test_rebuild_processes_every_entry_from_scratch():
    entries = [
        "[Day 1, Wren] Fed the cat, planted a potato.",
        "[Day 6, Marrow] The well felt mysterious tonight.",
        "[Day 9, Marrow] The cairn is beautiful in the frost.",
    ]
    memory = rebuild(entries)
    assert [r["index"] for r in memory["entities"]["well"]["mystery"]] == [1]
    assert [r["index"] for r in memory["entities"]["cairn"]["beauty"]] == [2]
    assert memory["processed_through"] == len(entries)


def test_rebuild_and_incremental_recording_agree():
    entries = [
        "[Day 1, Wren] Fed the cat, planted a potato.",
        "[Day 6, Marrow] The well felt mysterious tonight.",
        "[Day 9, Marrow] The cairn is beautiful in the frost.",
    ]
    rebuilt = rebuild(entries)
    incremental = new_memory()
    for i, text in enumerate(entries):
        record_entry(incremental, i, text)
    incremental["processed_through"] = len(entries)
    assert rebuilt == incremental


# ===========================================================================
# 4. REPORT -- the developer-facing surface (`--lineage-report`). Never
#    read by the game itself; this is the one place a human is meant to
#    actually look at the data. No day-range summary (dropped: redundant
#    once every excerpt already carries its own stamp, and the day range
#    told you nothing about whether the match was actually accurate).
# ===========================================================================
def test_report_on_an_empty_memory_says_so_plainly():
    report = format_report(new_memory())
    assert "no patterns" in report.lower()


def test_report_lists_entities_with_their_entry_counts_and_excerpts():
    memory = rebuild([
        "[Day 6, Marrow] The well felt mysterious tonight.",
        "[Day 9, Wren] Still mysterious, that well.",
        "[Day 14, Wren] The well felt oddly comforting today.",
    ])
    report = format_report(memory)
    assert "WELL" in report
    assert "3 entries" in report
    assert "mystery: 2 entries" in report
    assert "comfort: 1 entry" in report
    assert "[Day 6, Marrow] The well felt mysterious tonight." in report
    assert "[Day 14, Wren] The well felt oddly comforting today." in report


def test_report_orders_entities_by_entry_count_descending():
    memory = rebuild([
        "[Day 1] The cairn is beautiful.",
        "[Day 2] The well is mysterious.",
        "[Day 3] Still mysterious, that well.",
    ])
    report = format_report(memory)
    assert report.index("WELL") < report.index("CAIRN")


def test_report_omits_entities_with_no_associations():
    memory = rebuild(["[Day 1] Fed the cat, planted a potato."])
    report = format_report(memory)
    assert "CAT" not in report.upper() or "0 entries" not in report


# ===========================================================================
# 5. PERSISTENCE -- a separate file from emberworld_save.json, gitignored:
#    derived, regenerable, and specific to one local lineage of play.
# ===========================================================================
def test_save_and_load_roundtrip():
    memory = new_memory()
    record_entry(memory, 0, "[Day 6, Marrow] The well felt mysterious tonight.")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        save(memory, path)
        loaded = load(path)
    assert loaded == memory


def test_load_returns_a_fresh_memory_when_no_file_exists_yet():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "does_not_exist.json")
        assert load(path) == new_memory()


def test_saved_file_is_plain_readable_json():
    memory = new_memory()
    record_entry(memory, 0, "[Day 6, Marrow] The well felt mysterious tonight.")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        save(memory, path)
        with open(path) as f:
            raw = json.load(f)
    assert raw == memory


# ===========================================================================
# 6. SYNC -- the incremental hook. Takes a world-like object (duck-typed:
#    only .get(id) and the journal entity's .attrs are touched) so
#    lineage_memory.py never has to import world.py/content.py -- the "no
#    arrow back into the game" design holds in both directions: the game
#    reaches out to sync it, it never reaches back into the game.
# ===========================================================================
class _FakeJournal:
    def __init__(self, entries):
        self.attrs = {"entries": entries}


class _FakeWorld:
    def __init__(self, entries=()):
        self._journal = _FakeJournal(list(entries))

    def get(self, id):
        return self._journal if id == "journal" else None


def test_sync_processes_new_entries_and_remembers_where_it_left_off():
    w = _FakeWorld(["[Day 6, Marrow] The well felt mysterious tonight."])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        sync_lineage_memory(w, path)
        memory = load(path)
        assert [r["index"] for r in memory["entities"]["well"]["mystery"]] == [0]
        assert memory["processed_through"] == 1

        w._journal.attrs["entries"].append("[Day 9, Wren] The cairn is beautiful.")
        sync_lineage_memory(w, path)
        memory = load(path)
        assert [r["index"] for r in memory["entities"]["cairn"]["beauty"]] == [1]
        assert [r["index"] for r in memory["entities"]["well"]["mystery"]] == [0], \
            "re-syncing must not reprocess (or double-count) an already-seen entry"
        assert memory["processed_through"] == 2


def test_sync_is_a_no_op_when_nothing_new_was_written():
    w = _FakeWorld(["[Day 6, Marrow] The well felt mysterious tonight."])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        sync_lineage_memory(w, path)
        once = load(path)
        sync_lineage_memory(w, path)
        assert load(path) == once


def test_sync_handles_a_world_with_no_journal_gracefully():
    class _EmptyWorld:
        def get(self, id):
            return None
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "lineage_memory.json")
        sync_lineage_memory(_EmptyWorld(), path)   # must not raise
        assert not os.path.exists(path)


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
