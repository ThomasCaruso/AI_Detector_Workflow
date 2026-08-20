# Candidate Reranking

Use this method when a draft is semantically correct but the sentence choices keep collapsing toward generic analytical prose.

## Why this exists

A portable Skill cannot directly change the host model's tokenizer, logits, temperature, top-p, or sampling implementation. It can, however, change the selection process before a sentence is finalized.

Instead of accepting the first fluent continuation, generate a small internal candidate set and choose among alternatives.

## 1. Start from content atoms, not polished source sentences

Reduce each idea to terse semantic fragments first. This weakens accidental copying of the source's opening, syntax, and transition sequence.

For example:

`rival ships cheaper product / customer can switch / margins compress / managers fund uncertain R&D / delay becomes costly`

The fragments are not output. They are a temporary representation of meaning.

## 2. Generate materially different candidates

For a major sentence or cluster, silently consider at least three versions. A valid candidate set changes construction, not just vocabulary.

Change at least two of:

- who or what is the grammatical subject;
- the main action;
- which fact appears first;
- clause order;
- sentence count;
- abstraction level;
- whether a contrast or transition is explicit;
- whether evidence and interpretation are combined.

Bad candidate set:

- Competition creates pressure to innovate.
- Competition generates pressure to innovate.
- Competition produces pressure to innovate.

Those are synonym variants.

Better candidate set:

- A rival that cuts its price forces everyone else to revisit cost.
- Once customers can switch to a cheaper alternative, an inefficient process shows up in lost margin or lost sales.
- Manufacturing efficiency matters differently when another firm can turn a lower unit cost into a lower price.

## 3. Rank for fit, not rarity

Choose the candidate that best satisfies these questions:

1. Does it preserve the exact meaning and level of certainty?
2. Does it use nouns and actions that belong to this subject?
3. Is its syntax noticeably different from nearby sentences?
4. Does it avoid unnecessary rhetorical scaffolding?
5. Is it direct enough for the intended audience?

Do not reward a candidate merely for using rarer words.

## 4. Use a neighborhood check

A sentence can be good alone and still create a repetitive paragraph.

Before selecting it, compare it with the previous two sentences:

- same opening pattern?
- same clause count?
- another three-item list?
- another mirrored contrast?
- another abstract subject such as `competition`, `pressure`, `innovation`, or `this`?

If so, prefer an equally clear candidate with a different construction.

## 5. Stop after selection

Once the paragraph is clear, specific, and faithful, stop polishing. Repeated cleanup tends to normalize cadence and remove useful variation.

The goal is controlled selection among clear alternatives, not maximal irregularity.

## Voice samples

If the user supplies authentic writing samples, candidate ranking should favor the constructions that resemble the user's observable syntax, density, directness, and vocabulary. Do not copy distinctive phrases unnecessarily and do not invent experiences or beliefs.

## Boundary

Candidate reranking is a writing-quality method. It does not provide direct access to token probabilities and should not be represented as changing the model's tokenizer or decoding parameters.
