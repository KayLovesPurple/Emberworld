# Lineage Memory / Culture Observatory

## Status

Built and LLM-backed — see docs/ARCHITECTURE.md's "Lineage Memory"
section for the full landed shape, its history, and what's still
deliberately not built. The short version of how it got here: a
rule-based keyword-matching v1 shipped first (explicitly as a placeholder
to get storage/reporting working end to end), was extended once with a
first slice of the "V1.5" addendum below (behaviour tracking), and was
then replaced outright once real reports kept running into exactly what
this doc always said a keyword table couldn't do — telling an
observation from an interpretation (section 7), and any concept outside
a fixed hand-authored list (`good_omen` was never in one). Extraction is
now a real LLM call (`llm_rebuild`, cheap/fast model, structured
tool-use output), producing all four evidence types this doc's "V1.5"
section asks for: observation, interpretation, behaviour, association,
each with a real confidence score.

**Two design decisions changed at the same time as the extraction
engine, both about *when* this runs, not what it produces.** First: the
doc's "visit" as the unit of evidence (section 4) became the journal
entry itself rather than a derived grouping — (day, hand name) was
considered and rejected as the grouping key, since two different hands
landing on the same name on the same day is a real, observed occurrence
in this lineage, and merging them would silently conflate distinct
evidence. Second, and larger: this is no longer incremental or automatic.
The original design (and an earlier version of this codebase) synced
after every session, automatically, keyword-matching for free. Making
extraction real LLM calls made that the wrong shape — the cost and
latency would land on ordinary play, not just deliberate developer use —
so `--lineage-rebuild` is now a manually-triggered, full rebuild from the
whole journal, and there's exactly one `lineage_memory.json`, never a
second file running in parallel that could drift out of sync with it.

## Purpose

Emberworld's journal is becoming an unexpectedly valuable record of what independent hands notice, care about, wonder about, and choose to do.

The journal remains an open-ended historical record.

This system exists to **observe that record**, not to steer it.

> **Lineage Memory is a microscope, not a steering wheel.**

It detects recurring patterns in the journal and presents them to the developer. It does not feed those patterns back into agents, world state, prompts, descriptions, or available actions.

## 1. Design principles

### Preserve agent independence

The most valuable property of the current journal is that entries largely arise from independent decisions. Agents may have access to some previous journal entries, so natural cultural transmission already exists.

The observatory must never become a hidden social-conditioning system.

### Observation, not intervention

The system may answer:

> What patterns are appearing?

It must not answer:

> What should agents believe next?

It must never automatically:
- add beliefs to agent context
- alter prompts
- alter NPC/world descriptions
- rename objects
- create quests or mysteries
- change mechanics
- modify world state
- reward or suppress an interpretation

### Canon remains authored

If agents repeatedly describe the well as mysterious, the system records that. It does not make the well mysterious.

If agents repeatedly describe the forest as dangerous, the system records that. It does not make the forest dangerous.

The peaceful, gentle character of Emberworld remains under deliberate authorial control.

### The journal remains the historical source of truth

The journal is permanent. Lineage Memory is derived data.

If Lineage Memory is deleted or rebuilt, the journal remains untouched.

## 2. Architecture

The system is intentionally one-way:

    AGENT VISIT
         |
         v
    WORLD STATE
         |
         v
    JOURNAL ENTRY
         |
         v
    LINEAGE MEMORY
         |
         v
    DEVELOPER OBSERVATORY

There is deliberately **no arrow back** from Lineage Memory into the game.

## 3. What Lineage Memory records

Track recurring patterns such as:
- references to places and objects
- recurring descriptions and associations
- recurring actions and behaviours
- interpretations
- names and naming patterns
- symbolic acts
- emotional language
- recurring routes or locations
- changes in frequency over time
- disagreement and competing interpretations

Example:

    WELL
      mentions: 11
      "mysterious": 4
      "watching": 3
      "quiet": 3
      "water": 5

These are observations about the lineage, not properties of the well.

## 4. Unit of evidence

Use the **visit/hand**, not the displayed agent name, as the basic unit of cultural evidence.

Names may duplicate across sessions.

If one visit says:
- "The well watches."
- "The well is strange."
- "The well keeps secrets."

that is one visit expressing several related observations, not three independent confirmations.

If three separate visits express similar ideas, that is three independent pieces of evidence.

## 5. Incremental processing

Process each new journal entry once:

    new journal entry
          |
          v
    extract observations
          |
          v
    update Lineage Memory
          |
          v
    store derived state

The full journal should not be re-read during normal operation.

Also support a complete rebuild:

    full journal
          |
          v
    current extraction logic
          |
          v
    reconstructed Lineage Memory

This allows the analysis to improve without making historical extraction irreversible.

## 6. Observation types

Use a small vocabulary.

