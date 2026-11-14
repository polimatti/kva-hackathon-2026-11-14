"""Synthetic Italian industrial corpus with exact PII ground truth.

Every personal datum is inserted by this script, so its span, type and real identity are known.
No real person is described: names are random combinations, IDs are random strings in valid formats.

Usage: python data/generate.py [--n 300] [--seed 7] [--out data/corpus.jsonl]
"""
import argparse
import json
import random
import string
from pathlib import Path

# First names: common ones (also in the detector gazetteer) + rarer ones the detector does NOT know.
FIRST_COMMON = ["Mario", "Luca", "Giulia", "Francesca", "Marco", "Andrea", "Paolo", "Sara", "Elena", "Matteo",
                "Chiara", "Davide", "Simone", "Laura", "Stefano", "Federica", "Alessandro", "Valentina", "Roberto",
                "Silvia", "Giorgio", "Martina", "Fabio", "Anna", "Riccardo"]
FIRST_RARE = ["Ottavio", "Ernesta", "Lino", "Gisella", "Adalberto", "Nives", "Oreste", "Fulvia"]
LAST = ["Rossi", "Bianchi", "Ferrero", "Gallo", "Conti", "Ricci", "Marino", "Greco", "Bruno", "Costa",
        "Fontana", "Rinaldi", "Caruso", "Galli", "Martini", "Leone", "Longo", "Mancini", "Lombardi", "Moretti",
        "Barbero", "Giordano", "Rizzo", "Colombo", "Testa", "Bertolino", "Cravero", "Allasia"]
TITLES = ["Ing.", "Dott.", "Geom.", "Sig.", "Per. Ind."]
STREETS = ["Via Roma", "Corso Francia", "Via Nizza", "Corso Vittorio Emanuele II", "Via Po", "Strada del Drosso",
           "Via Sant'Antonino", "Corso Giulio Cesare", "Via Cibrario", "Piazza Statuto"]
CITIES = [("10139", "Torino"), ("10121", "Torino"), ("10093", "Collegno"), ("10098", "Rivoli"),
          ("10024", "Moncalieri"), ("10095", "Grugliasco")]
SUPPLIERS = ["Officine Valsusa srl", "Meccanica Dora spa", "Stampi Canavese srl", "Idraulica Pinerolese snc",
             "Componenti Monviso srl"]
MACHINES = ["PRESSA-01", "PRESSA-04", "PRESSA-07", "CNC-L3", "CNC-L5", "ROBOT-SALD-2", "FORNO-T1", "NASTRO-12"]
DEPTS = ["Stampaggio", "Lavorazioni CNC", "Saldatura", "Trattamenti termici", "Logistica interna"]
ERRORS = ["E-104", "E-221", "E-307", "E-415", "E-502", "E-618"]
DOMAIN_INT = "brusaindustrie.it"


def cf(rng):
    L = string.ascii_uppercase
    return ("".join(rng.choice(L) for _ in range(6)) + f"{rng.randint(50, 99)}" + rng.choice("ABCDEHLMPRST")
            + f"{rng.randint(1, 71):02d}" + rng.choice(L) + f"{rng.randint(100, 999)}" + rng.choice(L))


def iban(rng):
    raw = "IT" + f"{rng.randint(10, 99)}" + rng.choice(string.ascii_uppercase) + "".join(
        rng.choice(string.digits) for _ in range(22))
    return " ".join(raw[i:i + 4] for i in range(0, len(raw), 4)) if rng.random() < 0.5 else raw


def phone(rng, mobile=True):
    if mobile:
        p, a, b = f"3{rng.randint(20, 99)}", f"{rng.randint(100, 999)}", f"{rng.randint(1000, 9999)}"
        return rng.choice([f"+39 {p} {a} {b}", f"{p}-{a}{b}", f"{p}{a}{b}", f"{p} {a}{b}"])
    return f"011 {rng.randint(100, 999)} {rng.randint(1000, 9999)}"


def plate(rng):
    L = "ABCDEFGHJKLMNPRSTVWXYZ"
    return rng.choice(L) + rng.choice(L) + f"{rng.randint(100, 999)}" + rng.choice(L) + rng.choice(L)


def make_people(rng, n):
    seen, people = set(), []
    while len(people) < n:
        first = rng.choice(FIRST_COMMON if rng.random() < 0.8 else FIRST_RARE)
        last = rng.choice(LAST)
        if (first, last) in seen:
            continue
        seen.add((first, last))
        pid = f"P{len(people):03d}"
        people.append({
            "id": pid, "first": first, "last": last, "title": rng.choice(TITLES),
            "email": f"{first.lower()}.{last.lower()}@{DOMAIN_INT}",
            "phone": phone(rng), "emp": f"MAT-{rng.randint(10000, 99999)}", "cf": cf(rng),
            "address": f"{rng.choice(STREETS)} {rng.randint(1, 180)}, " + " ".join(rng.choice(CITIES)),
        })
    return people


