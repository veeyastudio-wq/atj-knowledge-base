# Access to Justice — Project Log

*The history behind project_state.md: what was built, what broke, what got fixed or reversed, and why decisions were made the way they were. Read this when investigating why something is the way it is, not by default at the start of every thread.*

---

## Memory layer architecture decision

Decided: neo4j-agent-memory, self-hosted on UK infrastructure via the bolt path, after evaluating three alternatives. Mem0 rejected: its V3 algorithm (April 2026) removed graph store support entirely, and Mem0 cloud runs on US infrastructure with no published DPA for UK/EU special category data. Zep/Graphiti rejected: best temporal reasoning in the field, but self-hosting means running Graphiti directly, equivalent operational burden to neo4j-agent-memory without the native Anthropic integration or mature multi-tenancy. NAMS (the hosted version) rejected for now: identical API, eliminates operational burden, but runs on Neo4j Aura with no UK/EU region, would mean sending Article 9 data to US infrastructure. Worth migrating to if Neo4j adds a UK/EU region, the migration would be configuration only.

The honest caveat discovered during the actual build: the library's high-level Python API doesn't support per-user scoping at every point ATJ needs it. See below for what that meant in practice.

## Memory layer build, what actually happened

First built 15 June 2026 (commit 8b0d295) with no accompanying build prompt or brief update, discovered two days later when the brief still said the build hadn't started. What it got wrong: write_memory passed raw conversational content straight into storage with extraction disabled, every message stored verbatim and indefinitely, a direct data minimisation violation.

Fixed 17 June 2026 (commit 49fb632): rewrote the write path to extract-then-discard, write_memory now calls the Claude API with an extraction prompt scoped to case stage, key dates, document status, party names, financial figures, orders made, hearing outcomes, explicitly excluding emotional expressions and anything resembling legal advice. No raw content is ever written to Neo4j.

Schema decision and reversal (commit d8af323): first pass stored every fact in one generic node. Reconsidered once a proper typed schema became cheap to build: every fact now written as (:User)-[:HAS_ATJ_FACT]->(:ATJFact:<Type>), Type being one of CaseStage, Hearing, Deadline, FinancialFigure, OrderType, or Person. Separately, add_entity() in the installed library has no user_identifier parameter and search_entities/search_facts are global unfiltered searches across all users, an actual cross-tenant leak, not hypothetical. Both findings meant MemoryClient was dropped entirely in favour of raw Cypher via AsyncGraphDatabase.

Retrieval ordering (commit 6441cda): retrieve_memory does not do semantic search, it runs a single Cypher traversal scoped to a user and returns every fact newest-first. The query parameter exists for API compatibility but is unused.

Fact contradiction over time, closed for one category, and independent compliance check added (both commit 6720466): every ATJFact carries an invalid_at property; writing a new case_stage fact marks the previous current one invalid before the new one is created, deliberately scoped to case_stage only since it's the one category where there's clearly ever one correct current value. The other fact types can legitimately coexist and matching a new one to an existing one is unsolved. Separately, a second smaller Claude model now reviews every extracted fact, given only its category and value, none of the original input, and judges it against the excluded categories; failures are discarded and logged as audit_reject.

Commit sequence: 8b0d295 → 49fb632 → d8af323 → 6441cda → 6720466. Tests: test_memory_smoke, test_memory_isolation, test_memory_supersession, test_memory_compliance, all pass.

## Reasoning engine build

prompts/system_prompt.md and scripts/chat.py committed 16 June 2026 (commit 6aeaab0), the same undocumented-commit pattern as the memory layer's first commit, found the next day by asking Claude Code to search the repo directly.

The system prompt defines the companion persona, states the legal information versus advice boundary with explicit reference to the Legal Services Act 2007, and works through it with three positive worked examples and one explicit negative example, the negative example targets the model fabricating a callback to something the user never said. It also reflects a direct discovery finding from conversation C-001: avoid adversarial language like "fighting your corner."

chat.py is a CLI orchestration loop, explicitly labelled in its own docstring as a validation tool, not the production interface. No atj-api directory, no app.py/main.py/orchestrator.py/server.py exist anywhere in the repo, there is no path from here to a real user without the production interface being built.

Independent response check built 17 June 2026 (commit 0377aee), mirrors the memory layer's audit_reject pattern applied to the reasoning engine's output. check_response sends only the user message and assistant text, nothing else, to the same compliance model already used for memory, asking whether the response crossed from information into recommending a course of action.

Calibration note worth keeping: the checker's first version flagged the approved example's line "consent if the amount looks fair" as advice, a false positive, listing a standard procedural option had been read as a recommendation. Fixed with an explicit rule in the checker's own instructions: listing options without ranking them is information, recommending one specifically is advice. That distinction is load-bearing in the checker prompt now, not just implied.

## Independent response check, failure handling design (this session)

