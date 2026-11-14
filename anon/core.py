"""Identity-preserving pseudonymisation for company documents before they reach a memory or a model.

Deterministic, stdlib only. Two passes over the whole corpus:
  1. detect PII spans (structured patterns + person-name rules + corpus-level coreference);
  2. resolve every person mention (full name, "Ing. Rossi", "M. Rossi", "Rossi", "Mario", e-mail) to one
     identity and replace it with a stable pseudonym, so cross-document links survive anonymisation.

Modes: "pseudo" (ours), "redact" (same detector, type tags only), "regex" (structured patterns only).
"""
import re
from collections import defaultdict

GAZ_FIRST = set("""Mario Luca Giulia Francesca Marco Andrea Paolo Sara Elena Matteo Chiara Davide Simone Laura Stefano
Federica Alessandro Valentina Roberto Silvia Giorgio Martina Fabio Anna Riccardo Giuseppe Giovanni Antonio Francesco
Maria Lucia Alessia Michele Lorenzo Gabriele Daniele Emanuele Claudia Paola Giorgia Alberto Enrico Nicola Pietro
Vittorio Carlo Roberta Monica Cristina Barbara Sergio Massimo Alessio Filippo Tommaso Beatrice Ilaria Elisa Irene
Franco Bruno Angelo Salvatore Vincenzo Raffaele Domenico Teresa Rosa Giovanna Patrizia Daniela Manuela""".split())
TITLES = r"(?:Ing\.|Dott\.ssa|Dott\.|Geom\.|Sig\.ra|Sig\.|Per\. Ind\.|Avv\.|Arch\.)"
CAP = r"[A-ZÀ-Ý][a-zà-ÿ']+"
STOP = {"Ticket", "Macchina", "Segnalato", "Descrizione", "Recapito", "Oggetto", "Gentile", "Cordiali", "Tel",
        "Rapporto", "Lavoratore", "Reparto", "Dinamica", "Era", "Automezzo", "Residenza", "Se", "Il", "La", "Da",
        "Per", "Via", "Corso", "Piazza", "Strada", "Torino"}

