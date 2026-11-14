"""Held-out check set: templates, name pools and formats the detector was NOT written against.

Differences from data/generate.py: unseen first names and surnames, "Surname Firstname" order, UPPERCASE names
(as in Italian forms), names inside free prose, phones without spaces and with +39 prefix, e-mails with other
local-part formats. Same output schema.

Usage: python data/generate_heldout.py [--n 120] [--seed 99] [--out data/heldout.jsonl]
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate import Doc, cf, iban, plate, MACHINES, ERRORS, DEPTS, SUPPLIERS, STREETS, CITIES

FIRST = ["Ludovica", "Edoardo", "Gaia", "Jacopo", "Noemi", "Ettore", "Ginevra", "Tiziano", "Mirko", "Arianna",
         "Mario", "Giulia", "Sara", "Paolo"]
LAST = ["Bonetto", "Chiaberge", "Peyrot", "Mondino", "Ghigo", "Vottero", "Audisio", "Gribaudo", "Rosso",
        "Ferrari", "Esposito", "Romano"]


def people(rng, n):
    seen, out = set(), []
    while len(out) < n:
        f, l = rng.choice(FIRST), rng.choice(LAST)
        if (f, l) in seen:
            continue
        seen.add((f, l))
        out.append({"id": f"Q{len(out):03d}", "first": f, "last": l,
                    "email": rng.choice([f"{l.lower()}.{f[0].lower()}", f"{f.lower()}{l.lower()}",
                                         f"{f[0].lower()}.{l.lower()}"]) + "@stabilimento-nord.it",
                    "phone": rng.choice([f"+39 3{rng.randint(20, 99)}{rng.randint(1000000, 9999999)}",
                                         f"+393{rng.randint(20, 99)}{rng.randint(1000000, 9999999)}",
                                         f"011/{rng.randint(100, 999)}{rng.randint(1000, 9999)}"]),
                    "cf": cf(rng), "emp": f"MAT-{rng.randint(10000, 99999)}",
                    "address": f"{rng.choice(STREETS)} {rng.randint(1, 99)}, " + " ".join(rng.choice(CITIES))})
    return out


def form_record(rng, i, ppl):
    d, w = Doc(f"X{i:04d}", "form"), rng.choice(ppl)
    m = rng.choice(MACHINES)
    d.t("MODULO PRESENZE FORMAZIONE SICUREZZA\nCOGNOME E NOME: ").p(f"{w['last'].upper()} {w['first'].upper()}",
                                                                  "PERSON", w["id"])
    d.t("\nCODICE FISCALE: ").p(w["cf"], "TAX_CODE", w["id"]).t("\nMATRICOLA: ").p(w["emp"], "EMPLOYEE_ID", w["id"])
    d.t("\nCorso abilitazione su ").u(m, "MACHINE").t(" — esito: idoneo\n")
    return d


def prose_note(rng, i, ppl):
    d = Doc(f"N{i:04d}", "note")
    a, b = rng.sample(ppl, 2)
    m, err = rng.choice(MACHINES), rng.choice(ERRORS)
    d.t("Nota di riunione. Oggi ").p(f"{a['last']} {a['first']}", "PERSON", a["id"])
    d.t(" ha spiegato che il fermo di ").u(m, "MACHINE").t(" (codice ").u(err, "ERROR")
    d.t(") dipende dal sensore. ").p(b["first"], "PERSON", b["id"]).t(" seguirà la sostituzione; per urgenze scrivere a ")
    d.p(b["email"], "EMAIL", b["id"]).t(" o chiamare il ").p(b["phone"], "PHONE", b["id"]).t(".\n")
    return d


def hr_letter(rng, i, ppl):
    d, w = Doc(f"R{i:04d}", "hr_letter"), rng.choice(ppl)
    d.t("Oggetto: rimborso trasferta\nSi autorizza il bonifico a favore di ").p(f"{w['first']} {w['last']}", "PERSON",
                                                                                   w["id"])
    d.t(" sul conto ").p(iban(rng), "IBAN", w["id"]).t(", residente in ").p(w["address"], "ADDRESS", w["id"])
    d.t(". Mezzo utilizzato: targa ").p(plate(rng), "PLATE", f"V{i}").t(". Reparto ").u(rng.choice(DEPTS), "DEPT")
    d.t(".\nFornitore trasporto: ").u(rng.choice(SUPPLIERS), "SUPPLIER").t("\n")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--out", default=str(Path(__file__).with_name("heldout.jsonl")))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    ppl = people(rng, 25)
    makers = [form_record, prose_note, hr_letter]
    docs = [makers[i % 3](rng, i, ppl).json() for i in range(a.n)]
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(d, ensure_ascii=False) + "\n" for d in docs)
    print(f"wrote {len(docs)} held-out docs, {sum(len(d['pii']) for d in docs)} PII spans -> {a.out}")


if __name__ == "__main__":
    main()
