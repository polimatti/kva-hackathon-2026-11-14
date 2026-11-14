#!/usr/bin/env bash
# Velo one-command demo: generates synthetic data, pseudonymises it, verifies, prints certificate.
# Requires only Python 3.10+ (stdlib only, no pip install needed).
#
# Usage:
#   bash demo.sh
#   # or: chmod +x demo.sh && ./demo.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "=== VELO DEMO ==="
echo ""
echo "Step 1: Generate synthetic corpus with planted PII..."
python data/generate.py --n 50 --out data/demo_corpus.jsonl
echo ""

echo "Step 2: Prepare input files..."
mkdir -p demo_in demo_out demo_vault
# Convert JSONL to individual .txt files for the CLI
python -c "
import json, pathlib
docs = [json.loads(l) for l in open('data/demo_corpus.jsonl', encoding='utf-8')]
for d in docs:
    pathlib.Path(f\"demo_in/{d['id']}.txt\").write_text(d['text'], encoding='utf-8')
print(f'  {len(docs)} text files written to demo_in/')
"
echo ""

echo "Step 3: Pseudonymise with dual feedback loop..."
echo ""
python velo.py anonymize --in demo_in --out demo_out --vault demo_vault
echo ""

echo "Step 4: Standalone verification..."
python velo.py verify --out demo_out --vault demo_vault
echo ""

echo "Step 5: Re-identification (with audit trail)..."
TOKEN=$(python -c "import json; m=json.load(open('demo_vault/mapping.json')); print(list(m.keys())[0])")
python velo.py reidentify --vault demo_vault --token "$TOKEN" --who "Demo operator" --reason "Demo run"
echo ""

echo "Step 6: Evaluate privacy and utility metrics..."
python eval/evaluate.py --corpus data/demo_corpus.jsonl --out demo_out/metrics.json
echo ""

echo "=== DEMO COMPLETE ==="
echo "Output:      demo_out/"
echo "Vault:       demo_vault/ (mapping + certificate + access log)"
echo "Metrics:     demo_out/metrics.json"

# Cleanup option
echo ""
echo "To clean up: rm -rf demo_in demo_out demo_vault data/demo_corpus.jsonl"