def make_contacts(rng, n):
    out = []
    for i in range(n):
        first, last = rng.choice(FIRST_COMMON + FIRST_RARE), rng.choice(LAST)
        sup = rng.choice(SUPPLIERS)
        dom = sup.split()[1].lower() + ".it"
        out.append({"id": f"C{i:03d}", "first": first, "last": last, "supplier": sup,
                    "email": f"{first[0].lower()}{last.lower()}@{dom}", "phone": phone(rng, mobile=rng.random() < .5),
                    "iban": iban(rng), "title": rng.choice(TITLES)})
    return out


class Doc:
    def __init__(self, doc_id, kind):
        self.id, self.kind, self.text, self.pii, self.util, self.facts = doc_id, kind, "", [], [], {}

    def t(self, s):
        self.text += s
        return self

    def p(self, s, typ, ent):
        self.pii.append({"start": len(self.text), "end": len(self.text) + len(s), "type": typ, "entity": ent,
                         "text": s})
        self.text += s
        return self

    def u(self, s, typ):
        self.util.append({"start": len(self.text), "end": len(self.text) + len(s), "type": typ, "text": s})
        self.text += s
        return self

    def json(self):
        return {"id": self.id, "kind": self.kind, "text": self.text, "pii": self.pii, "utility": self.util,
                "facts": self.facts}


def name_form(rng, d, person, forms=("full", "title", "initial")):
    f = rng.choice(forms)
    if f == "full":
        d.p(f"{person['first']} {person['last']}", "PERSON", person["id"])
    elif f == "title":
        d.t(person["title"] + " ").p(person["last"], "PERSON", person["id"])
    elif f == "initial":
        d.p(f"{person['first'][0]}. {person['last']}", "PERSON", person["id"])
    elif f == "surname":
        d.p(person["last"], "PERSON", person["id"])
    elif f == "first":
        d.p(person["first"], "PERSON", person["id"])


def date(rng):
    return f"{rng.randint(1, 28):02d}/{rng.randint(1, 10):02d}/2026"


def ticket(rng, i, techs, sups):
    d, tech, sup = Doc(f"T{i:04d}", "ticket"), rng.choice(techs), rng.choice(sups)
    m, part, err = rng.choice(MACHINES), f"CMP-{rng.randint(1000, 9999)}-{rng.choice('ABCD')}", rng.choice(ERRORS)
    d.facts = {"reporter": tech["id"], "machine": m}
    d.t(f"Ticket manutenzione {d.id} del ").u(date(rng), "DATE").t("\nMacchina: ").u(m, "MACHINE")
    d.t("\nSegnalato da: ").p(f"{tech['first']} {tech['last']}", "PERSON", tech["id"])
    d.t(" (matricola ").p(tech["emp"], "EMPLOYEE_ID", tech["id"]).t(")\n")
    d.t("Descrizione: allarme ").u(err, "ERROR").t(" durante il ciclo, sostituito il componente ").u(part, "PART")
    d.t(". Il tecnico ")
    name_form(rng, d, tech, ("surname", "initial", "title"))
    d.t(" ha chiesto supporto a ")
    name_form(rng, d, sup)
    d.t(".\nRecapito tecnico: ").p(tech["phone"], "PHONE", tech["id"]).t("\n")
    return d


def supplier_mail(rng, i, contacts, buyers):
    d, c, b = Doc(f"S{i:04d}", "supplier_email"), rng.choice(contacts), rng.choice(buyers)
    lot, part = f"L2026-{rng.randint(100, 999)}", f"CMP-{rng.randint(1000, 9999)}-{rng.choice('ABCD')}"
    d.facts = {"supplier": c["supplier"]}
    d.t("Da: ").p(c["email"], "EMAIL", c["id"]).t("\nA: ").p(b["email"], "EMAIL", b["id"])
    d.t("\nOggetto: non conformità lotto ").u(lot, "LOT").t("\n\nGentile ").t(b["title"] + " ").p(
        b["last"], "PERSON", b["id"])
    d.t(",\nvi segnaliamo che il lotto ").u(lot, "LOT").t(" del componente ").u(part, "PART")
    d.t(" presenta bave sul bordo. Per la nota di credito usate l'IBAN ").p(c["iban"], "IBAN", c["id"])
    d.t(".\n\nCordiali saluti,\n").p(f"{c['first']} {c['last']}", "PERSON", c["id"]).t("\n").u(
        c["supplier"], "SUPPLIER")
    d.t("\nTel. ").p(c["phone"], "PHONE", c["id"]).t("\n")
    return d


