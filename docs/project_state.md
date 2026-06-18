# Access to Justice — Project State

*Replaces the Google Drive–native project brief and the separate Technical Environment doc. This file lives in the repo and is read by Claude in claude.ai directly via the Google Drive connector, since this repo folder is itself synced to Google Drive under CloudStorage. Read this file in full at the start of every new thread. Read docs/project_log.md only when something specific needs the history or reasoning behind a decision, it is not required reading by default. Read docs/environment.md directly when a thread involves build work needing the full technical inventory.*

*Maintenance: update this file in the same commit as the change it describes, not after every conversation, after every real change. This is a plain git-tracked file, its history lives in git log, there is nothing to create as a new revision or delete manually. If a thread reports a change that should be reflected here and isn't, that's a signal something got missed, flag it rather than letting it slide.*

---

## What this project is

An AI product designed to support people navigating the UK family court system without legal representation, litigants in person going through divorce and family law proceedings. The product is a companion, not a lawyer. It provides comprehension, process guidance, document support, and emotional grounding throughout the entire legal journey, from the first letter to the final hearing.

The founding insight is personal. Vilam has been through the UK court system himself and watched a close friend go through divorce proceedings without adequate support.

## What this product is not

Not a legal firm. Not a McKenzie friend service. Not a replacement for legal advice. Not a generic legal chatbot.

## The regulatory boundary, non-negotiable

Under the Legal Services Act 2007, legal information, process explanation, and drafting support are not reserved activities. Recommending a course of action or predicting an outcome is. The product can explain what options exist and what a process requires. It cannot tell a user what to do in their specific case.

This is enforced at two points in the build: the system prompt's instructions, and an independent compliance check on every generated response, see Current build status below.

Hallucination risk: the product must never generate case law citations or present legal authorities unless verified. Layer 2 case law summaries are the controlled mechanism, verified summaries only, no generated citations.

UK GDPR: data users share falls into special category territory under Article 9. The memory layer architecture is built around this as a first-order requirement. The Data (Use and Access) Act 2025's automated decision-making provisions (Articles 22A to 22D, in force since 5 February 2026) are low risk for ATJ's use case but must be raised with the solicitor during legal consultation. The ICO's January 2026 agentic AI report requires the data minimisation logic to be documented at the agent level, individuals informed when special category data may be used or inferred, and memory storage able to be switched off per user without breaking the product.

