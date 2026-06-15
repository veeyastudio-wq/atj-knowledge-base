> **Canonical reference.** This file is the source of truth. The Google Drive copy (ATJ_Layer2_Entry_Format_Spec) is a working draft space only.

# ATJ Knowledge Base — Layer 2 Entry Format Specification
*Version 1.0 — 10 June 2026*

## Purpose

This document defines the structure of every Layer 2 KB entry. Layer 2 is explanatory content — written by us, grounded in Layer 1 sources, designed to be retrieved by the RAG system and fed to the model when a user asks a question. It is not documentation for Vilam to read. Every formatting and structural decision here is made for retrieval quality, not human readability.

## Core principles

Every entry must be self-contained. A retrieved chunk arrives at the model in isolation, with no surrounding context. Phrases like "as mentioned above" or "see the previous section" are retrieval failures. Each entry must make complete sense on its own.

One topic per entry. If a chunk covers two topics, retrieval accuracy drops because the embedding represents a blend of both. Split rather than combine.

Discovery gaps are explicit, not omitted. Sections that require input from research conversations are not left blank — they carry a visible inline comment and a frontmatter flag. This allows systematic completion after discovery without losing track of what is missing.

Layer 1 and Layer 2 entries are kept separate at indexing time. They should not compete for the same retrieval slot. The layer frontmatter field supports this separation.

## Entry types

Five entry types. Each uses the same base frontmatter and body structure, with variations noted below.

content_type: process_explanation — A hearing type, a procedural stage, or a court process
content_type: document_explanation — A form, order, or legal document
content_type: legal_principle — A principle that governs how a judge approaches a decision
content_type: case_law_summary — A specific case and the principle it established
content_type: terminology — A legal term a litigant is likely to encounter

## Base frontmatter — all entry types

---
content_type: # process_explanation | document_explanation | legal_principle | case_law_summary | terminology
layer: 2
title: # plain English title, e.g. "What is a First Appointment (FDA)?"
track: # divorce | financial_remedy | child_arrangements | cross_cutting
stage: # journey map stage this applies to, e.g. "Stage 4 — First Appointment (FDA)"
source_refs: # list of Layer 1 file slugs this entry draws from
jurisdiction: England and Wales
last_updated: # ISO date, e.g. 2026-06-10
discovery_gap: # true | false
---

Field notes:

- track: use cross_cutting for entries that apply across more than one track (e.g. MIAM, McKenzie friends, legal aid)
- stage: use the exact stage label from the journey map in the project brief; use pre_proceedings or cross_cutting where no single stage applies
- source_refs: list the slugs of the Layer 1 files this entry is grounded in; minimum one ref required; this is the audit trail for accuracy
- discovery_gap: set to true if any section of the entry contains an inline discovery gap comment; set to false only when all gaps are filled

## Body structure — process_explanation and document_explanation

# [Title]

## What it is
One to three sentences. Plain English definition. No assumed knowledge.

## When it happens
Where in the journey this occurs. What triggers it. What comes before and after.

## What it involves
The substance. What actually happens at this stage or with this document. What the judge or other party does. What the litigant must do or produce.

## What to know if you're unrepresented
The specific things an unrepresented person needs to understand that a represented person's lawyer would handle. This is the highest-value section for retrieval.

## Common mistakes
What typically goes wrong at this stage or with this document. Fill from discovery.

<!-- discovery gap: to be completed after research conversations. Expected input: what unrepresented people typically get wrong here, from direct respondent accounts. -->

## Key terms
Any legal terms used in this entry that a litigant may not know, defined briefly inline.

## Related entries
Slugs of related Layer 2 entries.

## Body structure — legal_principle

# [Title]

## What it is
One to three sentences. Plain English statement of the principle.

## Where it comes from
The statute or case that established it. One sentence.

## What it means in practice
How this principle operates in the courtroom. What a judge is actually doing when they apply it. Written for someone who has never been in a family court.

## What it means if you're unrepresented
How understanding this principle changes how you approach your case, your submissions, or your preparation.

## Related entries
Slugs of related Layer 2 entries.

## Body structure — case_law_summary

Additional frontmatter field required:
citation: # e.g. "White v White [2000] UKHL 54"

# [Case name]

## What was decided
One to three sentences. What the court decided in plain English. No legal jargon.

## What principle it established
The rule or principle this case created or confirmed. This is what gets cited in court.

## Which track it applies to
Financial remedy / child arrangements / both.

## When you are likely to encounter it
The specific moment in proceedings when this case is likely to be referenced.

## What it means if you're unrepresented
Why knowing about this case matters. What you should understand before it comes up.

## Related entries
Slugs of related Layer 2 entries.

## Body structure — terminology

Shorter format. One entry per term. Minimum word count is 100 words — the general 200-word floor does not apply to terminology entries.

# [Term]

## What it means
Plain English definition. One to four sentences maximum.

## When you will encounter it
The context in which this term appears — in a letter, in court, on a form.

## Track
Which track(s) this term is most associated with.

## Related entries
Slugs of related Layer 2 entries.

## Filename convention

{content_type}__{slug}__{track}.md

Examples:
process_explanation__fda_hearing__financial_remedy.md
document_explanation__form_e__financial_remedy.md
legal_principle__welfare_principle__child_arrangements.md
case_law_summary__white_v_white__financial_remedy.md
terminology__without_prejudice__cross_cutting.md

## Output directory

raw/layer2/

Subdirectories by content type:
raw/layer2/process_explanations/
raw/layer2/document_explanations/
raw/layer2/legal_principles/
raw/layer2/case_law_summaries/
raw/layer2/terminology/
raw/layer2/_discovery_gaps.md — auto-maintained list of all entries with discovery_gap: true

## Discovery gap management

When an entry is created with unfilled sections:
1. Set discovery_gap: true in frontmatter
2. Place this comment at each unfilled section:
<!-- discovery gap: to be completed after research conversations. Expected input: [description of what is needed]. -->

When the gap is filled after discovery:
1. Remove the inline comment
2. Set discovery_gap: false in frontmatter
3. Update last_updated to today's date
4. Update _discovery_gaps.md to remove the entry

## Two-pass writing process

Pass 1 — now. Write all structural content derivable from Layer 1 sources. Set discovery_gap: true where experiential content is needed. This covers: what things are, when they happen, what they involve, legal principles, case law summaries, terminology.

Pass 2 — after discovery. Return to each entry with discovery_gap: true. Fill the experiential sections from research conversation findings. Remove gap markers. Set discovery_gap: false.

## What Layer 2 does not contain

- Verbatim text from Layer 1 sources (that is what Layer 1 is for)
- Legal advice — no "you should" statements
- Predictions about outcomes
- Case law citations that have not been verified against a primary source
- Experiential content invented without discovery input — use a gap marker instead