def incident(rng, i, workers, sups):
    d, w, s = Doc(f"I{i:04d}", "incident"), rng.choice(workers), rng.choice(sups)
    m = rng.choice(MACHINES)
    d.facts = {"worker": w["id"], "machine": m}
    d.t(f"Rapporto infortunio {d.id} del ").u(date(rng), "DATE").t("\nLavoratore: ")
    d.p(f"{w['first']} {w['last']}", "PERSON", w["id"]).t(", CF ").p(w["cf"], "TAX_CODE", w["id"])
    d.t(", matricola ").p(w["emp"], "EMPLOYEE_ID", w["id"]).t("\nReparto: ").u(rng.choice(DEPTS), "DEPT")
    d.t("; macchina ").u(m, "MACHINE").t("\nDinamica: durante il cambio stampo su ").u(m, "MACHINE")
    d.t(" il lavoratore ha riportato una contusione alla mano sinistra. Era presente il preposto ")
    name_form(rng, d, s, ("full", "title"))
    d.t(".\nAutomezzo aziendale coinvolto: targa ").p(plate(rng), "PLATE", f"V{i}")
    d.t("\nResidenza del lavoratore: ").p(w["address"], "ADDRESS", w["id"]).t("\n")
    return d


def handover(rng, i, techs):
    d = Doc(f"H{i:04d}", "shift_chat")
    a, b = rng.sample(techs, 2)
    m1, m2, err = rng.sample(MACHINES, 2) + [rng.choice(ERRORS)]
    d.t("[06:0" + str(rng.randint(0, 9)) + "] ").p(a["first"], "PERSON", a["id"]).t(": passo il turno, ")
    d.u(m1, "MACHINE").t(" ok, ").u(m2, "MACHINE").t(" in allarme ").u(err, "ERROR").t(". Se serve chiama ")
    name_form(rng, d, b, ("first", "full"))
    d.t(" al ").p(b["phone"], "PHONE", b["id"]).t(".\n")
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(Path(__file__).with_name("corpus.jsonl")))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    staff = make_people(rng, 36)
    techs, sups, buyers = staff[:20], staff[20:28], staff[28:]
    contacts = make_contacts(rng, 10)
    makers = [lambda i: ticket(rng, i, techs, sups), lambda i: supplier_mail(rng, i, contacts, buyers),
              lambda i: incident(rng, i, staff[:28], sups), lambda i: handover(rng, i, techs)]
    docs = [makers[i % 4](i).json() for i in range(a.n)]
    with open(a.out, "w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    n_pii = sum(len(d["pii"]) for d in docs)
    print(f"wrote {len(docs)} docs, {n_pii} PII spans, {sum(len(d['utility']) for d in docs)} utility tokens -> {a.out}")
    write_table(random.Random(a.seed + 1), staff, Path(a.out).with_name("registro_formazione.csv"))


def write_table(rng, staff, path):
    """A training register (CSV) that names the same people as the documents: tests cross-file consistency.
    Gold: registro_formazione.gold.json maps (row, column) -> {type, entity} for every personal cell."""
    import csv
    header = ["Matricola", "Cognome", "Nome", "Email", "Telefono", "Reparto", "Macchina", "Ore", "Note"]
    rows, gold = [], []
    for r in range(60):
        p, q = rng.choice(staff), rng.choice(staff)
        note = rng.choice(["", "", f"affiancato da {q['first']} {q['last']}", f"recupero con Ing. {q['last']}"])
        rows.append([p["emp"], p["last"], p["first"], p["email"], p["phone"], rng.choice(DEPTS),
                     rng.choice(MACHINES), str(rng.choice([4, 8, 16])), note])
        for c, typ in ((0, "EMPLOYEE_ID"), (1, "PERSON"), (2, "PERSON"), (3, "EMAIL"), (4, "PHONE")):
            gold.append({"row": r, "col": c, "type": typ, "entity": p["id"]})
        if note:
            gold.append({"row": r, "col": 8, "type": "PERSON", "entity": q["id"], "text": note})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([header] + rows)
    path.with_suffix(".gold.json").write_text(json.dumps(gold), encoding="utf-8")
    print(f"wrote table {path.name}: {len(rows)} rows, {len(gold)} personal cells")


if __name__ == "__main__":
    main()