Actions still required before real user data touches the system: solicitor consultation on the information-versus-advice boundary (timing resolved, runs in parallel with build, not yet sent, Vilam's call), the full legal GDPR compliance framework, and a specific legal opinion on the in-room recording feature before it's prioritised. Hosting is decided: DigitalOcean, London (LON1) region. A hardened staging droplet now runs there, Docker Compose with atj-db and atj-neo4j, both bound to localhost only, reachable via SSH tunnel, see the Staging environment section in environment.md for detail. OPENAI_API_KEY and ANTHROPIC_API_KEY were set manually via SSH on 18 June 2026. Staging is no longer blocked on API key entry.

## Roles and working method

Vilam is the director: owns product vision, makes final calls, is the quality standard.

Claude in claude.ai is thinking partner and technical lead: writes all code, prepares complete Claude Code prompts, updates this file as part of the same commit as real changes. Never touches the filesystem directly.

Claude Code, run through the VS Code extension on Vilam's Mac, executes: Vilam pastes prompts, runs them, reports commit hashes and output back.

At the start of every new thread: read this file in full first. Don't assume GitHub access works from claude.ai directly, it doesn't, beyond a manual one-off file attach via the "+" button (doesn't persist) or asking Vilam to run a read-only Claude Code command and paste the output back.

## The process this product is built through

Discovery, synthesis, product definition, prototyping, build, pilot, iterate and launch, in repeating cycles of diverging and converging at every scale. Discovery is not complete until the five most painful moments in the journey are clearly understood and there's confident signal about what people would pay and when, minimum eight to ten research conversations. Build runs architecture, then knowledge base, then memory layer, then interface, each phase tested before the next begins. No launch until a ten-to-twenty-person pilot says it works.

## The person it is for

Primary user: someone going through divorce or family court proceedings in England and Wales without full legal representation. Not legally trained, almost certainly frightened, not stupid, simply outside a system not designed for them.

Secondary users: people in early stages of separation, people supporting a friend or family member, potentially McKenzie friends.

Geographic focus: England and Wales only.

## What the product does

A companion for the entire legal journey, not a one-off tool or document generator. Planned capabilities, phased: comprehension (explaining letters, orders, forms, documents in plain English), process guidance (where you are, what happens next), document support (drafting position statements, witness statements, correspondence, always framed as first drafts for review), preparation (getting ready for a hearing), and live support (real-time transcription and explanation during a hearing itself, the hardest to build, requires a dedicated legal opinion before prioritisation).

## Core product principle

The product should behave with the common sense of a knowledgeable, calm friend who happens to understand the family court system. When something is unclear, ask. When something looks wrong, flag it. When something is sensitive, pause and explain. Never automate past a moment a reasonable person would stop at.

## The problem, in numbers

In 2024, 39% of all private family law cases had both parties appearing without legal representation, up from 13% in 2013. Around 80% of cases had at least one unrepresented party. 75 to 80% of litigants in person are in court because legal representation is financially out of reach. In 2025, 270,474 new family court cases were filed. In 2024 the average private law case took 43.3 weeks from start to disposal, up from 25.1 weeks in 2018.

## The family court journey map

Most unrepresented people don't realise these are three separate, simultaneous legal processes. That disorientation is itself a product moment.

Divorce track: decision and first steps, filing the application, 20-week cooling-off period, conditional order, 6-week wait and final order.

Financial remedy track: MIAM, Form A, financial disclosure via Form E (full disclosure under a statement of truth, one of the most technically demanding stages for unrepresented parties), First Appointment, Financial Dispute Resolution (most cases resolve here), final hearing.

Child arrangements track: MIAM, C100 application, Cafcass safeguarding checks, FHDRA, DRA, final hearing.

Highest pain points: the realisation that finances and children are separate tracks, Form E itself, the night before a hearing, not knowing your procedural rights inside the hearing room, and the gap between hearings where directions and deadlines accumulate and get missed without a lawyer tracking them.

## Competitive landscape

Caira by Unwildered, closest competitor, UK-based, £15/month, broad legal chatbot with no persistent case context or journey tracking. Lawhive, UK AI-powered law firm, fixed-fee services, not a competitor for pure self-representation. Contend Legal, free AI legal chatbot, information layer only. The gap: nobody has built a purpose-built, end-to-end companion specifically for the England and Wales family court journey.

## Pricing hypothesis

£25 to £49 per month, to be validated through discovery. Pay-per-stage is worth testing as an alternative.

## Technical architecture

Three components. RAG: a curated knowledge base of UK family court law, procedure, forms, and HMCTS guidance, retrieved per turn alongside the user's question. Persistent memory layer: extracts what matters from every session into a structured knowledge graph, retrieved at the start of each new session so the product picks up where it left off. Claude API: the reasoning engine.

---

## Current build status

Discovery: in progress. One conversation completed (C-001). Critical research gap: no conversation yet with someone who had zero legal representation throughout their entire proceedings, this is the priority respondent type.

Knowledge base Layer 1 (raw source content): complete, 571 files, 2,576 chunks.

Knowledge base Layer 2 (explanatory content): 42 entries committed and embedded, 99 chunks. Blocked: Form E, Form G, both need the MyHMCTS journey mapped first. Deferred by design: second terminology pass, until discovery surfaces what gaps matter most.

Embedding pipeline: complete and signed off. 2,675 chunks total in pgvector.

Retrieval evaluation: 82.6% overall context recall (57/69 pairs), layer1 78.3%, layer2 84.8% (39/46). This is current as of the golden set correction pass and the terminology__directions content rewrite, both this session, see project_log.md for the full diagnosis. 14 misses were identified before these fixes: 2 are expected discovery gaps (content doesn't exist yet), 2 were the terminology__directions pairs now fixed by this session's content rewrite. The remaining misses from that diagnostic weren't individually characterised and may be worth a fresh look.

KB live update pipeline: complete. Delta detection, Claude API triage, evaluation gate, GitHub Actions monthly cron, all committed and working.

Memory layer: built and compliant. Neo4j via neo4j-agent-memory v0.5.0, but using custom Cypher via AsyncGraphDatabase directly, not the library's own MemoryClient, since add_entity() has no per-user scoping and search_entities/search_facts are global unfiltered searches. Only extracted facts are ever written, never raw conversational text. An independent compliance check (a second Claude API call) reviews every extracted fact before it's written and discards anything that fails, logged as audit_reject. Fact supersession via invalid_at now covers all fact types. case_stage uses blanket supersession (new stage always replaces the old). All other types use LLM-based reconciliation: on each write, existing active facts of the same type are retrieved for the user and a small model decides whether the new fact is an update to an existing one or genuinely new. On update, the target node is marked invalid_at before the replacement is written. Fail-safe defaults to new on any uncertainty or parse failure. All five test suites pass (test_memory_smoke, test_memory_isolation, test_memory_supersession, test_memory_compliance, test_memory_reconciliation). retrieve_memory returns at most RETRIEVE_MEMORY_LIMIT (50) facts per call, newest first; if truncated, the return dict signals this and chat.py both warns to stdout and notifies the model that context is incomplete.

Reasoning engine: connected end to end (memory retrieval, KB retrieval, Claude API call, independent response check, memory write) but only via a CLI test harness (scripts/chat.py), explicitly not a production interface. Internal testing only, between Vilam and Claude. The system prompt has not yet been reviewed by a solicitor.

Independent response check: built. On a failed compliance check, a fixed fallback response is shown instead of the model's draft or a silent block: "I can't answer that one directly, it would mean telling you what to do in your own case, and that crosses from giving you information into giving you advice, which isn't something this can responsibly do. What I can do is explain what's actually happening at this stage, or set out the options that typically exist here without picking one for you. Tell me which of those would help, or if this feels like the kind of call a solicitor, McKenzie friend, or Citizens Advice should weigh in on, I can help you think through what to ask them." Every check, pass or fail, is logged to logs/chat_ops.jsonl with the original failing draft preserved for review, never silently discarded.

Log retention: scripts/prune_logs.py exists. LOG_RETENTION_DAYS = 90 is an explicit placeholder pending legal review, not a validated compliance figure. No file locking yet, safe only for single-developer manual runs, needs real locking before ever being scheduled against live concurrent traffic.

Plan Mode: Claude Code defaults to plan mode project-wide (.claude/settings.json). Every Claude Code prompt includes a containment question; prompts touching the memory layer, the legal information/advice boundary, or irreversible actions also include a stress-test question. Caveat: the stress-test question is still the same Claude Code session checking its own work, weaker than the independent check already built into the product, the separate compliance-check model in memory.py and response_check.py, a genuinely different model reviewing output with no visibility into the first model's reasoning. Acknowledged limitation, not solved.

Production readiness: secrets management, observability, and GDPR data architecture are met in code. Data minimisation decision log exists on Drive (Version 2, unchanged by this restructuring, still Drive-native for now). Hosting provider decision and the full legal GDPR framework remain outstanding, see regulatory boundary above.

## Open items / next steps

Continue discovery, priority is finding someone with zero legal representation throughout.

Run the next discovery conversation; any financial remedy participant must be asked specifically about their Form E experience on MyHMCTS.

Follow up with Support Through Court (Charlotte Rook contacted, response pending, escalation contact is Emma Taylor, CEO).

Outreach in progress across multiple channels, current status tracked in Airtable (base appqkREbZXUDLBlZ5, Channels table), not duplicated here since Airtable is the system of record.

Send prompts/system_prompt.md to whoever is lined up for the solicitor consultation when Vilam decides to action it, this is the priority artefact for that review, not a general discussion of the product concept.

Map the MyHMCTS Form E journey, required before the Form E Layer 2 entry can be written.

Second terminology pass, deferred until discovery informs what gaps matter most.

Full legal GDPR compliance framework, instruct a solicitor, running in parallel with build.

No human review queue exists for response_check.py fallbacks or memory layer audit_rejects. A false positive, the check wrongly blocking a fine answer, currently only surfaces in the log, nobody reviews it. Acceptable while only Vilam and Claude are testing via the CLI harness. Must be addressed, even just manual log review, before any real user, including pilot participants, has a live session.

Compliance model false positive on family court abbreviations: Haiku rejected "FDA hearing" (First Directions Appointment) as out-of-scope, misreading it as Food and Drug Administration. Non-deterministic — passes on some runs, fails on others. Core family court vocabulary must not be audit-rejected. Fix: add an explicit abbreviations glossary to _COMPLIANCE_SYSTEM in memory.py before any real user session. Tracked here; not urgent while only test data is being processed.

Reconciliation gap — same-turn duplicates: _reconcile_facts only compares new facts against what is already in Neo4j. If two facts about the same evolving thing arrive in the same conversational turn, neither will supersede the other. Narrow edge case, acceptable for now, revisit if it surfaces in real sessions.

Monitor NAMS (Neo4j Agent Memory Service) for UK/EU region availability, would simplify self-hosting if it arrives.

Decide whether to build a cheap, narrow paid guide as a pre-launch validation and audience-building test, flagged, not decided.

Drive cleanup: now that this file and project_log.md are canonical, the old Drive-native brief revisions, the Technical Environment doc, and old handover docs in the ATJ parent folder are obsolete. Vilam's call on deleting versus archiving them.

Decision Log (data minimisation) review: still Drive-native, the same repo-file pattern used here could apply to it too, not yet actioned.

## File locations

Repo: https://github.com/veeyastudio-wq/atj-knowledge-base. Local path on Vilam's Mac: /Users/admin/Library/CloudStorage/GoogleDrive-veeya.studio@gmail.com/My Drive/Claude Workspace/Access to Justice/KB.

Google Drive ATJ parent folder: 18p6KDaCEV-LQ20jD1JMgRtp-J-0kOD7t. Data Minimisation Decision Log (Version 2) lives here, still Drive-native: 1xr5tUcfL0XCiPNo7P_XWt4JpTk9dK4nT.

Airtable base: appqkREbZXUDLBlZ5. Channels tbl4x8lOYPQ4xJqSu, Respondents tblOoOHP124QDgGGe, Conversations tblFFVtLqYO2NHVJy, Insights tblpuU2UbQFm9qsbK, Reference tblxeuTwAjXdaoHUP.

Local infrastructure: atj-db (pgvector/pg16, port 5432, RAG only), atj-neo4j (Neo4j 5.26 community, memory layer only). Both must be running before relevant scripts. Credentials live in .env only.