### Entity reference

An entry refers to a known world entity.

### Association

An entity is associated with a concept.

Example:

> "The well felt watchful."

### Behaviour

An agent performs an action involving an entity.

Example:

> "I left another stone at the cairn."

### Interpretation

An agent explicitly interprets something.

Example:

> "I think the well is keeping something from us."

Interpretations remain distinct from objective observations.

### Naming

An agent uses a particular name or phrase for an entity.

Repeated naming does not automatically change the canonical world name.

### Symbolic act

An action appears to have symbolic or social meaning.

Example:

> "I left the blue glass pebble there as a good omen."

## 7. Observation versus interpretation

Keep these separate.

> "The well was dry."

is an observation.

> "The well was watching me."

is an interpretation.

Never flatten the latter into:

    well.is_watchful = true

Instead record:

    observation:
      well -> dry

    interpretation:
      well -> watchful

This distinction protects the difference between what happened and what someone thought it meant.

## 8. Repetition and frequency

For each entity/concept combination, store at least:
- total mentions
- distinct visits containing the observation
- first observed day
- most recent day
- recent frequency
- historical frequency

Example:

    well / watchful
      mentions: 5
      visits: 5
      first_seen: 6
      last_seen: 30

## 9. Preserve disagreement

Do not reduce an entity to one "belief."

For example:

    WELL
      watchful: 5 visits
      peaceful: 3 visits
      useful: 6 visits
      mysterious: 4 visits
      ordinary: 2 visits

The important result is the shape of the interpretations.

Contradiction is data.

## 10. Reporting thresholds

Thresholds may be used to highlight patterns for the developer.

For example:
- emerging: >= 3 visits
- strong: >= 5 visits

But thresholds must never trigger gameplay changes.

Crossing a threshold means:

> highlight this for the developer

not:

> change the world.

## 11. Behaviour versus language

Track both.

For example:

    cairn
      stones_added: 9
      visits: 14
      explicit_mentions_of_memory: 2

This may indicate behavioural significance even if the journal language is sparse.

Conversely:

    well
      ominous_language: 5
      unusual_interactions: 0

would indicate narrative interpretation rather than a behavioural tradition.

## 12. Temporal patterns

Track changes over time, not just lifetime totals.

For example:

    Days 1-10
      well: mostly "water"

    Days 11-20
      well: increasing "mystery"

    Days 21-32
      well: "watching", "secrets", "unknowable"

Temporal change may be more revealing than aggregate frequency.

## 13. Candidate entities

Initially focus on known persistent entities, such as:
- well
- cairn
- forest
- hearth
- lamp
- curio shelf
- statue
- cat
- recurring paths/locations

New candidate entities may be surfaced, but automatic creation should be conservative. Do not let arbitrary nouns become thousands of tracked entities.

## 14. Candidate concepts

Start with broad categories:
- emotional qualities
- sensory qualities
- social meanings
- perceived agency
- mystery
- beauty
- comfort
- danger
- usefulness
- ritual
- memory
- luck
- affection
- curiosity

The purpose is to surface patterns, not perfectly classify every sentence.

## 15. Tone monitoring

Because Emberworld is intended to remain gentle and peaceful, the observatory may report tonal distributions.

Example:

    WELL
      gentle / neutral associations: 11
      ominous associations: 5
      practical associations: 7

If ominous language increases, the observatory reports it.

It does not:
- remove ominous interpretations
- insert positive entries
- alter prompts
- make the well objectively ominous
- make the well objectively comforting

The developer decides whether intervention is appropriate.

## 16. Developer-facing report

A periodic report can contain:

### New patterns
Things appearing for the first time or crossing a reporting threshold.

### Growing patterns
Patterns increasing in frequency.

### Persistent patterns
Patterns recurring over a long period.

### Contradictions
Entities with competing interpretations.

### Behavioural customs
Repeated actions involving the same object/place.

### Notable anomalies
One-off observations that may deserve attention despite low frequency.

This is a developer tool, not a player-facing feature.

## 17. Example report

    LINEAGE MEMORY — DAY 32

    WELL
      11 visits referenced it.
      "watchful" appeared in 5 visits.
      "mysterious" appeared in 4.
      "useful" appeared in 6.
      Interpretations remain mixed.

    CAIRN
      14 visits referenced it.
      9 visits added stones.
      2 entries described it as remembering.
      Behavioural significance is stronger than explicit mythology.

    FOREST
      23 visits referenced it.
      "beautiful" appeared in 8.
      "peaceful" appeared in 6.
      "listening" appeared in 4.
      "dangerous" appeared in 2.
      Overall interpretation remains predominantly gentle/curious.

## 18. Provenance

Every derived pattern should be traceable to source journal entries.

Example:

    well / watchful
      visits: 5
      sources:
        Day 6
        Day 14
        Day 29
        ...

