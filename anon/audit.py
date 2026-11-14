"""Dual Feedback Loop: verification gate + consistency audit + forensic compliance certificate.

Loop 1 — Forward Verification Gate
    After pseudonymisation, re-scan the OUTPUT for residual PII that survived the first pass.
    Any structured PII pattern found in the pseudonymised text (that is not one of our own tokens)
    is a leak. The gate marks the batch FAIL and reports exactly where.

Loop 2 — Retro-Feedback Consistency Audit
    After corpus-level processing, walk every span and check:
      - No identity splits (same key mapped to multiple tokens)
      - No identity merges (same token used for multiple keys)
      - Cross-file coherence (if text and tables share a person, they share a token)
    Splits and merges degrade the memory's ability to link facts.

Output — Compliance Certificate
    A JSON document that travels with the batch: batch ID, timestamps, GDPR basis,
    gate verdicts, statistics, and a final COMPLIANT / NON-COMPLIANT / REVIEW status.
    This is the artifact a DPO reads before approving ingestion.
"""
import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone

# Structured PII patterns (same as core.py) for the verification re-scan
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

# Our own token pattern — these are NOT leaks
_OUR_TOKEN = re.compile(r"\[(PERSONA|EMAIL PERSONA|TEL|IBAN|CF|MATRICOLA|TARGA|INDIRIZZO)-\d{2}\]")


def verify_clean(anonymised_texts):
    """Loop 1: re-scan pseudonymised output for residual PII.

    Returns a list (one per text) of leak dicts: {type, start, end, surface}.
    An empty list means the text is clean.
    """
    all_leaks = []
    for text in anonymised_texts:
        leaks = []
        for typ, rx in _VERIFY_PATTERNS:
            for m in rx.finditer(text):
                surface = m.group()
                # Check it's not inside one of our tokens
                if _OUR_TOKEN.search(surface):
                    continue
                # Check the match isn't part of a token like [EMAIL PERSONA-01]
                ctx_start = max(0, m.start() - 1)
                ctx_end = min(len(text), m.end() + 1)
                ctx = text[ctx_start:ctx_end]
                if "[" in ctx and "]" in ctx:
                    continue
                leaks.append({"type": typ, "start": m.start(), "end": m.end(), "surface": surface})
            all_leaks.append(leaks)
    return all_leaks


def audit_consistency(spans_per_doc):
    """Loop 2: retro-feedback consistency audit.

    Checks identity coherence across the full corpus:
    - splits: same identity key → multiple tokens (bad: fragments a person)
    - merges: same token → multiple identity keys (bad: conflates people)

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


def generate_certificate(
    batch_id,
    n_documents,
    n_tables,
    mode,
    verification_results,
    consistency_results,
    vault_location="separate storage (EDPB-compliant)",
):
    """Generate a forensic compliance certificate for the batch.

    This is the artifact a DPO reads before approving ingestion into memory.
    """
    now = datetime.now(timezone.utc)
    total_leaks = sum(len(r) for r in verification_results)
    gate1_pass = total_leaks == 0
    gate2_pass = consistency_results["consistent"]

    if gate1_pass and gate2_pass:
        status = "COMPLIANT"
    elif gate1_pass:
        status = "REVIEW"  # no leaks, but consistency issues
    else:
        status = "NON-COMPLIANT"

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
            "description": "Forward re-scan of pseudonymised output for residual PII",
            "passed": gate1_pass,
            "residual_pii_found": total_leaks,
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

    if not gate1_pass:
        cert["recommendations"].append(
            f"CRITICAL: {total_leaks} PII pattern(s) survived pseudonymisation. "
            "Review and re-process before ingestion."
        )
    if not gate2_pass:
        if consistency_results["split_count"]:
            cert["recommendations"].append(
                f"{consistency_results['split_count']} identity split(s): same person has multiple tokens. "
                "Memory queries about that person may return partial results."
            )
        if consistency_results["merge_count"]:
            cert["recommendations"].append(
                f"{consistency_results['merge_count']} identity merge(s): different people share a token. "
                "Memory may conflate distinct individuals."
            )
    if not cert["recommendations"]:
        cert["recommendations"].append("No issues found. Batch is ready for memory ingestion.")

    return cert


def print_certificate(cert):
    """Human-readable summary of the certificate."""
    lines = [
        f"{'=' * 60}",
        f"  VELO COMPLIANCE CERTIFICATE",
        f"{'=' * 60}",
        f"  Batch:       {cert['batch_id']}",
        f"  Certificate: {cert['certificate_id']}",
        f"  Generated:   {cert['generated_at']}",
        f"  Status:      {cert['status']}",
        f"  Mode:        {cert['mode']}",
        f"{'─' * 60}",
        f"  SCOPE",
        f"    Documents: {cert['scope']['documents']}",
        f"    Tables:    {cert['scope']['tables']}",
        f"{'─' * 60}",
        f"  GATE 1 — FORWARD VERIFICATION",
        f"    Passed:           {'YES' if cert['gate_1_verification']['passed'] else 'NO'}",
        f"    Residual PII:     {cert['gate_1_verification']['residual_pii_found']}",
        f"{'─' * 60}",
        f"  GATE 2 — RETRO-FEEDBACK CONSISTENCY",
        f"    Passed:           {'YES' if cert['gate_2_consistency']['passed'] else 'NO'}",
        f"    Consistency:      {cert['gate_2_consistency']['consistency_score']:.1%}",
        f"    Identity splits:  {cert['gate_2_consistency']['identity_splits']}",
        f"    Identity merges:  {cert['gate_2_consistency']['identity_merges']}",
        f"    Total identities: {cert['gate_2_consistency']['total_identities']}",
        f"{'─' * 60}",
        f"  LEGAL BASIS",
        f"    {cert['legal_basis']['framework']} {cert['legal_basis']['pseudonymisation_definition']}",
        f"    {cert['legal_basis']['classification']}",
        f"    Vault: {cert['vault']['location']}",
        f"{'─' * 60}",
        f"  RECOMMENDATIONS",
    ]
    for r in cert["recommendations"]:
        lines.append(f"    - {r}")
    lines.append(f"{'=' * 60}")
    return "\n".join(lines)
