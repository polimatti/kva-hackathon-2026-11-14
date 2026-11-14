"""Dual Feedback Loop: verification gate + consistency audit + auto-remediation + forensic certificate.

Loop 1 — Forward Verification Gate (enhanced, privacy-driven)
    Two-layer re-scan of the OUTPUT:
    Layer A: Structured PII patterns (email, IBAN, tax code, phone, address, plate, employee ID).
    Layer B: Vault-driven check — every original value in the vault is searched in the output.
             This catches names, addresses, and any PII that the pattern layer would miss.
    Any match that is not one of our own tokens is a leak.

Loop 1b — Auto-Remediation
    When Layer B finds a surviving original value, it patches the output automatically by
    replacing the leaked value with its corresponding token from the vault (reverse lookup).
    The remediation is logged and the certificate records both the leak and the patch.

Loop 2 — Retro-Feedback Consistency Audit
    After corpus-level processing, walk every span and check:
      - No identity splits (same key mapped to multiple tokens)
      - No identity merges (same token used for multiple keys)
      - Cross-file coherence (if text and tables share a person, they share a token)
    Splits and merges degrade the memory's ability to link facts.

Loop 3 — Per-Document Privacy Report
    For each document, produce a privacy summary: how many spans were replaced,
    by type, the verification status, and a risk score (0-100).

Output — Compliance Certificate
    A JSON document that travels with the batch: batch ID, timestamps, GDPR basis,
    gate verdicts, remediation log, statistics, and a final status.
"""
import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone

_CAP = r"[A-ZÀ-Ý][a-zà-ÿ']+"
_VERIFY_PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("IBAN", re.compile(r"\bIT(?:\s?[0-9A-Z]){25}\b")),
    ("TAX_CODE", re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("EMPLOYEE_ID", re.compile(r"\bMAT-\d{5}\b")),
    ("PLATE", re.compile(r"\b[A-Z]{2}\d{3}[A-Z]{2}\b")),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+39\s?)?(?:3\d{2}[\s-]?\d{3}\s?\d{3,4}|0\d{1,3}[\s/]\d{3}\s\d{4})(?![\w-])")),
    ("ADDRESS", re.compile(r"\b(?:Via|Viale|Corso|Piazza|Strada|Largo)\s[^\n,]{2,45}?\s\d{1,4}[A-Z]?,\s\d{5}\s" + _CAP)),
]

_OUR_TOKEN = re.compile(r"\[(PERSONA|EMAIL PERSONA|TEL|IBAN|CF|MATRICOLA|TARGA|INDIRIZZO)-\d{2}\]")


def _is_inside_token(text, start, end):
    """Check if a match position is inside one of our own tokens."""
    # Search backward for [ and forward for ]
    ctx_start = max(0, start - 20)
    ctx_end = min(len(text), end + 20)
    ctx = text[ctx_start:ctx_end]
    # Find all our tokens in the context
    for m in _OUR_TOKEN.finditer(ctx):
        tok_start = ctx_start + m.start()
        tok_end = ctx_start + m.end()
        if tok_start <= start and tok_end >= end:
            return True
    return False


def verify_clean(anonymised_texts, vault=None):
    """Loop 1: re-scan pseudonymised output for residual PII.

    Layer A: structured pattern scan.
    Layer B (if vault provided): vault-driven scan — check that no original value survives.

    Returns (all_leaks, remediation_map):
      all_leaks: list (one per text) of leak dicts {type, start, end, surface, layer}
      remediation_map: dict {original_value: token} for auto-patching (Layer B only)
    """
    all_leaks = []
    remediation_map = {}

    # Build reverse vault: original_value -> token (for Layer B)
    if vault:
        for token, originals in vault.items():
            if isinstance(originals, list):
                for orig in originals:
                    if len(orig) >= 3:  # skip very short values to avoid false matches
                        remediation_map[orig] = token

    for text in anonymised_texts:
        leaks = []

        # Layer A: structured patterns
        for typ, rx in _VERIFY_PATTERNS:
            for m in rx.finditer(text):
                if _is_inside_token(text, m.start(), m.end()):
                    continue
                leaks.append({
                    "type": typ, "start": m.start(), "end": m.end(),
                    "surface": m.group(), "layer": "A_pattern",
                })

        # Layer B: vault-driven — search for any original value in the output
        if vault:
            for orig, token in remediation_map.items():
                # Case-sensitive search for the original value
                idx = 0
                while True:
                    pos = text.find(orig, idx)
                    if pos == -1:
                        break
                    # Make sure it's not inside a token
                    if not _is_inside_token(text, pos, pos + len(orig)):
                        leaks.append({
                            "type": "VAULT_LEAK", "start": pos, "end": pos + len(orig),
                            "surface": orig, "layer": "B_vault",
                            "remediation_token": token,
                        })
                    idx = pos + 1

        all_leaks.append(leaks)

    return all_leaks, remediation_map