The developer should be able to inspect the evidence behind a reported pattern.

## 19. Confidence

Extraction is imperfect.

Where appropriate, derived observations should have an extraction confidence.

Prefer false negatives over confidently inventing meaning.

It is better to miss a subtle pattern than to manufacture a cultural trend that was never present.

## 20. LLM usage

An LLM may help extract structured observations from freeform journal text.

Good:

> Extract references to known entities and identify whether this entry contains an observation, interpretation, action, or association.

Bad:

> What does this entry mean for the culture of Emberworld?

The extraction step should be as literal and structured as practical.

## 21. Rebuildability

Support:

    rebuild_lineage_memory()

This:
1. reads all journal entries
2. processes them using the current extraction logic
3. reconstructs aggregate statistics
4. replaces the derived Lineage Memory dataset

The journal is never modified.

## 22. Explicit non-goals

Lineage Memory does not:
- change agent prompts
- change goals or personalities
- create quests
- create lore
- create mysteries
- rename entities
- modify live descriptions
- alter world state
- reward beliefs
- punish beliefs
- resolve contradictions
- decide canon
- steer emotional tone
- tell agents what the lineage believes

## 23. Central design principle

> **Do not turn emergence into a feedback loop before you understand the emergence.**

The current journal is interesting because its entries are largely the product of independent hands operating in a persistent world.

The observatory protects that property.

The intended pipeline is:

    independent agents
          ↓
    persistent world
          ↓
    journal
          ↓
    observation
          ↓
    developer understanding

Not:

    agents
      ↓
    journal
      ↓
    cultural model
      ↓
    altered prompts/world
      ↓
    agents
      ↓
    increasingly self-reinforcing culture

## 24. First implementation

Keep version 1 small.

Track only:
1. known entity references
2. recurring descriptive associations
3. repeated behaviours
4. distinct visits containing each pattern
5. first/last occurrence
6. broad tonal categories
7. source journal entries

Generate a periodic developer report.

Do not change the game.

Do not expose Lineage Memory to agents.

Do not create persistent cultural traits in world state.

Run it for a while and see what it reveals.

## 25. The experiment

The experiment is not:

> "Can we build a culture system?"

It is:

> **"What culture is already emerging when we deliberately do nothing to create one?"**

If the result is beautiful, the observatory has succeeded.

If it is repetitive, strange, unexpectedly dark, or surprisingly peaceful, that is useful too.

If nothing interesting emerges, that is also a valid result.

The system should make it easier to notice what the lineage is doing without making the lineage do anything differently.

## Final principle

> **Observe first. Intervene later, if ever.**

The journal is the world speaking for itself.

Lineage Memory is simply a better way for the developer to listen.


# Lineage Memory V1.5 — Evidence-Preserving Index

## Purpose

V1 already provides a useful semantic index:

    entity
      -> category
        -> source journal entries

V1.5 keeps that structure and provenance, but makes the underlying evidence explicit.

> **V1 tries to say what something means. V1.5 first records what happened, what was observed, and what an agent thought it meant.**

This remains an observational tool. It does not influence agents or the live world.

## 1. Core data model

Each entity may contain four primary evidence types:

    entity
      observations
      interpretations
      behaviours
      associations

### Observations

Something the agent appears to report as an observation.

> "The well was quiet."

Store:

    entity: well
    type: observation
    concept: quiet
    source: journal entry

Do not infer whether quiet is comforting, ominous, mysterious, etc.

### Interpretations

Something the agent appears to believe, infer, imagine, or attribute.

> "The well was dark and unknowable."

Store:

    entity: well
    type: interpretation
    concept: unknowable
    source: journal entry

### Behaviours

Something the agent actually did involving the entity.

> "stacked one more stone on the cairn"

Store:

    entity: cairn
    type: behaviour
    action: stone_added
    source: journal entry

Behaviour may be stronger evidence of cultural significance than descriptive language.

### Associations

A recurring conceptual association between an entity and another object/concept.

> "left a blue glass pebble on the cairn"

May produce:

    entity: cairn
    type: association
    associated_with: blue_glass_pebble
    source: journal entry

Do not automatically interpret an association as a belief.

## 2. Preserve V1 categories

Existing categories such as `comfort`, `mystery`, `memory`, `danger`, and `affection` remain useful, but become **derived analytical labels**.

For example:

    well
      interpretations
        unknowable

      derived_categories
        mystery

The underlying evidence must remain available.

## 3. Provenance

Every evidence item retains:

- journal entry index
- day
- displayed agent/hand name
- original text
- evidence type
- extracted concept/action
- optional extraction confidence

Names are not assumed to identify persistent agents.

## 4. Distinct visits

For every recurring pattern, track:

    mentions
    distinct_visits
    first_seen
    last_seen