STRUCTURED = [  # (type, priority, regex) — lower priority wins on overlap
    ("ADDRESS", 0, re.compile(r"\b(?:Via|Viale|Corso|Piazza|Strada|Largo)\s[^\n,]{2,45}?\s\d{1,4}[A-Z]?,\s\d{5}\s" + CAP)),
    ("EMAIL", 1, re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("IBAN", 2, re.compile(r"\bIT(?:\s?[0-9A-Z]){25}\b")),
    ("TAX_CODE", 3, re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("EMPLOYEE_ID", 3, re.compile(r"\bMAT-\d{5}\b")),
    ("PLATE", 3, re.compile(r"\b[A-Z]{2}\d{3}[A-Z]{2}\b")),
    ("PHONE", 4, re.compile(r"(?<![\w-])(?:\+39\s?)?(?:3\d{2}[\s-]?\d{3}\s?\d{4}|0\d{1,3}\s\d{3}\s\d{4})(?![\w-])")),
]


def _structured(text):
    return [(m.start(), m.end(), t, p) for t, p, rx in STRUCTURED for m in rx.finditer(text)]


def _person_seed(text):
    """Rules that need no corpus knowledge. Returns spans and learned surnames."""
    spans, surnames = [], set()
    for m in re.finditer(rf"\b({CAP})\s({CAP})\b", text):  # Firstname Surname
        if m.group(1) in GAZ_FIRST and m.group(2) not in STOP:
            spans.append((m.start(), m.end())); surnames.add(m.group(2))
    for m in re.finditer(rf"{TITLES}\s({CAP})\b", text):  # Ing. Rossi
        if m.group(1) not in STOP:
            spans.append((m.start(1), m.end(1))); surnames.add(m.group(1))
    for m in re.finditer(rf"(?<![\w.])([A-Z])\.\s({CAP})\b", text):  # M. Rossi
        if m.group(2) not in STOP:
            spans.append((m.start(), m.end())); surnames.add(m.group(2))
    for m in re.finditer(rf"^\[\d\d:\d\d\]\s({CAP}):", text, re.M):  # chat speaker
        spans.append((m.start(1), m.end(1)))
    return spans, surnames


def _person_coref(text, surnames):
    spans = []
    if surnames:
        alt = "|".join(sorted(map(re.escape, surnames), key=len, reverse=True))
        for m in re.finditer(rf"(?:\b({CAP})\s)?\b({alt})\b", text):  # [Unknown-first] KnownSurname
            first = m.group(1)
            s = m.start() if first and first not in STOP else m.start(2)
            spans.append((s, m.end()))
    for m in re.finditer(rf"\b({CAP})\b", text):  # bare known first name
        if m.group(1) in GAZ_FIRST:
            spans.append((m.start(), m.end()))
    return spans


def _resolve_overlaps(cands):
    """Greedy: higher priority first, then longer; keep a span only if it overlaps nothing kept."""
    kept = []
    for c in sorted(cands, key=lambda c: (c[3], -(c[1] - c[0]), c[0])):
        if all(c[1] <= k[0] or c[0] >= k[1] for k in kept):
            kept.append(c)
    return sorted(kept)


def detect_corpus(texts, mode="pseudo"):
    """Return, per text, a list of (start, end, type) spans."""
    all_spans = []
    surnames = set()
    seeds = []
    for t in texts:
        sp, sn = _person_seed(t) if mode != "regex" else ([], set())
        seeds.append(sp); surnames |= sn
    for t, seed in zip(texts, seeds):
        cands = _structured(t)
        if mode != "regex":
            cands += [(s, e, "PERSON", 5) for s, e in seed + _person_coref(t, surnames)]
        all_spans.append([(s, e, typ) for s, e, typ, _ in _resolve_overlaps(cands)])
    return all_spans, surnames


def _parse_person(surface, surnames):
    toks = surface.replace(".", ". ").split()
    if len(toks) >= 2 and toks[0].endswith(".") and len(toks[0]) == 2:
        return toks[0][0], toks[-1], "initial"
    if len(toks) >= 2:
        return " ".join(toks[:-1]), toks[-1], "full"
    return (None, toks[0], "last") if toks[0] in surnames else (toks[0], None, "first")


class Resolver:
    """Maps every surface form of a person to one identity key, using the whole corpus."""

    def __init__(self, person_surfaces, emails, surnames):
        self.surnames = surnames
        self.full = self.fulls(person_surfaces, emails)

    def fulls(self, person_surfaces, emails):
        out = set()
        for s in person_surfaces:
            f, l, k = _parse_person(s, self.surnames)
            if k == "full":
                out.add((f, l))
        for e in emails:
            local = e.split("@")[0]
            if "." in local:
                a, b = local.split(".", 1)
                out.add((a.capitalize(), b.capitalize()))
        return out

    @staticmethod
    def _match(pool, first, last, kind):
        if kind == "initial":
            return [x for x in pool if x[1] == last and x[0].startswith(first)]
        if kind == "last":
            return [x for x in pool if x[1] == last]
        return [x for x in pool if x[0] == first]

    def key(self, first, last, kind, local=()):
        """Document-level coreference first, then corpus-level; ambiguous mentions keep their own key."""
        if kind == "full":
            return f"{last}|{first}"
        for pool in (local, self.full):
            c = self._match(pool, first, last, kind)
            if len(c) == 1:
                return f"{c[0][1]}|{c[0][0]}"
            if len(c) > 1:
                break
        return {"initial": f"{last}|{first}.", "last": f"{last}|?"}.get(kind, f"?|{first}")

    def person(self, surface, local=()):
        return self.key(*_parse_person(surface, self.surnames), local=local)

    def email(self, addr, local=()):
        loc = addr.split("@")[0]
        if "." in loc:
            a, b = loc.split(".", 1)
            return self.key(a.capitalize(), b.capitalize(), "full")
        return self.key(loc[0].upper(), loc[1:].capitalize(), "initial", local=local)


TAG = {"PERSON": "PERSONA", "EMAIL": "EMAIL", "PHONE": "TEL", "IBAN": "IBAN", "TAX_CODE": "CF",
       "EMPLOYEE_ID": "MATRICOLA", "PLATE": "TARGA", "ADDRESS": "INDIRIZZO"}


def anonymize_corpus(texts, mode="pseudo"):
    """Returns (anonymized_texts, spans_per_text, vault). Each span: dict(start,end,type,key,token)."""
    spans, surnames = detect_corpus(texts, mode)
    persons = [t[s:e] for t, sp in zip(texts, spans) for s, e, typ in sp if typ == "PERSON"]
    emails = [t[s:e] for t, sp in zip(texts, spans) for s, e, typ in sp if typ == "EMAIL"]
    res = Resolver(persons, emails, surnames)
    ids = defaultdict(dict)
    vault = defaultdict(set)
    out_texts, out_spans = [], []
    for t, sp in zip(texts, spans):
        buf, pos, rich = [], 0, []
        local = res.fulls([t[s:e] for s, e, ty in sp if ty == "PERSON"],
                          [t[s:e] for s, e, ty in sp if ty == "EMAIL"])
        for s, e, typ in sp:
            surface = t[s:e]
            if typ == "PERSON":
                key = res.person(surface, local)
            elif typ == "EMAIL":
                key = res.email(surface, local)
            else:
                key = re.sub(r"\s|[-+]", "", surface).upper()
            if mode == "pseudo":
                group = "PERSONA" if typ in ("PERSON", "EMAIL") else TAG[typ]
                n = ids[group].setdefault(key, len(ids[group]) + 1)
                token = f"[EMAIL PERSONA-{n:02d}]" if typ == "EMAIL" else f"[{TAG[typ]}-{n:02d}]"
                vault[token].add(surface)
            else:
                token = f"[{TAG[typ]}]"
            buf.append(t[pos:s]); buf.append(token); pos = e
            rich.append({"start": s, "end": e, "type": typ, "key": key if mode == "pseudo" else typ, "token": token})
        buf.append(t[pos:])
        out_texts.append("".join(buf)); out_spans.append(rich)
    return out_texts, out_spans, {k: sorted(v) for k, v in vault.items()}