def auto_remediate(anonymised_texts, all_leaks):
    """Loop 1b: auto-patch surviving original values found by Layer B.

    Returns (patched_texts, remediation_log).
    Only patches B_vault leaks (which have a known token). A_pattern leaks are flagged but
    not auto-patched (they need manual review — the token is unknown).
    """
    patched_texts = []
    remediation_log = []

    for text, leaks in zip(anonymised_texts, all_leaks):
        # Sort vault leaks by position (reverse order for safe replacement)
        vault_leaks = sorted(
            [lk for lk in leaks if lk["layer"] == "B_vault"],
            key=lambda lk: lk["start"],
            reverse=True,
        )
        patched = text
        for lk in vault_leaks:
            token = lk.get("remediation_token", "[REDACTED]")
            patched = patched[:lk["start"]] + token + patched[lk["end"]:]
            remediation_log.append({
                "original": lk["surface"],
                "replaced_with": token,
                "position": lk["start"],
                "auto_patched": True,
            })
        patched_texts.append(patched)

    return patched_texts, remediation_log


def audit_consistency(spans_per_doc):
    """Loop 2: retro-feedback consistency audit.

    Checks identity coherence across the full corpus:
    - splits: same identity key -> multiple tokens (fragments a person)
    - merges: same token -> multiple identity keys (conflates people)

    Returns dict with splits, merges, scores, and a boolean `consistent`.
    """
    key_to_tokens = defaultdict(set)
    token_to_keys = defaultdict(set)
    type_counts = defaultdict(int)

    for spans in spans_per_doc:
        for s in spans:
            k, t = s.get("key", ""), s.get("token", "")
            if not k or not t:
                continue
            key_to_tokens[k].add(t)
            token_to_keys[t].add(k)
            type_counts[s.get("type", "UNKNOWN")] += 1

    splits = {k: sorted(v) for k, v in key_to_tokens.items() if len(v) > 1}
    merges = {t: sorted(v) for t, v in token_to_keys.items() if len(v) > 1}

    total_keys = len(key_to_tokens)
    total_tokens = len(token_to_keys)
    consistency_score = 1.0 - (len(splits) + len(merges)) / max(total_keys + total_tokens, 1)

    return {
        "splits": splits,
        "merges": merges,
        "split_count": len(splits),
        "merge_count": len(merges),
        "total_identities": total_keys,
        "total_tokens": total_tokens,
        "consistency_score": round(consistency_score, 4),
        "type_counts": dict(type_counts),
        "consistent": len(splits) == 0 and len(merges) == 0,
    }


