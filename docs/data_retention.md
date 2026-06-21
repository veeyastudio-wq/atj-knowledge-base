# ATJ — Data Retention Policy (provisional, pending solicitor review)

Status: provisional. Same pattern as LOG_RETENTION_DAYS in prune_logs.py,
a working placeholder, not a validated compliance position. Must be
confirmed by the solicitor consultation on the GDPR compliance framework
before going live with real user data.

## What is retained

- Extracted case facts (memory layer, Neo4j): kept for the life of the
  active case.
- Transcribed text from uploaded documents and photos: kept for the life
  of the active case. The original photo or document file is never
  stored, only the transcribed text (already decided, see
  docs/pilot_scope.md, Document handling).
- Conversation history: kept for the life of the active case, to support
  searchable history and the case file panel.
- Compliance logs (chat_ops.jsonl): governed separately, unchanged,
  LOG_RETENTION_DAYS = 90 days as before.

## How long

- Active case: no fixed cap while the user is actively engaging.
- Inactivity: if an account has no activity for 24 months, the user is
  notified and given 30 days to respond before case data (facts,
  transcribed documents, conversation history) is deleted. The account
  itself can remain.
- User-initiated deletion: a user can request full deletion of their
  case data at any time. Action is immediate and irreversible once
  confirmed.

## Access

- Only the user can access their own case data. No cross-user access.
  No staff access to individual case content outside of debugging with
  explicit justification logged.

## Legal basis

- To be confirmed by solicitor. Working assumption: legitimate interest
  or contract necessity for delivering the service, special category
  data under Article 9 handled via explicit consent at account creation,
  consistent with the existing memory layer architecture decision (see
  docs/project_state.md).

## Why this shape

Tying retention to the life of the case rather than a fixed short window
respects the product's actual purpose, a 90-day cap as used for
compliance logs would break the case file panel and persistent memory
for any real proceeding. Indefinite retention with no end point doesn't
satisfy storage limitation, so an inactivity trigger and an
unconditional user deletion right both exist as bounds.
