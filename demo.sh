#!/usr/bin/env bash
# Velo one-command demo: full privacy-driven 5-phase pipeline.
# Requires only Python 3.10+ (stdlib only, no pip install needed).
#
# Usage:
#   bash demo.sh
#   # or: chmod +x demo.sh && ./demo.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "╔══════════════════════════════════════════════════════╗"
echo "║          VELO — PRIVACY-DRIVEN DEMO                 ║"
echo "║    5-phase pseudonymisation with dual feedback loop  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

echo "▸ Phase 0: Generate synthetic corpus with planted PII..."
python data/generate.py --n 50 --out data/demo_corpus.jsonl
echo ""

echo "▸ Preparing input files..."
mkdir -p demo_in demo_out demo_vault
python -c "
import json, pathlib
docs = [json.loads(l) for l in open('data/demo_corpus.jsonl', encoding='utf-8')]
for d in docs:
    pathlib.Path(f\"demo_in/{d['id']}.txt\").write_text(d['text'], encoding='utf-8')
print(f'  {len(docs)} text files written to demo_in/')
"
echo ""

echo "▸ Phases 1-5: Pseudonymise with full pipeline..."
echo "  Phase 1: Detect + Resolve + Replace"
echo "  Phase 2: Forward Verification (Layer A: patterns + Layer B: vault-driven)"
echo "  Phase 3: Auto-Remediation (vault reverse-lookup)"
echo "  Phase 4: Retro-Feedback Consistency Audit"
echo "  Phase 5: Privacy Report + Compliance Certificate"
echo ""
python velo.py anonymize --in demo_in --out demo_out --vault demo_vault
echo ""

echo "▸ Standalone re-verification (dual-layer)..."
python velo.py verify --out demo_out --vault demo_vault
echo ""

echo "▸ Privacy report..."
python velo.py report --vault demo_vault
echo ""

echo "▸ Re-identification (with audit trail)..."
TOKEN=$(python -c "import json; m=json.load(open('demo_vault/mapping.json')); print(list(m.keys())[0])")
python velo.py reidentify --vault demo_vault --token "$TOKEN" --who "Demo operator" --reason "Demo run"
echo ""

echo "▸ Evaluate privacy and utility metrics..."
python eval/evaluate.py --corpus data/demo_corpus.jsonl --out demo_out/metrics.json
echo ""

echo "╔══════════════════════════════════════════════════════╗"
echo "║                  DEMO COMPLETE                       ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Output:       demo_out/                             ║"
echo "║  Vault:        demo_vault/                           ║"
echo "║    mapping.json      — pseudonym ↔ original values   ║"
echo "║    certificate.json  — forensic compliance cert      ║"
echo "║    privacy_reports.json — per-doc risk scores        ║"
echo "║    access_log.jsonl  — re-identification audit trail ║"
echo "║  Metrics:      demo_out/metrics.json                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "To clean up: rm -rf demo_in demo_out demo_vault data/demo_corpus.jsonl"
