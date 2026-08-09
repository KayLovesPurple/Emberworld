# Curio Visual Compression

## Purpose

Emberworld's curios are intentionally persistent. They can accumulate across many visits, and that accumulation is part of the world's lineage and character. The problem is presentation: an ever-growing list of individual curios will eventually make the hut noisy and difficult to read.

**Curio visual compression is a presentation-layer feature, not a world-state mechanic.**

The world may accumulate an unbounded number of curios, while the room description remains human-scale.

## Core invariant

Compression must never destroy, merge, transform, or otherwise alter curio world state.

Individual curios remain separate entities with their existing properties and history.

For example, three separate pinecone entities may render as:

> several pinecones

but they remain three separate entities to the game engine.

Compression changes only how the room is described.

## Scope

Initially, compression applies only to curios that are loose in the hut/room.

It does **not** apply to:

- the player's inventory
- the curio shelf
- the cairn
- the planted mystery seed
- the cat's internal state
- the journal

The shelf should remain individually legible because it is intentionally a curated collection. The cairn is already a collective, permanent structure and should remain mechanically distinct.

## Grouping rule

Curios may be visually grouped when they have the same display identity and occupy the same location.

Initially:

- same curio type
- same location
- same relevant display state

means that they are candidates for the same visual group.

For example:

> pinecone  
> pinecone  
> pinecone

may render as:

> three pinecones

while:

> pinecone  
> smooth grey stone  
> pinecone

may render as:

> two pinecones  
> a smooth grey stone

The ordering should remain broadly organic rather than turning the entire room into an alphabetically sorted inventory.

## Compression thresholds

Use a deliberately conservative first implementation:

- **1** → singular description
- **2–4** → exact count
- **5+** → approximate group description such as "several pinecones"

The exact underlying count is never lost.

The threshold should be treated as a presentation choice, not a world rule. It can be adjusted after observing real play.

## Compress repetition, not character

Not every curio should necessarily be treated as interchangeable.

A curio with an interesting persistent state should retain that character when possible.

For example, if the room contains:

- an ordinary pinecone
- an ordinary pinecone
- a pinecone well-battered after a game with Ember

do not simply render:

> three pinecones

A better presentation might be:

> two pinecones and a battered pinecone

or, at larger counts:

> several pinecones, including one well-battered from a game with Ember.

The important principle is:

**Compression removes repetition, not character.**

Start with the simplest grouping implementation. Introduce more sophisticated representative descriptions only when actual play demonstrates that they are needed.

## Interaction

Compression must not require a new inspection verb.

Emberworld already uses `look` for perception and inspection, so **`look` remains the universal inspection verb**.

Do not introduce `examine` merely to support compression.

Examples:

### Room description

> several pinecones lie near the hearth

### Looking at the group

`look pinecone`

could return:

> There are seven pinecones here. Most are ordinary. One is well-battered from a game with Ember.

### Taking one

`take pinecone`

takes one underlying pinecone.

Afterward, the rendered description updates automatically:

> several pinecones

may become:

> four pinecones

and eventually:

> three pinecones

The player should not need to learn a separate command for interacting with compressed groups.

If the parser eventually needs to distinguish individual members, use the existing `look`/action vocabulary and descriptive qualifiers rather than adding `examine`.

For example:

> `look battered pinecone`

could refer to the distinctive individual.

## Architecture

Compression should happen as a final presentation pass, after ordinary world/entity logic has determined what is present.

Conceptually:

    world state
        ↓
    find entities visible in hut
        ↓
    generate ordinary descriptions
        ↓
    curio compression pass
        ↓
    render room

Do not put compression state onto the curios themselves.

A compressed group should be a temporary rendering construct, not a new persistent entity.

## Mechanical invariant

Changing compression must never change the result of an action.

A world containing five pinecones is mechanically identical whether those pinecones are rendered as:

> pinecone, pinecone, pinecone, pinecone, pinecone

or:

> several pinecones

The renderer is summarising the state, not modifying it.

## Longer-term direction

If simple grouping proves successful, a later presentation tier could become more environmental.

For example:

- 1–4: exact descriptions
- 5–9: "several ..."
- 10+: "a little scatter of ..." / "a small collection of ..."

This should **not** be implemented initially.

The idea is that sufficiently repeated ordinary objects may eventually become part of the hut's environmental texture without being deleted from the world.

For example:

> a little scatter of pinecones lies near the hearth

would mean that the room has accumulated enough pinecones for them to read as part of the place.

Again, the underlying entities remain intact.

## Curio-specific exceptions

A future extension may allow particular curio types to opt out of compression when their individuality is especially important.

For example:

- ordinary pinecones → groupable
- ordinary feathers → groupable
- ordinary stones → groupable
- unusual glass pebble → potentially individual
- strange/mystery objects → potentially individual

Do not add this configuration until real play demonstrates a need for it.

## Relationship to existing curio design

The existing curio system already gives objects several possible destinations:

- carried by a visitor
- given to Ember
- placed on the shelf
- stones added permanently to the cairn

Compression should not create another mechanical destination. It only prevents the hut's textual representation from growing without bound.

The shelf remains curated and finite; the cairn remains collective and permanent; the hut's loose curios remain individually persistent but may be visually summarised.

## Design principle

> **Curio compression is presentation, not state.**

The world may remember every curio without requiring the room description to name every curio.

And the central rule is:

> **Compress repetition, not character.**
