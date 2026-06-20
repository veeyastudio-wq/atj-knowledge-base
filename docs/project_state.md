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

Memory layer: built and compliant. Neo4j via neo4j-agent-memory v0.5.0, but using custom Cypher via AsyncGraphDatabase directly, not the library's own MemoryClient, since add_entity() has no per-user scoping and search_entities/search_facts are global unfiltered searches. Only extracted facts are ever written, never raw conversational text. An independent compliance check (a second Claude API call) reviews every extracted fact before it's written and discards anything that fails, logged as audit_reject. Fact supersession via invalid_at now covers all fact types. case_stage uses blanket supersession (new stage always replaces the old). All other types use LLM-based reconciliation: on each write, existing active facts of the same type are retrieved for the user and a small model decides whether the new fact is an update to an existing one or genuinely new. On update, the target node is marked invalid_at before the replacement is written. Fail-safe defaults to new on any uncertainty or parse failure. All five test suites pass (test_memory_smoke, test_memory_isolation, test_memory_supersession, test_memory_compliance, test_memory_reconciliation). retrieve_memory returns at most RETRIEVE_MEMORY_LIMIT (50) facts per call, newest first; if truncated, the return dict signals this and chat.py both warns to stdout and notifies the model that context is incomplete. A 12-entry family court abbreviations glossary is included in _COMPLIANCE_SYSTEM to prevent common terms (FDA, FDR, MIAM, CAFCASS, Form E, C100 etc.) from being misread as out-of-scope.

Reasoning engine: connected end to end (memory retrieval, KB retrieval, Claude API call, independent response check, memory write) but only via a CLI test harness (scripts/chat.py), explicitly not a production interface. Internal testing only, between Vilam and Claude. The system prompt has not yet been reviewed by a solicitor. A "WHERE ANSWERS ACTUALLY GO WRONG" section was added to system_prompt.md on 19 June 2026, inserted between "THE LINE THAT NEVER MOVES" and "DECODING THE OTHER SIDE". Motivated by eval_compliance.py findings: two failure patterns identified in logs — directive sequencing on urgent questions (model prescribes an ordered personal action plan rather than describing available options) and closing clauses that restate the user's specific figures or facts as the object of a solicitor-redirect assessment. The new section names both patterns explicitly with wrong/right examples. Rerun of eval_compliance.py completed 19 June 2026. Results vs baseline: custody T1 60% (was 70%), T2 0% (unchanged — no over-correction); financial T1 53% (was 75%, 1 error excluded), T2 6% (was 5% — unchanged); urgent_contact T1 35% (was 50%), T2 25% (was 45%) — clearest improvement; solicitor_advice T1 30% (was 37%), T2 55% (was 35%) — regression. The regression on solicitor T2 is a new failure mode: the model is now adding "What I'd suggest is asking your solicitor...", "it would be worth pressing them on...", and in one case validating the solicitor's specific recommendation ("This is exactly why your solicitor's view — that the proposed terms don't justify settling — matters"). The closing clause pattern (restating the user's specific situation in a solicitor redirect) has not been resolved for this scenario. Log investigation confirmed the regression is in the closing clause only; the body of the answer (general risk information) is clean in both runs. A third pattern was added to the section on 19 June 2026 (commit d5a16e4): coaching the solicitor conversation rather than naming the topic — covering both prescribing what to ask/press ("What I'd suggest is asking your solicitor...", "it would be worth pressing them on...") and validating the solicitor's existing view ("your solicitor's view matters", "that's exactly why their advice is right"). A second rerun (rerun 2) completed 19 June 2026 with the third pattern added. Solicitor T2 deteriorated further to 80% (was 55% rerun 1, 35% baseline). Log investigation confirmed the WRONG example in the pattern 3 commit (d5a16e4) was reproduced by the model almost verbatim as a closing-clause template — the model echoed "What I'd suggest is asking your solicitor..." and "it would be worth pressing them on..." from the WRONG example in its own outputs. This is now a documented project lesson: vivid WRONG examples in the system prompt risk being reproduced as templates. The model reads a WRONG example as a pattern it knows about, not as a shape it avoids. Future prompt edits in this project should be cautious about including extended wrong-example text for behavioural rules; if wrong examples are needed, keep them very short and structurally distinct from what a real response would say. The right-version example is much safer to include. Pattern 3 was rewritten (commit e706f3b): behavioural rule only, no example pair, with a self-interruption trigger ("if a sentence starts with 'ask them...', stop and rewrite"). A fourth eval is running. If solicitor T2 remains at or above 55% after this rewrite, the conclusion is to revert patterns 2 and 3 entirely and accept the compliance check as the safety layer for this scenario. Strategic note: the compliance check (response_check.py) has caught every flagged case across all runs without any model output reaching a user. This prompt work is reducing the fire rate, not replacing the check as the actual safety guarantee.

