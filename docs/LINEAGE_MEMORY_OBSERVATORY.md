# Lineage Memory / Culture Observatory

## Status

Built (v1: rule-based extraction only — see docs/ARCHITECTURE.md's
"Lineage Memory" section for the landed shape and what's deliberately
deferred). The extraction approach was the one real open decision this
proposal left unresolved (section 20 sanctions an LLM step but doesn't
mandate it); v1 chose keyword-based matching over entities/concepts
instead, explicitly as a placeholder to get the rest of the pipeline
(storage, incremental processing, `--lineage-report`) working end to end
first. That means v1 does NOT attempt several things this doc asks for:
the observation-vs-interpretation distinction (section 7), naming and
symbolic-act detection (section 6), and behavioural tracking (section 11)
all need real language understanding a keyword table can't provide —
every match is recorded as a plain, unlabeled association instead, never
mislabeled as an "interpretation" it can't actually verify. The doc's
"visit" as the unit of evidence (section 4) also became the journal
entry itself in the landed version: (day, hand name) was considered and
rejected, since two different hands sharing a name on the same day is a
real, observed occurrence in this lineage, and merging them would
silently conflate distinct evidence.

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
