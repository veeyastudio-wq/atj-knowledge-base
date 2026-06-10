# Access to Justice — Knowledge Base Source Map
*Created: 10 June 2026*

---

## Purpose

This document maps the six categories of content required for the ATJ knowledge base, with authoritative sources, access status, format, and maintenance notes for each. It is a working reference for the build phase — not a final architecture document.

---

## Category 1 — Procedural rules and legislation

The foundation. Everything else in the knowledge base sits on top of this.

### Content required
- Family Procedure Rules 2010 (all 36 parts)
- Practice Directions supplementing the FPR
- Pre-Action Protocols
- Key underlying statutes: Children Act 1989, Matrimonial Causes Act 1973, Family Law Act 1996

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| Family Procedure Rules 2010 (full text) | legislation.gov.uk/uksi/2010/2955 | Free | Structured HTML / PDF |
| Practice Directions | justice.gov.uk/courts/procedure-rules/family | Free | HTML |
| Children Act 1989 | legislation.gov.uk/ukpga/1989/41 | Free | Structured HTML |
| Matrimonial Causes Act 1973 | legislation.gov.uk/ukpga/1973/18 | Free | Structured HTML |
| Family Law Act 1996 | legislation.gov.uk/ukpga/1996/27 | Free | Structured HTML |
| The Red Book (annotated practitioner reference) | lexisweb.co.uk | Paid — LexisNexis subscription | N/A |

### Maintenance note
legislation.gov.uk may lag behind the most recent amendments. The FPR is updated multiple times per year via Practice Direction updates. The knowledge base requires a process to catch changes — this cannot be a one-time import.

### The Red Book
The most complete annotated version of the FPR used by practising lawyers. Behind a paywall. Relevant at build stage when assessing whether a licensing arrangement is viable or necessary.

---

## Category 2 — Court forms

Every form a litigant in person may need to complete or receive, with plain English explanation of purpose and context.

### Content required
- D series: divorce and dissolution forms
- C series: Children Act forms (C1, C2, C100 and others)
- A series and financial remedy forms: Form A, Form E, Form E1 and supporting forms
- Adoption forms (lower priority for v1)

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| HMCTS form finder | hmctsformfinder.justice.gov.uk | Free | PDF |
| GOV.UK family forms index | gov.uk/guidance/family-procedure-rules-forms | Free | PDF |

### Maintenance note
Forms are updated regularly with version date codes (e.g. Form A updated April 2025). The knowledge base must track form versions. Outdated form guidance is a direct risk to users — following instructions for a superseded form can delay or damage a case.

### Important
Forms alone are insufficient. Each form entry in the knowledge base must be paired with contextual explanation: what the form is for, when it is triggered, what happens after it is filed, and what common mistakes look like. This is where the product adds value beyond what GOV.UK provides.

---

## Category 3 — GOV.UK procedural guidance and judiciary guidance for litigants in person

Step-by-step guidance for each main pathway through the system, plus dedicated resources published specifically for unrepresented parties.

### Content required
- GOV.UK step-by-step guides: divorce, financial remedy, child arrangements
- Judiciary litigants in person guidance pages
- Key Practice Directions in plain English context: PD12B (Child Arrangements Programme), PD12J (domestic abuse), PD22A (evidence), PD27A (court bundles)
- Guide for litigants in person on preparing court bundles (March 2026, President of Family Division)
- Advicenow guides: applying for a financial order without a lawyer; getting a divorce without a lawyer
- Family Justice Council guide: Sorting out Finances on Divorce

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| GOV.UK divorce guide | gov.uk/divorce | Free | HTML |
| GOV.UK financial remedy guide | gov.uk/money-property-when-relationship-ends | Free | HTML |
| GOV.UK child arrangements guide | gov.uk/looking-after-children-divorce | Free | HTML |
| Judiciary litigants in person page | judiciary.uk/related-offices-and-bodies/advisory-bodies/family-justice-council/litigants-in-person-in-the-family-justice-system | Free | HTML |
| Court bundles guide for litigants in person | judiciary.uk (March 2026) | Free | PDF |
| Advicenow guides | advicenow.org.uk | Free | HTML / PDF |
| Family Justice Council — Sorting out Finances on Divorce | judiciary.uk | Free | PDF |

### Maintenance note
GOV.UK guides are updated when policy or procedure changes. The court bundles guide (March 2026) supersedes all previous bundle guidance — earlier versions must not remain in the knowledge base. Version control is critical here.

---

## Category 4 — Hearing types and what happens in each

What each hearing is for, what the court expects, what a litigant in person can and cannot do, and what the possible outcomes are.

### Content required

**Children proceedings track**
- FHDRA (First Hearing Dispute Resolution Appointment)
- Dispute Resolution Appointment
- Fact-finding hearing
- Final hearing

**Financial remedy track**
- First Appointment (FDA)
- Financial Dispute Resolution hearing (FDR)
- Final hearing

**Across both tracks**
- Directions hearings
- Without notice / urgent applications
- Consent order hearings
- Appeals

