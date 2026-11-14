"""Velo CLI — pseudonymise a folder of .txt and .csv files before they reach a memory or a model.

  python velo.py anonymize --in <folder> --out <folder> --vault <folder>
  python velo.py reidentify --vault <folder> --token "[PERSONA-07]" --who "<name, role>" --reason "<why>"
  python velo.py verify --out <folder> --vault <folder>

Architecture: Dual Feedback Loop
  Loop 1 (Forward Gate): after pseudonymisation, re-scan output for residual PII.
  Loop 2 (Retro-Feedback): audit identity consistency across the full corpus.
  Output: forensic compliance certificate written to vault/certificate.json.

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
    audit_consistency,
    generate_certificate,
    print_certificate,
)


def cmd_anonymize(a):
    src, out, vault = Path(a.inp), Path(a.out), Path(a.vault)
    if out.resolve() == vault.resolve() or vault.resolve().is_relative_to(out.resolve()):
        sys.exit("refused: the vault must not live inside the output folder that feeds the memory")
    txt = sorted(src.rglob("*.txt"))
    tab = sorted(src.rglob("*.csv"))
    texts = [p.read_text(encoding="utf-8") for p in txt]
    tables = []
    for p in tab:
        rows = list(csv.reader(p.open(encoding="utf-8")))
        tables.append((rows[0], rows[1:]))
    out_texts, spans, out_tables, mapping = anonymize_all(texts, tables, a.mode)

    # Write pseudonymised output
    for p, t in zip(txt, out_texts):
        dst = out / p.relative_to(src); dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(t, encoding="utf-8")
    for p, (h, rows) in zip(tab, out_tables):
        dst = out / p.relative_to(src); dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([h] + rows)

    # Write vault
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- DUAL FEEDBACK LOOP ---
    batch_id = f"velo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Loop 1: Forward Verification Gate
    verification = verify_clean(out_texts)

    # Loop 2: Retro-Feedback Consistency Audit
    consistency = audit_consistency(spans)

    # Generate compliance certificate
    cert = generate_certificate(
        batch_id=batch_id,
        n_documents=len(txt),
        n_tables=len(tab),
        mode=a.mode,
        verification_results=verification,
        consistency_results=consistency,
        vault_location=str(vault.resolve()),
    )
    (vault / "certificate.json").write_text(json.dumps(cert, ensure_ascii=False, indent=1), encoding="utf-8")

    # Summary
    n = sum(len(s) for s in spans)
    print(f"{len(txt)} text files, {len(tab)} tables -> {out}  |  {n} spans replaced in text  |  "
          f"{len(mapping)} tokens in vault {vault / 'mapping.json'}")
    print()
    print(print_certificate(cert))

    if cert["status"] == "NON-COMPLIANT":
        sys.exit(1)


def cmd_verify(a):
    """Standalone verification: re-run both loops on already-processed output."""
    out, vault = Path(a.out), Path(a.vault)
    txt = sorted(out.rglob("*.txt"))
    texts = [p.read_text(encoding="utf-8") for p in txt]

    verification = verify_clean(texts)
    total_leaks = sum(len(r) for r in verification)
    if total_leaks:
        print(f"FAIL: {total_leaks} residual PII pattern(s) found in output")
        for i, (p, leaks) in enumerate(zip(txt, verification)):
            for lk in leaks:
                print(f"  {p.name}:{lk['start']}-{lk['end']} [{lk['type']}] {lk['surface']}")
        sys.exit(1)
    else:
        print(f"PASS: {len(txt)} files scanned, no residual PII found")


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
    an = sub.add_parser("anonymize"); an.add_argument("--in", dest="inp", required=True)
    an.add_argument("--out", required=True); an.add_argument("--vault", required=True)
    an.add_argument("--mode", default="pseudo", choices=["pseudo", "redact", "regex"])
    vf = sub.add_parser("verify"); vf.add_argument("--out", required=True)
    vf.add_argument("--vault", required=True)
    re_ = sub.add_parser("reidentify"); re_.add_argument("--vault", required=True)
    re_.add_argument("--token", required=True); re_.add_argument("--who", default="")
    re_.add_argument("--reason", default="")
    a = ap.parse_args()
    {"anonymize": cmd_anonymize, "verify": cmd_verify, "reidentify": cmd_reidentify}[a.cmd](a)


if __name__ == "__main__":
    main()
