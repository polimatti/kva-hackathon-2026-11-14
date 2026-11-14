"""Check set: measures privacy, utility and identity linkage on the synthetic corpus, for three modes.

Privacy  - recall: share of gold PII spans fully covered by a detected span (anything else is a leak).
           precision: share of detected spans that touch gold PII.
Utility  - share of non-personal technical tokens (machines, parts, error codes, lots, suppliers) left intact.
Linkage  - B-cubed F1 between real identities and pseudonym keys over detected person/e-mail mentions.
Memory QA - questions a company memory must still answer after anonymisation:
           Q1 tickets per reporter (pair agreement with the truth, Rand index),
           Q2 number of distinct injured workers.

Usage: python eval/evaluate.py [--corpus data/corpus.jsonl] [--out out/metrics.json]
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anon.core import anonymize_corpus  # noqa: E402

MODES = ["regex", "redact", "pseudo"]


def covered(g, spans):
    return any(s["start"] <= g["start"] and s["end"] >= g["end"] for s in spans)


def touches(s, golds):
    return any(s["start"] < g["end"] and s["end"] > g["start"] for g in golds)


def bcubed(pairs):
    """pairs: list of (gold_entity, predicted_key)."""
    if not pairs:
        return 0.0, 0.0, 0.0
    by_g, by_p = defaultdict(list), defaultdict(list)
    for i, (g, p) in enumerate(pairs):
        by_g[g].append(i); by_p[p].append(i)
    P = sum(sum(1 for j in by_p[p] if pairs[j][0] == g) / len(by_p[p]) for g, p in pairs) / len(pairs)
    R = sum(sum(1 for j in by_g[g] if pairs[j][1] == p) / len(by_g[g]) for g, p in pairs) / len(pairs)
    return P, R, 2 * P * R / (P + R) if P + R else 0.0


def rand_index(gold, pred):
    agree = total = 0
    for i, j in combinations(range(len(gold)), 2):
        total += 1
        agree += (gold[i] == gold[j]) == (pred[i] == pred[j])
    return agree / total if total else 1.0


def evaluate(docs, mode):
    texts = [d["text"] for d in docs]
    anon, spans, vault = anonymize_corpus(texts, mode)
    per_type = defaultdict(lambda: [0, 0])
    det = tp_det = util_ok = util_n = 0
    link = []
    for d, sp in zip(docs, spans):
        for g in d["pii"]:
            per_type[g["type"]][1] += 1
            per_type[g["type"]][0] += covered(g, sp)
            if g["type"] in ("PERSON", "EMAIL"):
                m = [s for s in sp if s["start"] <= g["start"] and s["end"] >= g["end"] and s["type"] == g["type"]]
                if len(m) == 1:
                    link.append((g["entity"], m[0]["key"]))
        det += len(sp); tp_det += sum(touches(s, d["pii"]) for s in sp)
        for u in d["utility"]:
            util_n += 1; util_ok += not touches(u, sp)
    rec_n = sum(v[0] for v in per_type.values()); tot = sum(v[1] for v in per_type.values())

    # Memory QA on the anonymised text only
    tk = [(d, a) for d, a in zip(docs, anon) if d["kind"] == "ticket"]
    gold_rep = [d["facts"]["reporter"] for d, _ in tk]
    pred_rep = [(re.search(r"Segnalato da: (.+?) \(", a) or [None, None])[1] for _, a in tk]
    inc = [(d, a) for d, a in zip(docs, anon) if d["kind"] == "incident"]
    gold_w = len({d["facts"]["worker"] for d, _ in inc})
    pred_w = len({(re.search(r"Lavoratore: (.+?), CF", a) or [None, None])[1] for _, a in inc})
    top_gold = Counter(gold_rep).most_common(1)[0][1]
    top_pred = Counter(pred_rep).most_common(1)[0][1]
    P, R, F = bcubed(link)
    return {
        "mode": mode,
        "privacy_recall": rec_n / tot, "privacy_precision": tp_det / det if det else 0.0,
        "leaked_spans": tot - rec_n, "gold_spans": tot,
        "recall_by_type": {k: round(v[0] / v[1], 4) for k, v in sorted(per_type.items())},
        "utility_preserved": util_ok / util_n,
        "linkage_bcubed": {"precision": P, "recall": R, "f1": F},
        "qa_tickets_per_reporter_rand": rand_index(gold_rep, pred_rep),
        "qa_top_reporter_count": {"truth": top_gold, "anonymised": top_pred},
        "qa_distinct_injured_workers": {"truth": gold_w, "anonymised": pred_w},
    }, anon, spans, vault


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "data" / "corpus.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "out" / "metrics.json"))
    a = ap.parse_args()
    docs = [json.loads(l) for l in open(a.corpus, encoding="utf-8")]
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    for mode in MODES:
        r, anon, spans, vault = evaluate(docs, mode)
        results[mode] = r
        if mode == "pseudo":
            (out.parent / "anonymised.jsonl").write_text(
                "".join(json.dumps({"id": d["id"], "kind": d["kind"], "text": t, "spans": s}, ensure_ascii=False)
                        + "\n" for d, t, s in zip(docs, anon, spans)), encoding="utf-8")
            (out.parent / "vault.json").write_text(json.dumps(vault, ensure_ascii=False, indent=1), encoding="utf-8")
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    hdr = f"{'mode':8} {'priv.rec':>8} {'priv.prec':>9} {'leaks':>6} {'utility':>8} {'link.F1':>8} {'QA1 rand':>9} {'QA2 workers':>12}"
    print(hdr)
    for m, r in results.items():
        q2 = r["qa_distinct_injured_workers"]
        print(f"{m:8} {r['privacy_recall']:8.3f} {r['privacy_precision']:9.3f} {r['leaked_spans']:6d} "
              f"{r['utility_preserved']:8.3f} {r['linkage_bcubed']['f1']:8.3f} {r['qa_tickets_per_reporter_rand']:9.3f} "
              f"{q2['anonymised']:>5}/{q2['truth']:<5}")
    print("recall by type (pseudo):", results["pseudo"]["recall_by_type"])


if __name__ == "__main__":
    main()