For each hearing type: purpose, who attends, what documents are required beforehand, what the litigant in person can say, what the possible outcomes are, and what happens immediately after.

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| Practice Direction 12B (Child Arrangements Programme) | justice.gov.uk/courts/procedure-rules/family/practice_directions/pd_part_12b | Free | HTML |
| Financial Remedies Guide 2026 | judiciary.uk/wp-content/uploads/2026/03/FRC-Guide-Final-Clean.pdf | Free | PDF |
| Childlaw Advice — hearings guide | childlawadvice.org.uk/information-pages/hearings-in-the-family-court | Free | HTML |

### Important
Official sources describe what hearings are. They do not describe what it feels like to be in one without a lawyer, or what an unrepresented party typically gets wrong. That layer — the experiential reality — will come from research conversations and must be treated as a distinct content type within the knowledge base.

---

## Category 5 — Standard court orders and correspondence

The documents the court produces, what they mean, what obligations they create, and what happens if they are not complied with.

### Content required

**Children orders**
- Child Arrangements Order
- Prohibited Steps Order
- Specific Issue Order
- Consent Order
- Interim orders
- Section 91(14) orders (barring further applications)

**Financial orders**
- Financial remedy order (clean break)
- Periodical payments order
- Property adjustment order
- Pension sharing order
- Maintenance pending suit

**Directions orders and correspondence**
- Standard directions orders at each stage
- Penal notices and enforcement notices
- HMCTS administrative correspondence (notice of hearing, requests to file documents)

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| Judiciary — Compendium of Standard Orders | judiciary.uk/guidance-and-resources/practice-guidance-standard-children-and-other-orders | Free | PDF |
| Order 7.7 — litigants in person summary order | (within above compendium) | Free | PDF |
| Financial Remedies Guide 2026 | judiciary.uk/wp-content/uploads/2026/03/FRC-Guide-Final-Clean.pdf | Free | PDF |

### Important
The Compendium of Standard Orders is an authoritative and underused resource. It includes templates specifically designed for litigants in person. It should be a primary source for this category.

The explanatory layer — what orders mean and what they require — is as important as the orders themselves. An order containing a penal notice has serious consequences. An unrepresented party must understand this clearly and immediately.

---

## Category 6 — Supporting context

The surrounding system: organisations, processes, and entitlements that affect a case but sit outside court procedure itself.

### Content required
- CAFCASS: role, when involved, what to expect from safeguarding interviews, how to engage
- MIAM: what it is, when required, exemptions, cost, mediation voucher scheme (up to £500)
- McKenzie friends: rights, limitations, how to use one, unregulated status and risks
- Legal aid: current eligibility criteria, domestic abuse gateway, how to apply, Legal Aid Agency contact

### Sources

| Source | URL | Access | Format |
|---|---|---|---|
| CAFCASS — official guidance | cafcass.gov.uk | Free | HTML |
| CAFCASS Cymru | gov.wales/cafcass-cymru | Free | HTML |
| MIAM guidance — GOV.UK | gov.uk/family-mediation-voucher-scheme | Free | HTML |
| Family Mediation Council | familymediationcouncil.org.uk | Free | HTML |
| Judiciary — McKenzie friends guidance | judiciary.gov.uk | Free | PDF |
| Legal Aid Agency — eligibility | gov.uk/check-legal-aid | Free | HTML |

### Maintenance note
Legal aid eligibility criteria and the mediation voucher scheme are subject to policy change. CAFCASS processes were updated in 2025. These sources require active monitoring — getting them wrong directly harms users.

---

## Summary

| Category | Sources | Access | Priority |
|---|---|---|---|
| 1 — Procedural rules and legislation | legislation.gov.uk, justice.gov.uk | Free (Red Book: paid) | Foundation — highest |
| 2 — Court forms | HMCTS form finder, GOV.UK | Free | High |
| 3 — GOV.UK and judiciary guidance | GOV.UK, judiciary.gov.uk, Advicenow | Free | High |
| 4 — Hearing types | PD12B, Financial Remedies Guide 2026 | Free | High |
| 5 — Standard orders and correspondence | Judiciary compendium, Financial Remedies Guide | Free | High |
| 6 — Supporting context | CAFCASS, FMC, Legal Aid Agency, judiciary | Free | Medium |

All primary sources are publicly accessible and free. No licensing is required to begin building the knowledge base. The Red Book is the only paid resource identified and is optional — relevant at build stage if deeper annotation is needed.

---

## What this document does not cover

- How the knowledge base is structured for RAG retrieval (chunking strategy, metadata tagging, embedding model)
- The experiential layer: what research conversations will add that official sources cannot provide
- The tacit lawyer knowledge layer: published judgments, judicial guidance on how courts approach key decisions — to be scoped separately
- Maintenance process design: how updates to sources are tracked and applied
- Data architecture and GDPR considerations

These are build-phase decisions. This document is discovery and pre-build orientation only.
