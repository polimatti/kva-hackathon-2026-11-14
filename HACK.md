# HACK.md — Pseudonimi che la memoria capisce

> Single source of truth for the day. Markers: `[verified: source]` · `[declared]` · `[unverified]`.
> An empty section says `MISSING — needed before <phase>`.

Team: Mattia Morgut (operator, business owner, presenter) · Builder: Claude Code (Claude Opus 5.5) · Researcher: Claude Code
Clock: pitch delivery 16:45, show-off 17:05 · Credits left: $25 team key, not yet used · Track: **5 · Anonymising data**
Official rubric: SKILL.md §2a — track weights: G1 Fit 25 · Right-to-win 30 · Explainability 20 · Invest 15 · Sentiment 10

## Selection criteria (written before the ideas)
1. A two-person team (one human + one agent) can show it end to end today, with data we create ourselves.
2. Its result can be checked deterministically (ground truth known), so "Demo or reality" (18 pts) is real.
3. The track is not crowded at choice time (all tracks had 0 teams at 09:45 [verified: dashboard]).

## Shortlist and gate
| Idea | Potential | Readiness | Flags | Verdict |
|------|-----------|-----------|-------|---------|
| Identity-preserving pseudonymiser for company memory (track 5) | 55 | 76 | median_idea | TOY |
| Decision black box for an industrial agent (blackbox-agents) | not scored | — | — | backup |
| Memory inspector for people (3b) | not scored | — | — | dropped: lower tech weight, needs UI polish |

Chosen: the pseudonymiser — highest readiness and a deterministic check set. Override of the TOY verdict by the
team (Mattia, 10:10): the cap comes from P5 = 1 (no domain access), which every idea of this team shares.
Recovery move: one real conversation with a person who feeds company documents to a model (mentor call or a DPO)
before 12:30, logged in the evidence log.

## The 8hack canvas

### Q1 · Problem
The person who wants to put company documents (maintenance tickets, supplier e-mails, incident reports) into an AI
memory or a model must remove personal data first (GDPR; EDPB Guidelines 01/2025 on pseudonymisation
[verified: edpb.europa.eu]). Today they redact with type tags ("[PERSON]") or skip the project; redaction destroys
who-did-what, so the memory can no longer answer the questions it was built for [verified: our check set, see Q6].

### Q2 · Focus
We focus on the step "documents → memory ingestion" for Italian manufacturing SMEs' operational text
(tickets, supplier mail, incident reports, shift chats). We explicitly ignore: images, audio, structured DB exports,
re-identification attacks on quasi-identifiers beyond the listed types.

### Q3 · UVP to test
For the IT/quality lead of an Italian manufacturer who wants an AI memory over operational documents, our step
removes personal data **and keeps every person as the same stable pseudonym across documents** — unlike type
redaction (Presidio defaults, regex scripts) — because it resolves "Ing. Rossi", "M. Rossi", "Rossi", "Mario"
and mario.rossi@… to one identity before replacing them.
Hypothesis: we believe such a lead will rank "the memory still answers who-did-what" as a blocker for approving
an anonymised memory, because redacted corpora lose that.
Test today: ask 1 mentor + any participant with company-data experience; check set below for the technical half.
Kill criterion (ex-ante): privacy recall < 0.98 on the held-out set, or linkage F1 not above redaction by ≥ 0.5 →
the angle is not real. Market half: 0 of the people we ask name cross-document identity as a need → narrow to a
plain Italian-pattern redactor.
Result: technical half PASS on the in-distribution set (see Q6); held-out set and market half pending.

### Q4 · USPs
1. Redaction breaks memory → stable pseudonyms per identity → the memory still answers "who opened most tickets"
   · proof: QA1 Rand 1.000 vs 0.047 for redaction · vs Presidio default operators · angle: proof
2. Name variants leak or split → document-level then corpus-level coreference → one person = one token ·
   proof: linkage B-cubed F1 0.884 vs 0.062 · vs regex scripts · angle: mechanism
3. "Is it safe?" → every run prints privacy recall/precision per type against ground truth · proof: check set ·
   vs vendor claims without numbers · angle: objection
4. Italian industrial patterns (codice fiscale, IBAN IT, targhe, matricole, indirizzi) [unverified on real data]