def privacy_report_per_doc(spans_per_doc, verification_results):
    """Loop 3: per-document privacy summary.

    For each document, produce:
    - spans_replaced: count by type
    - verification_status: clean / leaked
    - risk_score: 0 (clean, many spans replaced) to 100 (leaks found)
    """
    reports = []
    for i, (spans, leaks) in enumerate(zip(spans_per_doc, verification_results)):
        by_type = defaultdict(int)
        for s in spans:
            by_type[s.get("type", "UNKNOWN")] += 1

        has_leaks = len(leaks) > 0
        n_spans = len(spans)

        # Risk score: 0 = clean with good coverage, 100 = leaks
        if has_leaks:
            risk = min(100, 50 + len(leaks) * 10)
        elif n_spans == 0:
            risk = 30  # no PII found — could be clean or could be missed
        else:
            risk = 0

        reports.append({
            "doc_index": i,
            "spans_replaced": dict(by_type),
            "total_spans": n_spans,
            "leaks_found": len(leaks),
            "leak_types": [lk["type"] for lk in leaks],
            "verification_status": "leaked" if has_leaks else "clean",
            "risk_score": risk,
        })

    return reports


def generate_certificate(
    batch_id,
    n_documents,
    n_tables,
    mode,
    verification_results,
    consistency_results,
    vault_location="separate storage (EDPB-compliant)",
    remediation_log=None,
    privacy_reports=None,
):
    """Generate a forensic compliance certificate for the batch."""
    now = datetime.now(timezone.utc)
    total_leaks = sum(len(r) for r in verification_results)
    pattern_leaks = sum(
        1 for r in verification_results for lk in r if lk.get("layer") == "A_pattern"
    )
    vault_leaks = sum(
        1 for r in verification_results for lk in r if lk.get("layer") == "B_vault"
    )
    auto_patched = len(remediation_log) if remediation_log else 0
    unpatched = pattern_leaks  # A_pattern leaks are not auto-patched

    gate1_pass = unpatched == 0  # pass if all leaks were auto-remediated
    gate2_pass = consistency_results["consistent"]

    if gate1_pass and gate2_pass:
        status = "COMPLIANT"
    elif gate1_pass:
        status = "REVIEW"
    else:
        status = "NON-COMPLIANT"

    # Risk summary from per-doc reports
    risk_summary = None
    if privacy_reports:
        risks = [r["risk_score"] for r in privacy_reports]
        risk_summary = {
            "max_risk": max(risks),
            "avg_risk": round(sum(risks) / len(risks), 1),
            "docs_at_risk": sum(1 for r in risks if r > 0),
            "docs_clean": sum(1 for r in risks if r == 0),
        }

    cert = {
        "certificate_id": hashlib.sha256(
            f"{batch_id}:{now.isoformat()}".encode()
        ).hexdigest()[:16],
        "batch_id": batch_id,
        "generated_at": now.isoformat(timespec="seconds"),
        "status": status,
        "mode": mode,
        "scope": {
            "documents": n_documents,
            "tables": n_tables,
        },
        "legal_basis": {
            "framework": "GDPR",
            "pseudonymisation_definition": "Art. 4(5)",
            "guidelines": [
                "EDPB Guidelines 01/2025 on Pseudonymisation",
                "EDPB Guidelines 02/2026 on Anonymisation (draft)",
                "ENISA Pseudonymisation Techniques and Best Practices (2019)",
            ],
            "classification": "Pseudonymised data (still personal data under GDPR)",
            "vault_requirement": "Additional information kept separately per EDPB 01/2025 §3",
        },
        "gate_1_verification": {
            "description": "Forward re-scan: structured patterns (Layer A) + vault-driven check (Layer B)",
            "passed": gate1_pass,
            "residual_pii_found": total_leaks,
            "pattern_leaks": pattern_leaks,
            "vault_leaks": vault_leaks,
            "auto_remediated": auto_patched,
            "unpatched_leaks": unpatched,
            "documents_with_leaks": sum(1 for r in verification_results if r),
        },
        "gate_2_consistency": {
            "description": "Retro-feedback audit of identity coherence across corpus",
            "passed": gate2_pass,
            "consistency_score": consistency_results["consistency_score"],
            "identity_splits": consistency_results["split_count"],
            "identity_merges": consistency_results["merge_count"],
            "total_identities": consistency_results["total_identities"],
        },
        "statistics": {
            "spans_by_type": consistency_results["type_counts"],
            "total_tokens_assigned": consistency_results["total_tokens"],
        },
        "vault": {
            "location": vault_location,
            "access_control": "Logged; requires person + reason (access_log.jsonl)",
        },
        "recommendations": [],
    }

    if risk_summary:
        cert["risk_summary"] = risk_summary

    if remediation_log:
        cert["remediation"] = {
            "auto_patched": len(remediation_log),
            "detail": remediation_log[:20],  # cap at 20 for readability
        }

    if unpatched > 0:
        cert["recommendations"].append(
            f"CRITICAL: {unpatched} structured PII pattern(s) survived pseudonymisation "
            "and could not be auto-patched. Review and re-process before ingestion."
        )
    if auto_patched > 0:
        cert["recommendations"].append(
            f"INFO: {auto_patched} original value(s) found in output were auto-patched "
            "using vault reverse-lookup. Verify the patched output."
        )
    if not gate2_pass:
        if consistency_results["split_count"]:
            cert["recommendations"].append(
                f"{consistency_results['split_count']} identity split(s): same person has "
                "multiple tokens. Memory queries may return partial results."
            )
        if consistency_results["merge_count"]:
            cert["recommendations"].append(
                f"{consistency_results['merge_count']} identity merge(s): different people "
                "share a token. Memory may conflate distinct individuals."
            )
    if not cert["recommendations"]:
        cert["recommendations"].append(
            "No issues found. Batch is ready for memory ingestion."
        )

    return cert


