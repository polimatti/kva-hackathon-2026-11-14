"""Tables: column-aware pseudonymisation that shares identities with the text pipeline.

A column is personal when its header says so (Italian and English keywords); split name columns
(Cognome + Nome) are joined into one identity. Free-text columns go through the text detector.
Every value is resolved with the same Resolver and the same counters as the documents, so a person
gets the same PERSONA-nn in tickets, e-mails and the register.
"""
import re

HEADER_TYPES = [
    (r"^(cognome|surname|last ?name)$", "LAST"),
    (r"^(nome|first ?name|given ?name)$", "FIRST"),
    (r"(nominativo|cognome e nome|nome e cognome|full ?name|dipendente)", "PERSON"),
    (r"(e-?mail|posta)", "EMAIL"),
    (r"(telefono|tel\.?|cellulare|phone|mobile)", "PHONE"),
    (r"(matricola|employee ?id|badge)", "EMPLOYEE_ID"),
    (r"(codice fiscale|^cf$|tax ?code)", "TAX_CODE"),
    (r"^iban$", "IBAN"),
    (r"(indirizzo|residenza|domicilio|address)", "ADDRESS"),
    (r"(targa|plate)", "PLATE"),
    (r"(note|commento|descrizione|comment)", "FREE_TEXT"),
]


def classify(header):
    out = []
    for h in header:
        t = next((typ for rx, typ in HEADER_TYPES if re.search(rx, h.strip().lower())), None)
        out.append(t)
    return out


def table_texts(header, rows):
    """Texts the corpus-level learner should see: full names from split columns + free text cells."""
    types = classify(header)
    texts = []
    li, fi = (types.index("LAST") if "LAST" in types else None), (types.index("FIRST") if "FIRST" in types else None)
    for r in rows:
        if li is not None and fi is not None:
            texts.append(f"Nominativo: {r[fi]} {r[li]}")
        texts += [r[i] for i, t in enumerate(types) if t == "FREE_TEXT" and r[i]]
    return texts