Example:

    well / interpretation / watchful
      mentions: 7
      distinct_visits: 5

Use distinct visits when assessing recurrence.

## 5. Multiple observations from one entry

One journal entry may produce multiple evidence items, but all remain one visit.

For example:

> "Left a blue glass pebble on the cairn — small thing, but the cairn remembers what the forest doesn't."

May produce:

    cairn
      behaviour:
        object_left

      interpretation:
        remembers

    forest
      interpretation:
        does_not_remember

These do not count as multiple independent confirmations.

## 6. Aggregation

For each entity + evidence type + concept/action, maintain:

    total_mentions
    distinct_visits
    first_seen
    last_seen
    source_indices

Example:

    cairn / behaviour / stone_added
      total_mentions: 9
      distinct_visits: 8
      first_seen: Day 21
      last_seen: Day 31

## 7. No single "belief score"

Do not reduce evidence to a single belief value.

Instead expose counts:

    well / interpretation / watchful
      mentions: 5
      visits: 4

This supports the statement:

> "Watchfulness has appeared across four visits."

It does not justify:

> "The lineage believes the well is watchful."

## 8. Preserve contradictions

Keep competing interpretations side by side:

    well
      interpretations:
        watchful
        unknowable
        peaceful
        ordinary

Contradiction is data.

## 9. Behaviour versus language

Track both.

For example, the cairn may have:

    stones_added: 9 visits
    described_as_remembering: 2 visits

This lets us later ask whether something matters because people **do things with it**, **talk about it**, or both.

## 10. Temporal information

Retain first and last appearance.

Do not yet decide whether a pattern is "growing"; preserve enough information to calculate that later.

## 11. Candidate entities and concepts

Initially focus on known persistent entities such as:

- well
- cairn
- forest
- hearth
- lamp
- curio shelf
- statue
- cat
- recurring paths/locations

New candidates may be surfaced conservatively.

Concepts can initially include:

- comfort
- mystery
- danger
- memory
- affection
- beauty
- curiosity
- usefulness
- luck
- ritual

These are analytical vocabulary, not world facts.

## 12. Confidence

Extraction confidence describes how confident the extractor is that an evidence item was correctly identified.

It does **not** mean truth.

For example:

    confidence: 0.94

means the extractor is fairly confident that the sentence expresses the concept; it does not mean the well is 94% mysterious.

## 13. Rebuildability

Support:

    rebuild_lineage_memory()

This reads the journal and reconstructs the derived index using the current extraction rules.

The journal itself is never modified.

## 14. Backwards compatibility

Existing V1 data should remain usable.

A V1 category can become:

    derived_category
      supporting_evidence

If a V1 category cannot be confidently decomposed into observation, interpretation, behaviour, or association, retain it as:

    legacy_category

Do not invent precision that the source data does not support.

## 15. Developer-facing output

The report should answer:

### What keeps recurring?

    well / interpretation / watchful
      5 mentions
      4 visits

### What do people actually do?

    cairn / behaviour / stone_added
      9 mentions
      8 visits

### What is being interpreted?

    cairn / interpretation / remembers
      2 mentions
      2 visits

### Where are interpretations contradictory?

    well
      watchful: 5
      peaceful: 3
      ordinary: 2

### What is new?

    blue_glass_pebble -> cairn
      first observed Day 30

Always retain access to the source entries.

## 16. Explicit non-goals

V1.5 does not:

- influence agents
- influence prompts
- alter goals or personalities
- modify world state
- alter live descriptions
- create quests
- create lore
- make interpretations true
- resolve contradictory beliefs
- rename entities
- reward recurring interpretations
- suppress recurring interpretations
- steer Emberworld's mythology or tone

It is read-only with respect to the simulation.

## 17. Minimum V1.5 implementation

1. Keep V1's entity structure.
2. Separate evidence into observations, interpretations, behaviours, and associations.
3. Preserve original journal excerpts.
4. Add distinct-visit counts.
5. Preserve first/last occurrence.
6. Preserve source indices.
7. Mark broad semantic categories as derived.
8. Preserve contradictory evidence.
9. Support rebuilding from the journal.
10. Keep the system read-only with respect to the live simulation.

## 18. Intended result

V1.5 should be able to say:

> "The cairn has appeared in 14 visits. Stones have been deliberately added in 8 visits. Two visits describe it as remembering. Three visits associate it with the forest."

It should not jump straight to:

> "The cairn is a mysterious cultural landmark."

The first is evidence.

The second is interpretation.

**We want the evidence first.**

## Guiding principle

> **Record what the agents did and thought before deciding what it means.**

V1.5 makes the journal easier to study without making the agents easier to predict.

The purpose is not to manufacture culture. It is to make emergent culture legible enough that, later, we can decide whether any of it deserves to become part of the game.