Decided: on a failed compliance check, substitute a fixed, non-generated fallback response rather than blocking silently or regenerating, there's no real failure data yet to design a smart retry around. Fallback text: "I can't answer that one directly, it would mean telling you what to do in your own case, and that crosses from giving you information into giving you advice, which isn't something this can responsibly do. What I can do is explain what's actually happening at this stage, or set out the options that typically exist here without picking one for you. Tell me which of those would help, or if this feels like the kind of call a solicitor, McKenzie friend, or Citizens Advice should weigh in on, I can help you think through what to ask them."

Implemented in scripts/chat.py and scripts/response_check.py (commit f513151). A displayed_text variable (fallback on fail, the real assistant text otherwise) replaces assistant_text everywhere downstream, the console print, the in-session conversation history, and both write_memory calls, verified by reading the actual source, not relayed. response_check.py logs every check to logs/chat_ops.jsonl with two new fields, original_draft (the raw failing text, null on pass) and fallback_substituted (boolean). The new user_identifier/session_id parameters feed only the log, never the compliance model call itself, confirmed via source.

## Log retention (this session)

chat_ops.jsonl was found to store full plaintext of blocked responses indefinitely with no deletion job, more sensitive than before and outside the scope of the existing Decision Log, which only covers Neo4j. Built scripts/prune_logs.py (commit 13aa036) with LOG_RETENTION_DAYS = 90 explicitly marked as a placeholder pending legal review, not a validated compliance figure. Generic, path-parameterised, atomic .tmp-then-replace write pattern. A concurrency gap was caught: the script assumes no concurrent writer, fine for single-developer manual runs now, needs real file locking before ever being scheduled against live concurrent traffic, documented in code rather than silently assumed. test_prune_logs.py covers stale-.tmp recovery and malformed-line handling (kept rather than guessed-and-deleted).

## Golden set staleness, diagnosis and fix (this session)

Root cause: evaluate_retrieval.py scopes each golden pair's search to its own tagged layer field, so a layer1-tagged pair can never surface a better layer2 chunk even if one exists, caught before it became a silent no-op, since a corrected expected_chunk_id alone would do nothing without also flipping layer to layer2.

Built scripts/propose_golden_updates.py (commit 91a1c02) as a permanent reusable utility, producing eval/golden_set_update_proposal.json. 9 proposals reviewed individually: 6 accepted, 3 rejected. Two rejections were pairs about "making an application generally" and "C100 online filing," both wrongly matched to a serving_applications chunk, conflating filing with serving. One rejection was "financial settlement hearing documents," where a specific Form E/ES1/ES2 checklist beats a general track overview for that exact question.

Applied to eval/golden_set.json (commit 8b5219b): 6 corrections (expected_chunk_id, layer, and source_file) for Tipstaff terminology, FP2 document explanation, consent order explanation, statement-of-truth terminology, serving-at-refuge process explanation, and who gets sent the application. Verified field-by-field that the other 63 entries were untouched.

Score movement: overall 75.4% (52/69) to 79.7% (55/69). Layer1 72.4% to 78.3% (the exclusions removed from that layer were the cause). Layer2 77.5% to 80.4% (37/46).

Diagnostic surfaced 14 remaining misses: 2 are expected discovery gaps, content that doesn't exist yet. 2 are terminology__directions pairs consistently losing to process_explanation chunks, a real retrieval-quality issue, not a golden-set labelling issue, see below. The remaining 10 weren't individually characterised in this pass.

## Terminology KB content fix, terminology__directions (this session)

Diagnosed via actual retrieve.py runs: a vocabulary mismatch, not a chunking problem, the file is a single chunk well under the 512-token limit both before and after.

Rewrote raw/layer2/terminology/terminology__directions__cross_cutting.md to add user vocabulary ("judge," "list," "sending in documents," "mandatory not optional") and a new "what happens if you miss a deadline" section. An early draft included an unverified claim that courts treat missing a deadline more harshly than an advance application, this was researched against the actual scraped FPR corpus and found to come from CPR 3.9/Denton, civil procedure that doesn't apply to family proceedings, removed and replaced with corpus-grounded language.

A second check caught that "or agree one with the other party in writing" had been silently dropped between drafts. Verification found direct corpus support for the opposite: FPR Part 4 rule 4.5(3) and Part 30 both state parties cannot extend deadlines by agreement, only the court can (rule 4.1(3)(a), which also confirms court extensions remain possible even after a deadline has passed). Final approved sentence: "If you need more time, you can apply to the court for an extension, including after a deadline has already passed. Parties cannot agree between themselves to extend a deadline set by a court order, only the court can."

Re-chunked, re-embedded, re-run (commit b37e8a1). Both target queries flipped from miss to hit. Score movement: overall 79.7% (55/69) to 82.6% (57/69). Layer1 unchanged at 78.3% (neither fix touched layer1). Layer2 80.4% (37/46) to 84.8% (39/46), exactly the two targeted queries, no side effects elsewhere.

## KB pipeline bug fixes

Triage parser bug (commit 5cf6647): the parser misread HTML comment placeholders, used intentionally to mark sections awaiting research input, as evidence of malformed content, causing false HOLD classifications on two entries (non-molestation order, FL401). Both now classify correctly.

