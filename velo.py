"""Velo CLI — pseudonymise a folder of .txt and .csv files before they reach a memory or a model.

  python velo.py anonymize --in <folder> --out <folder> --vault <folder>
  python velo.py reidentify --vault <folder> --token "[PERSONA-07]" --who "<name, role>" --reason "<why>"
  python velo.py verify --out <folder> --vault <folder>
  python velo.py report --out <folder> --vault <folder>

Architecture: Privacy-Driven Dual Feedback Loop
  Phase 1: Detect + Resolve + Replace (corpus-level coreference)
  Phase 2: Forward Verification Gate (dual-layer: patterns + vault-driven)
  Phase 3: Auto-Remediation (patch surviving original values using vault reverse-lookup)
  Phase 4: Retro-Feedback Consistency Audit (identity splits/merges)
  Phase 5: Per-Document Privacy Report + Compliance Certificate

Where the mapping table lives and who can use it:
- The memory / model only ever receives --out. The mapping (token -> original values) is written ONLY to --vault,
  a separate folder that must sit outside the memory store (different machine, share or bucket in production).
- This is pseudonymisation, not anonymisation (GDPR art. 4(5); EDPB Guidelines 01/2025): whoever holds the
  vault can re-identify. Re-identification goes through `reidentify`, which refuses without a person and a
  reason and appends every lookup to vault/access_log.jsonl.
- Tokens carry no information about the person (sequential per run, no hash of the name to brute-force).
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anon.core import anonymize_all  # noqa: E402
from anon.audit import (  # noqa: E402
    verify_clean,
    auto_remediate,
    audit_consistency,
    privacy_report_per_doc,
    generate_certificate,
    print_certificate,
)


def cmd_anonymize(a):
    src, out, vault = Path(a.inp), Path(a.out), Path(a.vault)
    if out.resolve() == vault.resolve() or vault.resolve().is_relative_to(out.resolve()):
        sys.exit("refused: the vault must not live inside the output folder that feeds the memory")

    # ── Phase 1: Detect + Resolve + Replace ──
    txt = sorted(src.rglob("*.txt"))
    tab = sorted(src.rglob("*.csv"))
    texts = [p.read_text(encoding="utf-8") for p in txt]
    tables = []
    for p in tab:
        rows = list(csv.reader(p.open(encoding="utf-8")))
        tables.append((rows[0], rows[1:]))

    out_texts, spans, out_tables, mapping = anonymize_all(texts, tables, a.mode)

    # Write vault first (needed for Phase 2 Layer B)
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── Phase 2: Forward Verification Gate (dual-layer) ──
    batch_id = f"velo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    verification, remediation_map = verify_clean(out_texts, vault=mapping)

    # ── Phase 3: Auto-Remediation ──
    vault_leaks = sum(1 for r in verification for lk in r if lk.get("layer") == "B_vault")
    remediation_log = []
    if vault_leaks > 0:
        out_texts, remediation_log = auto_remediate(out_texts, verification)
        # Re-verify after remediation
        verification, _ = verify_clean(out_texts, vault=mapping)

    # Write pseudonymised output (after remediation)
    for p, t in zip(txt, out_texts):
        dst = out / p.relative_to(src); dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(t, encoding="utf-8")
    for p, (h, rows) in zip(tab, out_tables):
        dst = out / p.relative_to(src); dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([h] + rows)

    # ── Phase 4: Retro-Feedback Consistency Audit ──
    consistency = audit_consistency(spans)

    # ── Phase 5: Privacy Report + Certificate ──
    privacy_reports = privacy_report_per_doc(spans, verification)
    cert = generate_certificate(
        batch_id=batch_id,
        n_documents=len(txt),
        n_tables=len(tab),
        mode=a.mode,
        verification_results=verification,
        consistency_results=consistency,
        vault_location=str(vault.resolve()),
        remediation_log=remediation_log,
        privacy_reports=privacy_reports,
    )
    (vault / "certificate.json").write_text(json.dumps(cert, ensure_ascii=False, indent=1), encoding="utf-8")
    (vault / "privacy_reports.json").write_text(json.dumps(privacy_reports, ensure_ascii=False, indent=1), encoding="utf-8")

    # Summary
    n = sum(len(s) for s in spans)
    print(f"{len(txt)} text files, {len(tab)} tables -> {out}  |  {n} spans replaced  |  "
          f"{len(mapping)} tokens in vault")
    if remediation_log:
        print(f"  Auto-remediated: {len(remediation_log)} surviving original value(s) patched")
    print()
    print(print_certificate(cert))

    if cert["status"] == "NON-COMPLIANT":
        sys.exit(1)


def cmd_verify(a):
    """Standalone verification: re-run both layers on already-processed output."""
    out, vault_path = Path(a.out), Path(a.vault)
    txt = sorted(out.rglob("*.txt"))
    texts = [p.read_text(encoding="utf-8") for p in txt]

    # Load vault for Layer B
    vault_file = vault_path / "mapping.json"
    mapping = json.loads(vault_file.read_text(encoding="utf-8")) if vault_file.exists() else None

    verification, _ = verify_clean(texts, vault=mapping)
    total_leaks = sum(len(r) for r in verification)
    pattern_leaks = sum(1 for r in verification for lk in r if lk.get("layer") == "A_pattern")
    vault_leaks = sum(1 for r in verification for lk in r if lk.get("layer") == "B_vault")

    if total_leaks:
        print(f"FAIL: {total_leaks} residual PII found ({pattern_leaks} pattern, {vault_leaks} vault)")
        for i, (p, leaks) in enumerate(zip(txt, verification)):
            for lk in leaks:
                print(f"  {p.name}:{lk['start']}-{lk['end']} [{lk['type']}] "
                      f"[{lk['layer']}] {lk['surface'][:40]}")
        sys.exit(1)
    else:
        print(f"PASS: {len(txt)} files scanned (dual-layer), no residual PII found")


def cmd_report(a):
    """Print the privacy report and certificate from a previous run."""
    vault_path = Path(a.vault)
    cert_file = vault_path / "certificate.json"
    report_file = vault_path / "privacy_reports.json"

    if cert_file.exists():
        cert = json.loads(cert_file.read_text(encoding="utf-8"))
        print(print_certificate(cert))
    else:
        print("No certificate found. Run 'anonymize' first.")
        sys.exit(1)

    if report_file.exists():
        reports = json.loads(report_file.read_text(encoding="utf-8"))
        clean = sum(1 for r in reports if r["verification_status"] == "clean")
        at_risk = sum(1 for r in reports if r["risk_score"] > 0)
        print(f"\nPer-document privacy: {clean} clean, {at_risk} at risk, {len(reports)} total")
        # Show worst documents
        worst = sorted(reports, key=lambda r: -r["risk_score"])[:5]
        if worst and worst[0]["risk_score"] > 0:
            print("Highest risk documents:")
            for r in worst:
                if r["risk_score"] > 0:
                    print(f"  doc {r['doc_index']}: risk={r['risk_score']}, "
                          f"leaks={r['leaks_found']}, spans={r['total_spans']}")


def cmd_reidentify(a):
    if not a.who.strip() or not a.reason.strip():
        sys.exit("refused: --who and --reason are required")
    vault = Path(a.vault)
    mapping = json.loads((vault / "mapping.json").read_text(encoding="utf-8"))
    hit = mapping.get(a.token)
    with (vault / "access_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "who": a.who, "reason": a.reason,
                             "token": a.token, "found": hit is not None}, ensure_ascii=False) + "\n")
    print(json.dumps({"token": a.token, "values": hit}, ensure_ascii=False) if hit else "token not in vault")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    an = sub.add_parser("anonymize", help="Pseudonymise files with dual feedback loop")
    an.add_argument("--in", dest="inp", required=True)
    an.add_argument("--out", required=True)
    an.add_argument("--vault", required=True)
    an.add_argument("--mode", default="pseudo", choices=["pseudo", "redact", "regex"])

    vf = sub.add_parser("verify", help="Re-verify output (dual-layer: patterns + vault)")
    vf.add_argument("--out", required=True)
    vf.add_argument("--vault", required=True)

    rp = sub.add_parser("report", help="Print privacy report and certificate")
    rp.add_argument("--vault", required=True)

    re_ = sub.add_parser("reidentify", help="Reverse-lookup a token (logged)")
    re_.add_argument("--vault", required=True)
    re_.add_argument("--token", required=True)
    re_.add_argument("--who", default="")
    re_.add_argument("--reason", default="")

    a = ap.parse_args()
    {"anonymize": cmd_anonymize, "verify": cmd_verify, "report": cmd_report,
     "reidentify": cmd_reidentify}[a.cmd](a)


if __name__ == "__main__":
    main()