Independent response check: built. On a failed compliance check, a fixed fallback response is shown instead of the model's draft or a silent block: "I can't answer that one directly, it would mean telling you what to do in your own case, and that crosses from giving you information into giving you advice, which isn't something this can responsibly do. What I can do is explain what's actually happening at this stage, or set out the options that typically exist here without picking one for you. Tell me which of those would help, or if this feels like the kind of call a solicitor, McKenzie friend, or Citizens Advice should weigh in on, I can help you think through what to ask them." Every check, pass or fail, is logged to logs/chat_ops.jsonl with the original failing draft preserved for review, never silently discarded.

Log retention: scripts/prune_logs.py exists. LOG_RETENTION_DAYS = 90 is an explicit placeholder pending legal review, not a validated compliance figure. No file locking yet, safe only for single-developer manual runs, needs real locking before ever being scheduled against live concurrent traffic.

Plan Mode: Claude Code defaults to plan mode project-wide (.claude/settings.json). Every Claude Code prompt includes a containment question; prompts touching the memory layer, the legal information/advice boundary, or irreversible actions also include a stress-test question. Caveat: the stress-test question is still the same Claude Code session checking its own work, weaker than the independent check already built into the product, the separate compliance-check model in memory.py and response_check.py, a genuinely different model reviewing output with no visibility into the first model's reasoning. Acknowledged limitation, not solved.

Production readiness: secrets management, observability, and GDPR data architecture are met in code. Data minimisation decision log exists on Drive (Version 2, unchanged by this restructuring, still Drive-native for now). Hosting provider decision and the full legal GDPR framework remain outstanding, see regulatory boundary above.

API layer: scripts/api.py is a FastAPI wrapper around the orchestration loop, exposing POST /chat (accepts user_id, message, and optional session_id; returns the model response plus compliance pass/fail, fallback triggered flag, memory facts retrieved, and session_id) and GET /health. Calls the same functions in the same sequence as the CLI harness: memory retrieval, RAG retrieval, Claude API, compliance check, memory write. Maintains two memory layers in parallel: short-term in-process session history (last 10 turns per session_id, in-memory dict only, resets on server restart, non-durable by design for local dev) and long-term Neo4j memory via memory.py (survives restarts, unchanged). Local development only, not deployed. Run with uvicorn against the same atj-db and atj-neo4j instances as the CLI harness. Known startup issue resolved: initialise_memory() calls asyncio.run() internally, which raises RuntimeError when called from FastAPI's async lifespan context (uvicorn already has a running event loop). Fixed by wrapping the call in asyncio.to_thread() so it runs in a thread pool thread with its own event loop. memory.py is not changed.

