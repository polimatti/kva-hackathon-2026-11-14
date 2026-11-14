Track: Anonymising data — Velo, pseudonimi che la memoria capisce.

**Problem.** Before company documents (maintenance tickets, supplier e-mails, incident reports) reach an AI memory, personal data must go. Type redaction ([PERSONA]) keeps privacy but kills the memory: on our corpus, distinct injured workers drop from 27 to 1 [verified: check set].

**What we build.** Identity-preserving pseudonymisation: every person keeps one stable pseudonym across documents ("Ing. Rossi", "M. Rossi", mario.rossi@… → PERSONA-07), mapping kept apart.

**Riskiest assumption.** Rules + coreference catch names on messy real text. Frozen test today: structured PII 100%, hard names 51% [verified: frozen test run 1].

**Kill criterion (ex-ante).** Person recall < 0.98 on a new frozen test after our fixes, or linkage F1 not ≥ 0.5 above redaction → the angle is not real.

**Team and roles.** Mattia Morgut: operator, business owner, presenter. Claude Code (Claude Opus 5.5): builder and researcher.

**Plan.** 10:30–12:15 rule fixes on dev set + new frozen test · 12:30 video + abstract · 14:00 first pitch · afternoon: model pass on residual names via AI Gateway, measured on the same frozen test · 16:00 feature freeze.

Repo: https://github.com/polimatti/kva-hackathon-2026-11-14
