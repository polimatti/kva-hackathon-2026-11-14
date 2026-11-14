"""FROZEN test set. Written at 10:30 on 14/11/2026 and run once; the detector is not tuned on it.
If the detector changes after a run, the result is reported as "seen" and a new seed/pool is drawn.

Hard cases on purpose: multi-word surnames (De Luca, Dalla Valle), double first names (Gian Maria),
lowercase names in chat, female titles (Dott.ssa, Sig.ra), names next to company names, mixed e-mail formats.

Usage: python data/generate_test.py [--n 150] [--seed 2026] [--out data/test.jsonl]
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import Doc, cf, iban, plate, MACHINES, ERRORS, SUPPLIERS, STREETS, CITIES  # noqa: E402

FIRST = ["Gian Maria", "Anna Lisa", "Pier Giorgio", "Benedetta", "Ruggero", "Ilenia", "Corrado", "Mara",
         "Tullio", "Rosanna", "Marco", "Elena"]
LAST = ["De Luca", "Dalla Valle", "Lo Russo", "Di Stefano", "Bertone", "Quaglia", "Tosco", "Garrone",
        "Sacco", "Ponzio"]
FTITLE = ["Dott.ssa", "Sig.ra", "Ing.", "Arch."]


def people(rng, n):
    seen, out = set(), []
    while len(out) < n:
        f, l = rng.choice(FIRST), rng.choice(LAST)
        if (f, l) in seen:
            continue
        seen.add((f, l))
        lf, ll = f.lower().replace(" ", ""), l.lower().replace(" ", "")
        out.append({"id": f"T{len(out):03d}", "first": f, "last": l, "title": rng.choice(FTITLE),
                    "email": rng.choice([f"{lf}.{ll}", f"{lf[0]}{ll}", f"{ll}.{lf}"]) + "@gruppo-meccanico.it",
                    "phone": f"+39 3{rng.randint(20, 99)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
                    "cf": cf(rng), "emp": f"MAT-{rng.randint(10000, 99999)}",
                    "address": f"{rng.choice(STREETS)} {rng.randint(1, 99)}, " + " ".join(rng.choice(CITIES))})
    return out


def audit(rng, i, ppl):
    d, a, b = Doc(f"A{i:04d}", "audit"), *rng.sample(ppl, 2)
    m, sup = rng.choice(MACHINES), rng.choice(SUPPLIERS)
    d.t("Verbale audit fornitore ").u(sup, "SUPPLIER").t("\nAuditor: ").t(a["title"] + " ").p(
        f"{a['first']} {a['last']}", "PERSON", a["id"])
    d.t("\nRilievo: la macchina ").u(m, "MACHINE").t(" non ha il registro manutenzioni. La ").t(
        a["title"] + " ").p(a["last"], "PERSON", a["id"])
    d.t(" chiede un piano entro 30 giorni. In copia ").p(b["email"], "EMAIL", b["id"]).t(".\n")
    return d


def chat(rng, i, ppl):
    d, a, b = Doc(f"C{i:04d}", "chat"), *rng.sample(ppl, 2)
    err = rng.choice(ERRORS)
    d.t("ciao ").p(b["first"].lower(), "PERSON", b["id"]).t(", la ").u(rng.choice(MACHINES), "MACHINE")
    d.t(" dà di nuovo ").u(err, "ERROR").t(", senti ").p(a["last"], "PERSON", a["id"]).t(" al ")
    d.p(a["phone"], "PHONE", a["id"]).t(" — ").p(a["first"], "PERSON", a["id"]).t(" sa come resettarla\n")
    return d


def payroll(rng, i, ppl):
    d, w = Doc(f"P{i:04d}", "payroll"), rng.choice(ppl)
    d.t("Variazione dati dipendente\nNominativo: ").p(f"{w['last']} {w['first']}", "PERSON", w["id"])
    d.t("\nCF ").p(w["cf"], "TAX_CODE", w["id"]).t(" — matricola ").p(w["emp"], "EMPLOYEE_ID", w["id"])
    d.t("\nNuovo IBAN: ").p(iban(rng), "IBAN", w["id"]).t("\nNuovo domicilio: ").p(w["address"], "ADDRESS", w["id"])
    d.t("\nAuto aziendale assegnata: ").p(plate(rng), "PLATE", f"V{i}").t("\n")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=str(Path(__file__).with_name("test.jsonl")))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    ppl = people(rng, 22)
    makers = [audit, chat, payroll]
    docs = [makers[i % 3](rng, i, ppl).json() for i in range(a.n)]
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)
    print(f"wrote {len(docs)} frozen-test docs, {sum(len(d['pii']) for d in docs)} PII spans -> {a.out}")


if __name__ == "__main__":
    main()