Walking skeleton frontend: static/index.html is a minimal vanilla JS page served by FastAPI at /. Message list, text input, send button. Holds session_id in a JS variable for the page load lifetime (no persistence across reloads, matching the backend's non-persistent session store). Shows a [fallback] label when the compliance fallback fires. Proves the full loop — memory retrieval, RAG, Claude, compliance check, memory write — renders in a browser. Local dev only, not deployed.

## UI design direction (locked 19 June 2026)

Conversational first, not navigation-based. Claude surfaces visuals, timelines, checklists, and dashboards at runtime via a generative UI architecture (Claude emits structured content, a thin frontend layer renders it), rather than fixed pre-built screens. Opening experience is a warm intake conversation that builds case context and gathers documents/photos without feeling like a form. Returning users get a time and date aware, proactive experience, Claude surfaces what matters without being asked, emotionally aware through situational inference rather than stored emotional data. Document handling: Claude asks what the document is, offers understand/fill in/talk through, guides forms one step at a time. Writing support: Claude asks where the user is (not started, partial, draft to polish) and offers voice recording throughout. Case file panel is a self-building living record of documents, letters, forms, timelines, and calendar events, full memory/document integration required for pilot. Visual identity: calm, mature, minimal, Claude's own interface pushed softer, Wysa-level tonal discipline around not overstating what the AI is to the user. Token cost requirements for the pilot build: Anthropic automatic prompt caching on system and compliance check prompts, RAG retrieval capped at 3 to 7 chunks per call, explicit max_tokens on every call. Live in-court recording remains deferred pending legal opinion regardless of this scope decision, this is a legal constraint, not a sequencing choice.

## Phase 1 — walking skeleton (complete, 19 June 2026)

End-to-end loop proven working: browser → FastAPI → memory retrieval → RAG
retrieval → Claude reasoning call → independent compliance check → memory
write → response back to browser. Components built this session:

- scripts/api.py: minimal FastAPI wrapper around the existing orchestration
  in chat.py. Imports existing functions, no duplicated logic. Local dev
  only, no auth, no deployment config.
- Short-term session history, separate from long-term Neo4j memory. In-memory
  per-session store, capped at 10 turns, non-persistent across server
  restarts by design. Long-term memory retrieval/write via memory.py
  unchanged.
- static/index.html: minimal vanilla JS frontend served by FastAPI at /.
  No framework, no build step. Shows fallback indicator and session status
  line for testing visibility.
- Fixed a startup crash: initialise_memory()'s internal asyncio.run() call
  conflicted with FastAPI's running event loop. Resolved by running it via
  asyncio.to_thread().

## Compliance consistency findings (19 June 2026)

Built scripts/eval_compliance.py to test the compliance check by repeated
trial rather than single-run spot checks, after manual testing showed the
same prompt sequence producing different pass/fail outcomes across runs.
Default 20 reps per scenario (statistical reasoning for this default is in
the script's docstring).

Root cause found: the compliance check itself was working correctly in
every observed case. The failures were the model's generation habit of
appending a personalised closing clause to otherwise-clean informational
answers, either restating the user's specific figures, sequencing the
user's own next steps as a directive plan, or coaching what specific
question to ask a solicitor.

Three system prompt iterations were made to prompts/system_prompt.md
("WHERE ANSWERS ACTUALLY GO WRONG" section). Results across four borderline
test scenarios, N=20 per cell unless noted:

- custody_split_then_c100: T1 70%→65%, T2 stayed at 0% throughout (no
  over-correction).
- financial_settlement_offer: T1 stayed at 75% (an apparent improvement to
  53% in rerun 1 was a measurement artifact from an eval script bug, not a
  real effect — see below). T2 stayed at 5% throughout.
- urgent_contact_action: clearest genuine improvement. T1 50%→32%, T2
  45%→20%, both turns improved across all three iterations with no
  over-correction.
- solicitor_advice_evaluation: T1/T2 baseline 37%/35%. First two prompt
  iterations made T2 substantially worse (55%, then 80%), traced to the
  model echoing the exact sentence structure of a WRONG example we'd
  written into the prompt as a "don't do this" demonstration. Removing the
  example and replacing it with a direct behavioural rule (no illustrative
  example) brought T2 back to 40%, statistically indistinguishable from
  baseline (37%/35% vs 40%/40%, well within normal variance at N=20).

Decision: did not attempt a fourth prompt pattern. Three iterations showed
diminishing and then negative returns. This scenario is documented as a
known, accepted limitation, not a solved problem: a genuinely neutral
informational question about hearing risk vs consent order gets blocked by
the compliance check roughly one time in three, baseline and after
iteration alike. The compliance check is functioning as the real safety
net for this scenario, not the system prompt. No unsafe content has reached
a user in any test run, the cost is a false-positive fallback rate on a
legitimate question, which is a UX cost, not a safety failure. Worth
revisiting later via response_check.py tuning or improving the fallback
experience itself, not further system prompt iteration.

Lesson for future prompt edits: a vivid, quotable WRONG example in a system
prompt risks being reproduced by the model as a template, even while
correctly avoiding the specific pattern it was meant to discourage. Prefer
direct behavioural rules naming the signature of the unwanted pattern over
illustrative "don't say this" example sentences, especially for closing
or redirect language the model is likely to fall back on under pressure to
conclude an answer cleanly.

Separately fixed in scripts/eval_compliance.py: a JSONDecodeError caused by
unescaped control characters in API responses was silently excluding reps
from the denominator rather than counting them as errors. Fixed to retry
with control characters stripped, and to surface unrecoverable failures
explicitly (e.g. "1×JSONDecodeError") rather than an opaque error count.

## Build sequencing plan

Walking skeleton approach: prove the riskiest, least-precedented piece
early and in isolation, before building features on top of an unproven
foundation, rather than building every component to completion in
parallel and discovering integration problems at the end.

1. Walking skeleton (complete) — minimal API + bare frontend, full loop
   proven end to end.
2. Generative UI spike, isolated — prototype Claude emitting structured
   content (timelines, checklists, document cards) rendered by a thin
   frontend layer, against fake/static data first, before connecting it
   to live backend responses. This is the most technically demanding and
   least precedented piece, tested in isolation deliberately.
3. Wire generative UI into the real chat flow, once the spike works.
4. Case file panel — living record fed by real memory and document
   storage, not mocked. Built after the chat loop is solid since it's a
   second UI surface drawing on the same underlying state.
5. Document handling and writing support workflows (upload, ask-what-it-is
   flow, three writing-support paths).
6. Voice recording on mobile, reliable from day one per the locked UI
   direction, additive to phase 5.
7. Baseline interaction polish: streaming, stop button, typing indicators,
   trust signals, searchable history.

Phase 2 complete (19 June 2026). See below.

## Phase 2 — generative UI spike (complete, 19 June 2026)

Two new files added, isolated from the rest of the build:

**static/ui_spike.html** — standalone static page, no framework, no build
step, no backend calls. Renders two hardcoded fixture objects on load:

- Timeline fixture: "Your divorce — where things stand", 6 stages using the
  divorce track (filed/acknowledged/20-week period/conditional order/6-week
  wait/final order). Two stages complete (green dot), one current (blue dot
  with glow, bold label), three upcoming (hollow gray dot). Gray vertical
  connector lines between stages.
- Checklist fixture: "Before your FDR hearing", 6 items. Two checked/done
  (strikethrough, muted text), four unchecked with normal-weight labels and
  gray description text below each.

Styling: warm off-white background, white cards, system sans-serif font.
Calm and minimal per the locked UI direction. Spike label at top identifies
this as dev-only.

**scripts/generative_ui_spike.py** — standalone script, not connected to
chat.py, api.py, memory.py, or retrieve.py. Defines two tools
(render_timeline and render_checklist) with the same schemas as the HTML
fixtures. Sends 5 varied prompts to claude-sonnet-4-6 with
tool_choice={"type": "any"} and prints the raw tool_use block for each.

Schema used by both tools — render_timeline:
  { "title": string, "stages": [{ "id", "label",
    "status": "upcoming"|"current"|"complete",
    "description"?, "date"? }] }

Schema used by both tools — render_checklist:
  { "title": string, "items": [{ "id", "label", "done": boolean,
    "description"? }] }

5-prompt run results (19 June 2026):

1. "What happens after I file for divorce?"
   → render_timeline, 8 stages, all required fields present. ✓

2. "What do I need to do before my financial dispute resolution hearing?"
   → render_checklist, 12 items, all required fields present. ✓

3. "Can you show me the financial remedy track from the very start?"
   → render_timeline, 8 stages, all required fields present. ✓

4. "What are the steps involved in a C100 child arrangements application?"
   → render_timeline, 9 stages, all required fields present. ✓

5. "What documents do I need to bring to my First Appointment?"
   → render_checklist, 10 items, all required fields present. ✓

5/5 prompts produced fully schema-valid output. All responses returned
stop_reason: tool_use.

Correction to first-run finding: the initial run showed prompt 3
returning only {"title": "..."} with no stages array, initially diagnosed
as a MAX_TOKENS truncation. A second run (adding stop_reason visibility to
the script) disproved this: all 5 responses returned stop_reason: tool_use,
not max_tokens. The required fields were already correctly specified in the
schema (unchanged between runs). The first run's failure on prompt 3 was
model variance — a single non-representative sample. The script was updated
to print stop_reason alongside every tool_use block, making future
regressions of this kind immediately distinguishable from token limit issues.

Validation, retry, and fallback detection added to generative_ui_spike.py
(20 June 2026). Content-level validation checks that title is non-empty
and stages/items is a non-empty list — not just schema shape. Retry-once
logic: on validation failure, the same prompt is resent once; if that
also fails, the call is marked as a fallback. This mirrors the
retry-then-fallback pattern in response_check.py, which retries a
compliance check failure once before serving the fixed fallback response.

20-call batch results (5 prompts × 4 reps, 20 June 2026):
  Total calls (first attempts) : 20
  Passed first attempt         : 20/20 (100%)
  Needed retry                 : 0/20 (0%)
  Fallback after retry         : 0/20 (0%)

All 5 prompts clean across all 4 reps. 0 retries fired, 0 fallbacks.
The one anomalous response from the original single-shot run (prompt 3,
stages missing) was isolated variance — not reproduced across 20 calls.

Conclusion: Claude reliably produces the correct tool and correct schema
shape. The spike has proven the rendering logic (static/ui_spike.html)
and the tool-use schema compliance (generative_ui_spike.py) independently,
as intended. Validation and retry logic is in place for when wiring into
the live chat flow introduces real-world variance.

Next step: Phase 3 — wire generative UI into the real chat flow.

## Claude Code prompt rule, standing (three tiers)

1. Containment question on every prompt, tailored to the specific change
   ("confirm this only touches X and nothing else"). Baseline for all
   routine work.
2. Stress-test question (argue against the plan before running it) added
   only when the prompt touches the memory layer, the legal information
   vs advice boundary, or anything irreversible. Caveat: this is still the
   same Claude Code session checking its own work, weaker than the
   project's actual independent check (response_check.py, a genuinely
   separate model with no visibility into the first model's reasoning).
3. Every prompt producing runnable code ends with an instruction to
   actually run it and paste real output before reporting a commit ready,
   not just describe the diff. This is functional self-verification, not
   judgment self-review, so it doesn't carry the same weakness as the
   stress-test question.

Starting now (compliance testing cycle complete as of this commit): Claude
in claude.ai reads the actual changed files in full on each commit, not
just diffs, as an independent code-quality check, separate from anything
Claude Code reports about its own work. Same separation-of-concerns logic
as response_check.py being a different model from the generator.

AI-specific requirements adopted as standing practice (from an external
best-practices document reviewed 19 June 2026, AI-specific items only, not
the full process framework): explicit failure handling required for model
timeouts and malformed/unparseable outputs (proven necessary by the
eval_compliance.py JSONDecodeError bug), prompts versioned via git
(already true for system_prompt.md via commit history, now explicit),
audit trail for AI actions (already satisfied by chat_ops.jsonl logging
every check pass/fail). The full 7-phase analyse/design/approval/implement/
test/self-review/verify cycle was reviewed and explicitly not adopted as a
blanket requirement, judged too heavy for this build stage; heavier process
already applies only where the containment/stress-test tiers call for it.

## Open items / next steps

Continue discovery, priority is finding someone with zero legal representation throughout.

Run the next discovery conversation; any financial remedy participant must be asked specifically about their Form E experience on MyHMCTS.

Follow up with Support Through Court (Charlotte Rook contacted, response pending, escalation contact is Emma Taylor, CEO).

Outreach in progress across multiple channels, current status tracked in Airtable (base appqkREbZXUDLBlZ5, Channels table), not duplicated here since Airtable is the system of record.

Send prompts/system_prompt.md to whoever is lined up for the solicitor consultation when Vilam decides to action it, this is the priority artefact for that review, not a general discussion of the product concept.

Map the MyHMCTS Form E journey, required before the Form E Layer 2 entry can be written.

Second terminology pass, deferred until discovery informs what gaps matter most.

Full legal GDPR compliance framework, instruct a solicitor, running in parallel with build.

Log review process: scripts/review_logs.py exists and surfaces fallbacks and audit_rejects in a plain-English summary (run with --days N, default 7). Must be run manually before any pilot participant session to confirm no unexpected blocking behaviour. No automated alerting yet.

Compliance consistency eval: scripts/eval_compliance.py tests how consistently the compliance check behaves across deliberate borderline scenarios by repeated trial (default 20 reps per scenario, configurable via --reps). Four scenarios: custody split recommendation, financial settlement offer, urgent child contact action, and solicitor advice evaluation. Each is a two-turn conversation. Reports per-turn fallback rate across reps; flags any turn exceeding the FAIL_RATE_THRESHOLD (20%). N=20 is a development smoke test — a clean result does not certify safety (detecting a 5% failure rate with 80% power requires ~200 reps; see module docstring). Not yet run; pending Phase 1 browser test sign-off.

Reconciliation gap — same-turn duplicates: _reconcile_facts only compares new facts against what is already in Neo4j. If two facts about the same evolving thing arrive in the same conversational turn, neither will supersede the other. Narrow edge case, acceptable for now, revisit if it surfaces in real sessions.

Monitor NAMS (Neo4j Agent Memory Service) for UK/EU region availability, would simplify self-hosting if it arrives.

Decide whether to build a cheap, narrow paid guide as a pre-launch validation and audience-building test, flagged, not decided.

Drive cleanup: now that this file and project_log.md are canonical, the old Drive-native brief revisions, the Technical Environment doc, and old handover docs in the ATJ parent folder are obsolete. Vilam's call on deleting versus archiving them.

Decision Log (data minimisation) review: still Drive-native, the same repo-file pattern used here could apply to it too, not yet actioned.

UI build is scoped for full pilot, not phased. Following discussion on 19 June 2026, the decision was made to build the full UI vision into the pilot directly: generative UI rendering layer, fully integrated case file panel (memory and document storage, not mocked), reliable mobile voice recording, and all document/writing workflows. No 'later phase' exists for these components. Estimated 250 to 400 hours of Claude Code execution and review, realistically months of calendar time. Risk accepted: more assumptions built before first real user contact than a minimal pilot would carry. Flagged before the decision was made; decision stands unless the build stalls or a specific component proves significantly harder than estimated.

## File locations

Repo: https://github.com/veeyastudio-wq/atj-knowledge-base. Local path on Vilam's Mac: /Users/admin/Library/CloudStorage/GoogleDrive-veeya.studio@gmail.com/My Drive/Claude Workspace/Access to Justice/KB.

Google Drive ATJ parent folder: 18p6KDaCEV-LQ20jD1JMgRtp-J-0kOD7t. Data Minimisation Decision Log (Version 2) lives here, still Drive-native: 1xr5tUcfL0XCiPNo7P_XWt4JpTk9dK4nT.

Airtable base: appqkREbZXUDLBlZ5. Channels tbl4x8lOYPQ4xJqSu, Respondents tblOoOHP124QDgGGe, Conversations tblFFVtLqYO2NHVJy, Insights tblpuU2UbQFm9qsbK, Reference tblxeuTwAjXdaoHUP.

Local infrastructure: atj-db (pgvector/pg16, port 5432, RAG only), atj-neo4j (Neo4j 5.26 community, memory layer only). Both must be running before relevant scripts. Credentials live in .env only.