### Q5 · Single points of failure
| # | Component | How it fails | L/M/H | Impact | Mitigation | Owner | By |
|---|-----------|--------------|-------|--------|------------|-------|----|
| D1 | Detector tuned on our own synthetic data | scores look perfect, jury distrusts | H | demo | held-out set with new templates, report honestly | Claude | 12:00 |
| D2 | MCP login / Control8 | cannot publish start/video/pitch | M | demo | /hackathon/live and /me as manual fallback | Mattia | 10:30 |
| D3 | One laptop, one human | crash or absence | M | demo | push every milestone; static HTML report opens offline | Claude | always |
| D4 | Video ≤ 50 s by 12:30 | not recorded | M | gate 1 | script + slides generated, Mattia records voice | both | 12:15 |
| V1 | Riskiest assumption: buyers need identity linkage, not just redaction | false | M | thesis | kill criterion above | Mattia | 12:30 |
| V2 | Rule-based detection on real messy text | recall drops | H | thesis | optional LLM pass on residuals via AI Gateway; measured separately | Claude | Phase II |

### Q6 · First things to build
| # | Build | Proves | Done when | Time box | Status |
|---|-------|--------|-----------|----------|--------|
| 1 | Walking skeleton: generator → pseudonymiser → check set | flow runs end to end | `python eval/evaluate.py` prints the table | 30 min | done 10:04 |
| 2 | Riskiest piece: coreference across name variants | linkage survives | linkage F1 ≥ 0.85 | 30 min | done: 0.884 |
| 3 | Held-out check set (new templates, unseen names) | not overfitted | recall reported per type | 45 min | todo |
| 4 | "Now possible": same memory question on redacted vs pseudonymised corpus | the contrast | runs 3× in a row | 30 min | metrics done, demo page todo |
| 5 | Fallbacks: static HTML report, recorded run | demo with wifi off | report opens offline | 20 min | todo |

Cut list: LLM pass (Phase II only), web UI with upload, re-identification risk scoring, non-Italian languages.

### Q7 · Target audience
Segment: IT / quality leads in Italian manufacturing SMEs starting an AI memory or RAG project (early adopter:
they already have the documents and a GDPR officer saying no) · Bottom-up size: MISSING — needed before 16:30
Persona — who: head of IT or quality, 50–250 staff company · job: get approval to index operational documents ·
trigger: DPO blocks the RAG pilot · where: Confindustria Piemonte events, KVA network · objection: "is it really
anonymous?"
Buyer vs user: buyer = IT/quality lead with DPO sign-off; user = the ingestion pipeline (and the people querying).
Where we reach ten of them next week: MISSING — needed before 16:30.

### Q8 · Moat technologies
| Technology | Commodity / differentiator | Today (in the demo) | Target (hard to copy) | Measured by | Horizon |
|------------|----------------------------|---------------------|-----------------------|-------------|---------|
| PII pattern detection | commodity | Italian regex pack | — | recall by type | — |
| Identity resolution across documents | differentiator | rules + doc/corpus coreference | learned from human corrections per company | linkage F1 on check set | 3 months |
| Utility-aware evaluation | differentiator | QA questions + utility tokens | per-customer check sets built from their own memory queries | QA agreement | 3 months |
Copy test: a strong team can copy today's rules in a weekend. What they would not have: per-company correction
history and the check sets. Today the moat is a plan, not a fact.

## Landscape (as of 14/11/2026)
- Microsoft Presidio: open source; consistent pseudonyms need a custom operator and a mapping you keep yourself;
  no cross-document coreference out of the box [verified: microsoft.github.io/presidio pseudonymization sample].
- Private AI: commercial redaction before RAG/prompting; Italian listed among languages [verified: private-ai.com].
- Skyflow: vault tokens for PII during RAG ingestion and inference [verified: aws.amazon.com APN blog].
- Protecto, Tonic: masking/unmasking for LLM pipelines [verified: search results, details not checked].
- Native-feature check: frontier assistants do not anonymise customer corpora before ingestion [unverified].
- EDPB Guidelines 01/2025: pseudonymised data is still personal data; the mapping must be kept separate
  [verified: edpb.europa.eu, summaries by Hunton, IAPP].

## Evidence log
| When | Who (role, real or proxy) | Verbatim quote or observation | Assumption: confirmed / refuted / unclear |
|------|---------------------------|-------------------------------|-------------------------------------------|

## Verification log
| When | What an agent produced | What a human checked, and how | What the agent got wrong, and how we caught it |
|------|------------------------|-------------------------------|------------------------------------------------|
| 10:00 | pseudonymiser v1, linkage F1 0.755 | diagnostic script listing split/merged identities | surname-only mentions not linked to the full name in the same doc; e-mail names not indexed → fixed, F1 0.884 |
| 10:00 | privacy recall 1.000 | — | suspicious: detector and data written by the same agent → held-out set (Q6 #3) |

## Checkpoints
- 1st: MISSING — after 12:30
- 2nd (feature freeze): MISSING — 16:00

## Pitch
MISSING — needed before 14:00

## Next week
MISSING — needed after 18:30