def print_certificate(cert):
    """Human-readable summary of the certificate."""
    g1 = cert["gate_1_verification"]
    g2 = cert["gate_2_consistency"]
    lines = [
        f"{'=' * 64}",
        f"  VELO COMPLIANCE CERTIFICATE",
        f"{'=' * 64}",
        f"  Batch:       {cert['batch_id']}",
        f"  Certificate: {cert['certificate_id']}",
        f"  Generated:   {cert['generated_at']}",
        f"  Status:      {cert['status']}",
        f"  Mode:        {cert['mode']}",
        f"{'─' * 64}",
        f"  SCOPE",
        f"    Documents: {cert['scope']['documents']}",
        f"    Tables:    {cert['scope']['tables']}",
        f"{'─' * 64}",
        f"  GATE 1 — FORWARD VERIFICATION (dual-layer)",
        f"    Passed:           {'YES' if g1['passed'] else 'NO'}",
        f"    Layer A (patterns):   {g1.get('pattern_leaks', g1['residual_pii_found'])} leak(s)",
        f"    Layer B (vault):      {g1.get('vault_leaks', 0)} leak(s)",
        f"    Auto-remediated:      {g1.get('auto_remediated', 0)}",
        f"    Unpatched:            {g1.get('unpatched_leaks', g1['residual_pii_found'])}",
        f"{'─' * 64}",
        f"  GATE 2 — RETRO-FEEDBACK CONSISTENCY",
        f"    Passed:           {'YES' if g2['passed'] else 'NO'}",
        f"    Consistency:      {g2['consistency_score']:.1%}",
        f"    Identity splits:  {g2['identity_splits']}",
        f"    Identity merges:  {g2['identity_merges']}",
        f"    Total identities: {g2['total_identities']}",
    ]
    if "risk_summary" in cert:
        rs = cert["risk_summary"]
        lines += [
            f"{'─' * 64}",
            f"  RISK SUMMARY",
            f"    Avg risk score:   {rs['avg_risk']}",
            f"    Max risk score:   {rs['max_risk']}",
            f"    Docs clean:       {rs['docs_clean']}",
            f"    Docs at risk:     {rs['docs_at_risk']}",
        ]
    lines += [
        f"{'─' * 64}",
        f"  LEGAL BASIS",
        f"    {cert['legal_basis']['framework']} {cert['legal_basis']['pseudonymisation_definition']}",
        f"    {cert['legal_basis']['classification']}",
        f"    Vault: {cert['vault']['location']}",
        f"{'─' * 64}",
        f"  RECOMMENDATIONS",
    ]
    for r in cert["recommendations"]:
        lines.append(f"    - {r}")
    lines.append(f"{'=' * 64}")
    return "\n".join(lines)