Date serialisation bug (commit 3c1fc99): embed_kb.py's insert_chunk crashed on any file with a date field in frontmatter. Fixed with json.dumps(metadata, default=str).

Python environment upgrade (commit add3338): system Python 3.9.6 couldn't run neo4j-agent-memory, which requires 3.10+, and its pip predates --break-system-packages. Upgraded to 3.12.13 via Homebrew, all project scripts now run with python3.12, not system python3.

## Documentation fork incident, 17 June 2026

Two separate files, both titled and dated as Rev 33, existed simultaneously in the Drive folder, having branched independently from an earlier common revision without either thread aware of the other's work. One held the memory layer compliance account, the other held the brand research, outreach research, and several bug fixes. Merged into Rev 34 so nothing was lost. The standing lesson: before treating any single linked file as canonical, check the parent folder for other files with the same or similar title.

## Brand and launch research, 17 June 2026

Positioning: April Dunford's method starts from what the customer would do if the product didn't exist, for ATJ that's isolation, Google, and guesswork, not a competitor app or a solicitor. Positioning should be built against that, which keeps the product inside the regulatory line by construction.

Validating before building: the Mom Test reinforces the existing discovery discipline, ask about specific past behaviour and real commitments, not hypothetical opinions.

Cautionary tale: BetterHelp was fined $7.8M by the US FTC in 2023 for sharing mental health questionnaire data with advertisers after promising it would stay private. The same discipline behind the memory layer's local-embeddings decision has to extend to every future marketing and growth decision, not just the technical architecture.

Trauma-informed communication, SAMHSA's six principles (safety, trustworthiness and transparency, peer support, collaboration, empowerment and choice, cultural awareness), usable for onboarding and in-product UX, not just marketing copy. One discipline worth carrying forward: never use someone's hardship as the hook.

Closest comparable: Farewill, UK will-writing and probate, rebuilt a taboo, jargon-choked category around dignity and plain language instead of the solicitor aesthetic, became the UK's largest will writer within a decade. Second comparable: Valla, UK employment-law access startup, same underlying thesis, people give up on legitimate legal problems because help is priced out of reach, not because they lack a case.

Distribution: SeedLegals grew mainly by being useful inside communities its customers already gathered in, rather than advertising at them.

Working principles carried forward: position against navigating alone, not against solicitors or other apps. Build credibility through usefulness and presence, this audience won't follow a founder narrative the way a SaaS audience would. Treat trauma-informed language as a standing check on all copy and UX. Hold a hard line against ever using case detail or distress signals to improve targeting or conversion. A cheap, narrow paid guide is worth considering as a pre-launch validation test, not a pivot toward an info-product business.

## Outreach channel research findings

Citizens Advice already runs targeted litigant-in-person referral work in some branches, their 2016 report "Standing alone: going to the family court without a lawyer" is a credible source on this exact population. Advicenow (formerly Law for Life) is the closest sibling organisation found, plain English self-help guides, partnered with Resolution for a fixed-fee panel. Resolution publishes a Good Practice Guide for working with litigants in person. Family mediators and divorce coaches are an untouched channel, Mediate UK and Peaceful Solutions have formal referral pathways. McKenzie friend content creators are a small, well-matched audience: Philip Kedge, Graham Fletcher (111k+ views, built around his own litigant-in-person experience), Family Law Cafe.

Dave Barma and Gemma Bailey have already published a paid self-help PDF on Gumroad with active ad tracking, real commercial intent, changing outreach to them from a cold pitch into a conversation about something they've already built.

Pattern worth noting: the Domestic Abuse Survivors Group started as a two-person WhatsApp group because existing forums felt too complicated, and grew through peer word of mouth. Trust in this space tends to spread through small trusted circles, not broadcast.

## Conversation C-001, key findings

Respondent R-001, friend of Vilam, mid-proceedings, child arrangements, had representation throughout but inadequate, ran out of funds. The most valuable insight was the moment a more experienced lawyer laid out the other side's full strategy in one session, the product needs to show users the shape of the whole process. In the hearing room he didn't know when to speak, what he was allowed to say, or when to challenge, was "bulldozed into agreeing to things he should never have agreed to." Paid for legal advice four times he felt he didn't need. Strong language around "fighting your corner," product language must avoid this framing, it risks crossing the legal information boundary.

## Documentation workflow change, this session

The Drive-native brief (34 revisions) and the separate Technical Environment doc are retired in favour of docs/project_state.md and this file, both in the repo. This was possible because the repo folder is itself synced to Google Drive under CloudStorage, confirmed by directly searching Drive and finding docs/environment.md independently indexed there, meaning any file Claude Code writes into the repo is readable by Claude in claude.ai with no separate Drive-native copy and no manual relay from Vilam. The Data Minimisation Decision Log stays Drive-native for now, the same pattern could apply to it later.

## Self-correcting loop deferred, response_check.py (this session)

Decided not to build a self-correcting loop for response_check.py yet. Every check, pass or fail, already logs to chat_ops.jsonl with the original draft preserved, so nothing is lost by waiting. A correction mechanism needs real failure data to be designed against, not guessed at before any exists.
