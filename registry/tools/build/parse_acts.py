"""Republika Srpska: laws of the National Assembly, as adopted and published in Službeni glasnik Republike Srpske.

Reads local copies of three official, free sources and writes corpus.d parts (SCHEMA.md in scripts/gitlaw_common).
Deterministic: the same inputs give the same bytes.

    python -X utf8 parse_acts.py --src <folder> [--report holds.jsonl] [--out corpus.d] [--antiword antiword]

Input (under --src):
- sg/issues.jsonl: the gazette publisher's (JU Službeni glasnik Republike Srpske) list of issues {"year", "slug",
  "title" (issue number, e.g. "078"), "date" (issue date, ISO)}; sg/fetched.jsonl {"slug", "sha256"} and
  sg/toc/<slug>.html.gz: each issue's table of contents (issuer headings and act titles, Cyrillic) from its free
  "Pregled" page.
- nsrs/index.jsonl: the National Assembly's list of adopted laws {"title", "sg" (gazette number, e.g. "78/26"),
  "date", "detail", "files"}; nsrs/fetched.jsonl {"url", "file", "sha256"} or {"url", "error"}; nsrs/zip/<file>: the
  attachment (a zip holding the adopted text as .docx or .doc).
- court/fetched.jsonl {"d", "case", "sha256"} and court/raw/<d>.html.gz: decisions of the Constitutional Court of
  Republika Srpska (ustavnisud.org), each decision's text block.
- erp/list.jsonl (every Republika Srpska law in the gazette publisher's Electronic Register of Regulations, eRP),
  erp/fetched.jsonl {"id"} and erp/detail/<id>.json.gz: each law's record (gazette issue, publication day, status
  "Aktivan"/"Neaktivan", and the acts that amended it, "povezaniPropisi").

What becomes an act here: a law the National Assembly adopted (its list gives the gazette number), whose title is in
that gazette issue's table of contents, in the text of the Assembly's file of the adopted law (signed by its
President), as one version in force on the day its own final article names, counted from the gazette issue date
("осмог дана од дана објављивања" = issue date + 8). The signature block below the text is cut.

2026-11-10 (romania-law standard): a law the sources report as changed later (the register, gazette titles, later
law texts or a court ruling, as listed below) is no longer held: it is published as enacted with "label"
("amended, not consolidated", or "repealed, not consolidated" when the register no longer lists it, records it as
not in force, or a later text repeals it) and "amended_by" ({ref, title, published, url}); labelled.jsonl beside the
report lists them. A later law citing an amending law is not a change. The rules below that are about later changes
now label instead of hold; the others still hold.

Before 2026-11-10, an act was held back, not published (the reason is written to the report), when:
- the register has no record of it at its gazette issue, or records it as no longer in force, or lists an act
  related to it (an amendment) published on or after it, or gives another publication day;
- a later title in any gazette issue's contents amends, repeals or corrects it (Закон о измјенама/допунама ... Закона
  о <its subject>, Закон о престанку важења ..., Исправка ...), unless that title names gazette numbers without its own;
- a later title in the contents is a law of the same (or a similar) name: a new law of that name replaces it;
- a later law text held cites it by name with its gazette number followed by later issues (its amendments), or in a
  sentence saying it ceases to be valid ("престаје да важи ..."); for an amending law, a later law text citing the
  amending law itself;
- a Constitutional Court decision whose ruling (the part before its reasons) finds provisions not in accordance with
  the Constitution, or says they cease to be valid, cites it by name and gazette number;
- its title is not of the form ЗАКОН О ... (codes are amended under other names);
- its own final article does not name a day this parser can read;
- its articles do not split cleanly (none, a number twice, numbers not consecutive, an empty article), the file uses
  Word's automatic numbering (its numbers are not in the text), or the signature block is missing (a draft).
An act is judged only when every gazette issue's contents and every Assembly law text dated on or after it, every
Constitutional Court decision and every register record is held.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import io
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTS = HERE / "corpus.d"
NSRS = "https://www.narodnaskupstinars.net"
ERP_PAGE = "https://erp.slglasnik.org/"


def erp_ref(x: dict) -> str:
    n = str(x.get("sluzbeniGlasnikBroj") or "").strip()
    n = str(int(n)) if n.isdigit() else n
    return f"{n}/{str(x.get('sluzbeniGlasnikGodina') or '')[2:]}"
CYR = dict(zip("абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ",
               ["a", "b", "v", "g", "d", "đ", "e", "ž", "z", "i", "j", "k", "l", "lj", "m", "n", "nj", "o", "p", "r",
                "s", "t", "ć", "u", "f", "h", "c", "č", "dž", "š",
                "A", "B", "V", "G", "D", "Đ", "E", "Ž", "Z", "I", "J", "K", "L", "Lj", "M", "N", "Nj", "O", "P", "R",
                "S", "T", "Ć", "U", "F", "H", "C", "Č", "Dž", "Š"]))
ASCII = {"a": "a", "b": "b", "v": "v", "g": "g", "d": "d", "đ": "dj", "e": "e", "ž": "z", "z": "z", "i": "i", "j": "j",
         "k": "k", "l": "l", "m": "m", "n": "n", "o": "o", "p": "p", "r": "r", "s": "s", "t": "t", "ć": "c", "u": "u",
         "f": "f", "h": "h", "c": "c", "č": "c", "š": "s"}
MONTHS = {m: i for i, m in enumerate(["januar", "februar", "mart", "april", "maj", "jun", "jul", "avgust",
                                       "septembar", "oktobar", "novembar", "decembar"], 1)}
MONTHS.update({"januara": 1, "februara": 2, "marta": 3, "aprila": 4, "maja": 5, "juna": 6, "jula": 7, "avgusta": 8,
               "septembra": 9, "oktobra": 10, "novembra": 11, "decembra": 12, "augusta": 8, "juni": 6, "juli": 7})
ORD = {"prvog": 1, "drugog": 2, "trećeg": 3, "četvrtog": 4, "petog": 5, "šestog": 6, "sedmog": 7, "osmog": 8,
       "devetog": 9, "desetog": 10, "petnaestog": 15, "dvadesetog": 20, "tridesetog": 30, "narednog": 1, "sljedećeg": 1}
ART = re.compile(r"^Члан\s+(\d+)\s*([а-ш])?\s*\.?$")
IN_FORCE = re.compile(r"(?:Ovaj|Ovo|Ova|Taj)\s+[Zz]akon\b[^.]{0,200}?\bstupa\s+na\s+snagu\s+([^.]*)")
AMEND_WORD = re.compile(r"\b(?:izmj?en\w*|dopun\w*|ispravk\w*|prestank\w*\s+važenja|prestanku\s+važnosti)\b")
CITE = re.compile(r"\b(Zakon|zakon)\w*\s+o\s+([^()\"]{3,250}?)\s*\(\s*\"?\s*Službeni\s+glasnik\s+Republike\s+Srpske\s*\"?"
                  r"\s*,?\s*(?:br\.|broj|br)\s*([^)]{1,300})\)")
REPEAL = re.compile(r"\bprestaj[eu]\s+(?:da\s+)?važi(?:ti)?\b|\bprestaj[eu]\s+važnost|\bstavlja(?:ju)?\s+se\s+van\s+snage|"
                    r"\bvan\s+snage\s+(?:se\s+)?stavlja")
SENTENCE_END = re.compile(r"(?<=[a-zčćžšđ)\"])\.\s+(?=[A-ZČĆŽŠĐ])|\bČlan\s+\d+\w?\.\s")


class Hold(Exception):
    pass


def norm(s: str) -> str:
    s = s.replace(" ", " ").replace("­", "").replace("\t", " ").replace("​", "")
    s = s.replace("–", "-").replace("—", "-").replace("„", '"').replace("“", '"').replace("”", '"')
    s = s.replace("«", '"').replace("»", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"[ \r\n\f\v]+", " ", s).strip()


HOMO = str.maketrans("AaBEeKkMHOoPpCcTXxyJj", "АаВЕеКкМНОоРрСсТХхуЈј")
CYR_LETTER = re.compile(r"[Ѐ-ӿ]")


def fix_homoglyphs(s: str) -> str:
    """Latin look-alike letters typed inside a Cyrillic word ("ЗAКOН", "Члaн") become the Cyrillic letters they look
    like; words in Latin script, and words mixing other Latin letters, are left as they are."""
    words = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[^\W\d_]+", s)]
    out, pos = [], 0
    for i, (a, b, w) in enumerate(words):
        new = w
        if CYR_LETTER.search(w) and re.search(r"[A-Za-z]", w) and not re.search(r"[^Ѐ-ӿAaBEeKkMHOoPpCcTXxyJj]", w):
            new = w.translate(HOMO)
        elif len(w) == 1 and w in "AaOoEeCcyKkJj" and 0 < i < len(words) - 1 and \
                all(CYR_LETTER.search(x[2]) and not re.search(r"[A-Za-z]", x[2]) for x in (words[i - 1], words[i + 1])):
            new = w.translate(HOMO)  # a one-letter word ("O") between Cyrillic words
        out.append(s[pos:a] + new)
        pos = b
    return "".join(out) + s[pos:]


def lat(s: str) -> str:
    """Latin transliteration (for matching only; the texts keep their script)."""
    return s.translate(CYR_TABLE)


CYR_TABLE = {ord(k): v for k, v in CYR.items()}


def subject(s: str) -> str:
    s = re.sub(r"\(\s*\"?\s*službeni\s+glasnik.*$", "", norm(lat(s)).lower())
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    return s[:80]


def own_subject(title: str) -> str | None:
    m = re.match(r"^zakon\s+o\s+(.+)$", norm(lat(title)).lower())
    return "zakon:" + subject(m.group(1)) if m else None


def target(title: str) -> tuple[str, list] | None:
    """(subject amended, repealed or corrected, gazette numbers the title names) of a title, or None."""
    t = norm(lat(title)).lower()
    m = AMEND_WORD.search(t)
    if not m:
        return None
    rest = t[m.end():]
    iss = issues_in(" ".join(re.findall(r"\(([^)]*službeni\s+glasnik[^)]*)\)", rest)))
    chain = r"^(?:\s+i\s+(?:izmj?en\w*|dopun\w*))*\s+"
    z = re.match(chain + r"(?:(?!zakon)\w+\s+){0,2}?zakon(?:a|u)?\s+o\s+(.+)$", rest)
    if z:
        return "zakon:" + subject(z.group(1)), iss
    k = re.match(chain + r"(\w+\s+zakonika?\b.*)$", rest)  # a code: Кривичног законика, Изборног закона
    if k:
        return "code:" + subject(k.group(1)), iss
    return None


def similar(a: str, b: str, n: int) -> bool:
    ka, sa = a.split(":", 1)
    kb, sb = b.split(":", 1)
    return ka == kb and (sa.startswith(sb[:n]) or sb.startswith(sa[:n]))


def issues_in(s: str) -> list[tuple[int, int]]:
    out = []
    for n, yy in re.findall(r"(?<![\d/])(\d{1,3})\s*/\s*(\d{2}|\d{4})(?!\d)", s):
        y = int(yy)
        y = y + (2000 if y < 50 else 1900) if y < 100 else y
        out.append((int(n), y))
    return out


def ascii_key(s: str) -> str:
    return "".join(ASCII.get(ch, "") for ch in lat(s).lower())


# ------------------------------------------------------------------ text of the adopted law
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_paras(data: bytes, strict: bool = True) -> list[tuple[str, bool | None]]:
    """(text, centred) per paragraph in body order; table rows as "cell | cell"."""
    import xml.etree.ElementTree as ET
    z = zipfile.ZipFile(io.BytesIO(data))
    root = ET.fromstring(z.read("word/document.xml"))
    styles, style_num = {}, {}
    if "word/styles.xml" in z.namelist():
        sr = ET.fromstring(z.read("word/styles.xml"))
        for s in sr.iter(W + "style"):
            jc = s.find(f"{W}pPr/{W}jc")
            styles[s.get(W + "styleId")] = jc.get(W + "val") if jc is not None else None
            np_ = s.find(f"{W}pPr/{W}numPr")
            if np_ is not None:
                style_num[s.get(W + "styleId")] = np_
    # Word's automatic numbering: the numbers are not in the text, so they are rendered here from numbering.xml
    # (decimal and Latin letter/Roman formats, and dash bullets); any other format holds the act.
    nums, abstracts = {}, {}
    if "word/numbering.xml" in z.namelist():
        nr = ET.fromstring(z.read("word/numbering.xml"))
        for an in nr.iter(W + "abstractNum"):
            lv = {}
            for l in an.findall(W + "lvl"):
                g = lambda tag: (l.find(W + tag).get(W + "val") if l.find(W + tag) is not None else None)
                lv[int(l.get(W + "ilvl"))] = {"fmt": g("numFmt") or "decimal", "text": g("lvlText"),
                                              "start": int(g("start") or 1), "suff": g("suff") or "tab"}
            abstracts[an.get(W + "abstractNumId")] = lv
        for n in nr.iter(W + "num"):
            a_ = n.find(W + "abstractNumId")
            over = {}
            for o in n.findall(W + "lvlOverride"):
                so = o.find(W + "startOverride")
                if so is not None:
                    over[int(o.get(W + "ilvl"))] = int(so.get(W + "val"))
            nums[n.get(W + "numId")] = (a_.get(W + "val") if a_ is not None else None, over)
    counters: dict[str, dict[int, int]] = {}

    def fmt(n: int, f: str) -> str:
        if f == "decimal":
            return str(n)
        if f in ("lowerLetter", "upperLetter"):
            s = chr(ord("a") + (n - 1) % 26) * ((n - 1) // 26 + 1)
            return s if f == "lowerLetter" else s.upper()
        if f in ("lowerRoman", "upperRoman"):
            r, v = "", n
            for val, sym in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
                             (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
                while v >= val:
                    r, v = r + sym, v - val
            return r if f == "lowerRoman" else r.upper()
        raise Hold("automatic_numbering:" + f)

    def label(p) -> str:
        np_ = p.find(f"{W}pPr/{W}numPr")
        if np_ is None:
            st = p.find(f"{W}pPr/{W}pStyle")
            np_ = style_num.get(st.get(W + "val")) if st is not None else None
        if np_ is None:
            return ""
        nid = np_.find(W + "numId")
        nid = nid.get(W + "val") if nid is not None else None
        il = np_.find(W + "ilvl")
        il = int(il.get(W + "val")) if il is not None else 0
        if nid in (None, "0"):
            return ""
        if not strict:
            return ""
        if nid not in nums or nums[nid][0] not in abstracts or il not in abstracts[nums[nid][0]]:
            raise Hold("automatic_numbering:undefined")
        lv = abstracts[nums[nid][0]]
        c = counters.setdefault(nid, {})
        start = nums[nid][1].get(il, lv[il]["start"])
        c[il] = c[il] + 1 if il in c else start
        for deeper in [k for k in c if k > il]:
            del c[deeper]
        d = lv[il]
        if d["fmt"] == "bullet":
            if d["text"] not in ("-", "–", "—"):
                raise Hold("automatic_numbering:bullet")
            txt = "-"
        elif d["fmt"] == "none":
            return ""
        else:
            txt = d["text"] or ""
            for k in range(9):
                if f"%{k + 1}" in txt:
                    if k not in c and k in lv:
                        c[k] = nums[nid][1].get(k, lv[k]["start"])
                    txt = txt.replace(f"%{k + 1}", fmt(c.get(k, 1), lv.get(k, d)["fmt"]))
        return txt + ("" if d["suff"] == "nothing" else " ")

    body = root.find(W + "body")
    out = []

    def ptext(p):
        parts = [label(p)]
        for el in p.iter():
            if el.tag == W + "t":
                parts.append(el.text or "")
            elif el.tag in (W + "tab",):
                parts.append(" ")
            elif el.tag in (W + "br", W + "cr"):
                parts.append("\n")
            elif el.tag == W + "delText":
                pass
        return "".join(parts)

    def centred(p):
        jc = p.find(f"{W}pPr/{W}jc")
        if jc is not None:
            return jc.get(W + "val") == "center"
        st = p.find(f"{W}pPr/{W}pStyle")
        return styles.get(st.get(W + "val") if st is not None else "Normal") == "center"

    for el in body:
        if el.tag == W + "p":
            if strict and (el.find(f".//{W}ins") is not None or el.find(f".//{W}del") is not None):
                raise Hold("tracked_changes")
            for line in ptext(el).split("\n"):
                out.append((line, centred(el)))
        elif el.tag == W + "tbl":
            for tr in el.iter(W + "tr"):
                cells = [" ".join(ptext(p) for p in tc.iter(W + "p")) for tc in tr.findall(W + "tc")]
                out.append((" | ".join(norm(c) for c in cells), False))
    return out


def doc_paras(data: bytes, antiword: str) -> list[tuple[str, bool | None]]:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.doc"
        f.write_bytes(data)
        p = subprocess.run([antiword, "-m", "UTF-8.txt", "-w", "0", str(f)], capture_output=True)
    if p.returncode:
        raise Hold("doc_unreadable")
    return [(line, None) for line in p.stdout.decode("utf-8", "replace").split("\n")]


def paragraphs(zbytes: bytes, antiword: str, strict: bool = True) -> list[tuple[str, bool | None]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(zbytes))
    except zipfile.BadZipFile:
        raise Hold("attachment_not_zip")
    docs = [i for i in z.infolist() if not i.is_dir() and re.search(r"\.(docx|doc)$", i.filename, re.I)
            and not i.filename.split("/")[-1].startswith(("~$", "._"))]
    others = [i for i in z.infolist() if not i.is_dir() and i not in docs and not i.filename.startswith("__MACOSX")]
    if len(docs) != 1:
        raise Hold(f"attachment_files:{len(docs)}+{len(others)}")
    data = z.read(docs[0])
    if docs[0].filename.lower().endswith(".docx"):
        try:
            return docx_paras(data, strict)
        except (KeyError, zipfile.BadZipFile):
            raise Hold("docx_unreadable")
    if data[:4] == b"PK\x03\x04":
        return docx_paras(data, strict)
    return doc_paras(data, antiword)


def is_upper(s: str) -> bool:
    letters = re.findall(r"[^\W\d_]", s)
    return bool(letters) and all(ch == ch.upper() for ch in letters) and len(letters) >= 3


def split(paras: list[tuple[str, bool | None]]) -> tuple[dict, str, str | None]:
    """(units, title, adoption day) from the adopted law's paragraphs."""
    lines = [(fix_homoglyphs(norm(t)), c) for t, c in paras]
    lines = [(t, c) for t, c in lines if t]
    # The signature block: "Број: ...", "Датум: ...", ПРЕДСЈЕДНИК НАРОДНЕ СКУПШТИНЕ.
    sig = None
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"^Број\s*:", lines[i][0]):
            sig = i
            break
    if sig is not None and sig > 0 and re.fullmatch(r"ПРЕДСЈЕДНИК", lines[sig - 1][0].upper()):
        sig -= 1  # "ПРЕДСЈЕДНИК" set on the line above "Број: ..."
    if sig is None or not any("ПРЕДСЈЕДНИК" in t.upper() for t, _ in lines[sig:]):
        raise Hold("no_assembly_signature")
    tail = " ".join(t for t, _ in lines[sig:])
    lines = lines[:sig]
    m = re.search(r"Датум\s*:?\s*(\d{1,2})\.\s*([а-ш]+)\s+(\d{4})", tail)
    adopted = None
    if m and lat(m.group(2)).lower() in MONTHS:
        adopted = date(int(m.group(3)), MONTHS[lat(m.group(2)).lower()], int(m.group(1))).isoformat()
    else:
        m = re.search(r"Датум\s*:?\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", tail)
        if m:
            adopted = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    # Title: the upper-case lines from ЗАКОН up to the first other line.
    k = 0
    pre = []
    while k < len(lines) and not lines[k][0].upper().startswith("ЗАКОН"):
        pre.append(lines[k][0])
        k += 1
    title_parts = []
    while k < len(lines) and is_upper(lines[k][0]) and not ART.match(lines[k][0]) and \
            not (title_parts and re.match(r"^(?:ГЛАВА|ДИО|ДЈЕЛОВИ|ОДЈЕЉАК|ПОГЛАВЉЕ|ОДСЈЕК|[IVXLCDM]+\b|[0-9]+\.)", lines[k][0])):
        title_parts.append(lines[k][0])
        k += 1
    if not title_parts:
        raise Hold("no_title")
    title = norm(" ".join(title_parts))
    units: dict[str, dict] = {}
    order: list[str] = []
    pending: list[tuple[str, bool | None]] = []
    cur = None
    in_q = False
    own_n = 0

    def flush_pending_into(article_key):
        """Lines waiting before an article heading: upper-case ones are headings, the last plain short ones its
        caption (with alignment known: the centred ones)."""
        nonlocal pending
        cap = []
        while pending:
            t, c = pending[-1]
            plain = not is_upper(t) and len(t) < 200 and not re.search(r"[.;:,]$", t) and \
                not re.match(r"^(?:\(?\d+\)|[а-ш]\)|-|\")", t) and (c is None or c)
            if plain and len(cap) < 3:
                cap.insert(0, t)
                pending.pop()
            else:
                break
        heads = []
        for t, c in pending:
            if is_upper(t) or (c and cur is not None):
                heads.append(t)
            elif cur is not None:
                units[cur]["lines"].append(t)  # a body line of the article before
                units[cur]["body"] += 1
            else:
                raise Hold("text_before_first_article")
        for j, h in enumerate(heads, 1):
            hk = f"{cur}-zz-heading-{j}" if cur else f"0-heading-{j}"
            units[hk] = {"label": h, "kind": "heading", "lines": [f"# {h}"]}
            order.append(hk)
        pending = []
        return cap

    for t, c in lines[k:]:
        q_before = in_q
        if t.count('"') % 2:
            in_q = not in_q
        m = ART.match(t)
        if m and not q_before and cur is not None and not units[cur]["body"] and not pending:
            raise Hold(f"empty_article:{cur}")
        if m and not q_before:
            n, sfx = int(m.group(1)), m.group(2)
            key = f"clan-{n:03d}" + (f"-{ascii_key(sfx)}" if sfx else "")
            if key in units:
                raise Hold(f"duplicate_unit:{key}")
            if not sfx:
                if n != own_n + 1:
                    raise Hold("article_numbers_not_consecutive")
                own_n = n
            cap = flush_pending_into(key)
            label = f"Члан {n}{sfx or ''}."
            units[key] = {"label": label, "kind": "art", "lines": [f"# {label}"] + cap, "body": 0}
            order.append(key)
            cur = key
            continue
        if q_before or cur is None:
            if cur is None:
                pending.append((t, c))
            else:
                if pending:
                    units[cur]["lines"].extend(x for x, _ in pending)
                    pending = []
                units[cur]["lines"].append(t)
                units[cur]["body"] += 1
            continue
        # outside quotation marks, after an article heading: body text, or a heading/caption of what follows
        if is_upper(t) or (c and len(t) < 200 and not re.search(r"[.;:,]$", t)) or \
                (c is None and len(t) < 120 and not re.search(r"[.;:,]$", t) and not re.match(r"^(?:\(?\d+\)|[а-ш]\)|-|\")", t)):
            pending.append((t, c))
            continue
        if pending:
            units[cur]["lines"].extend(x for x, _ in pending)
            pending = []
        units[cur]["lines"].append(t)
        units[cur]["body"] += 1
    if in_q:
        raise Hold("quotation_marks_unbalanced")
    if cur is None:
        raise Hold("no_articles")
    if pending:
        if any(is_upper(x) for x, _ in pending):
            raise Hold("heading_after_last_article")
        units[cur]["lines"].extend(x for x, _ in pending)
        units[cur]["body"] += len(pending)
    out = {}
    if pre:
        if any(re.search(r"НАЦРТ|ПРИЈЕДЛОГ|ПРЕДЛОГ", x.upper()) for x in pre):
            raise Hold("draft")
        out["uvod"] = {"label": "Увод", "kind": "preamble", "text": "\n".join(pre) + "\n"}
    for key in order:
        u = units[key]
        if u["kind"] == "art" and not u["body"]:
            raise Hold(f"empty_article:{key}")
        out[key] = {"label": u["label"], "kind": u["kind"], "text": "\n".join(u["lines"]) + "\n"}
    return out, title, adopted


# ------------------------------------------------------------------ in-force day
def in_force(units: dict, published: str, adopted: str | None) -> tuple[str, str]:
    arts = [lat(u["text"]).replace("\n", " ") for u in units.values() if u["kind"] == "art"]
    text = " ".join(arts)
    clauses = [m for m in IN_FORCE.finditer(text) if text.count('"', 0, m.start()) % 2 == 0]
    if not clauses:
        raise Hold("in_force_clause_missing")
    m = clauses[-1]
    c = m.group(1).strip()
    full = text[m.start(1):m.start(1) + 160]
    try:
        return read_day(c, published, adopted)
    except Hold as h:
        if not str(h).startswith("in_force_unreadable"):
            raise
        return read_day(variants(full), published, adopted)


def variants(c: str) -> str:
    c = c.strip()
    c = re.sub(r"\bobjave\b", "objavljivanja", c)
    c = re.sub(r"^(\w+)\s*\(\s*(?:\d+|osam|osmi|osmog)\s*\)", r"\1", c)
    c = re.sub(r"^(?:osam|osmi)\s+dana?\b", "osmog dana", c)
    c = re.sub(r"^prvi\s+dan\b", "prvog dana", c)
    c = re.sub(r"^dan\s+nakon\b", "prvog dana nakon", c)
    c = re.sub(r"\bdana\s+od\s+objavljivanja\b", "dana od dana objavljivanja", c)
    return c


def read_day(c: str, published: str, adopted: str | None) -> tuple[str, str]:
    c = re.sub(r"\bobjave\b", "objavljivanja", c)
    p = date.fromisoformat(published)
    if re.match(r"^(?:danom|na\s+dan|s\s+danom|sa\s+danom)\s+(?:njegovog\s+|njegova\s+)?objavljivanja", c):
        return published, "publication"
    m = re.match(r"^(" + "|".join(ORD) + r")a?\s+dana\s+(?:od\s+dana|nakon|po|poslije)\s+(?:njegovog\s+|njegova\s+)?objavljivanja", c)
    if m:
        return (p + timedelta(days=ORD[m.group(1)])).isoformat(), "days"
    m = re.match(r"^(\d{1,3})\s*\.?\s*(?:dana|dan)\s+(?:od\s+dana|nakon|po|poslije)\s+(?:njegovog\s+)?objavljivanja", c)
    if m:
        return (p + timedelta(days=int(m.group(1)))).isoformat(), "days"
    m = re.match(r"^(?:dana\s+|s\s+|sa\s+|od\s+)?(\d{1,2})\.\s*(" + "|".join(MONTHS) + r")\s+(\d{4})", c) or \
        re.match(r"^(?:dana\s+|s\s+|sa\s+|od\s+)?(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", c)
    if m:
        mo = MONTHS.get(m.group(2)) or int(m.group(2))
        d = date(int(m.group(3)), mo, int(m.group(1))).isoformat()
        if d < published:
            raise Hold(f"in_force_before_publication:{d}")
        return d, "date"
    raise Hold("in_force_unreadable:" + c[:100])


def repeal_sentence(flat: str, start: int, end: int) -> bool:
    if re.search(r"(?:stupanja|stupanjem)\s+na\s+snagu\s*$|primjen\w*\s*$", flat[max(0, start - 40):start]):
        return False
    a = max(0, start - 400)
    b = min(len(flat), end + 200)
    before = [m.end() for m in SENTENCE_END.finditer(flat, a, start)]
    after = SENTENCE_END.search(flat, end, b)
    s, e = (before[-1] if before else a), (after.start() if after else b)
    return bool(REPEAL.search(flat[s:e]))


# ------------------------------------------------------------------ gazette contents
def toc_lines(raw: str) -> list[str]:
    raw = re.sub(r"<title>.*?</title>", "", raw, flags=re.S)
    raw = re.sub(r"<br\b[^>]*>|</?(?:p|div|li|tr|h\d)\b[^>]*>", "\n", raw, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return [x for x in (norm(l) for l in t.split("\n")) if x]


COUNTRY = {
    "code": "BA-SRP", "name": "Republika Srpska", "slug": "bosnia-republika-srpska", "lang": "sr-Cyrl",
    "tz": "Europe/Sarajevo", "future_branch": "buducnost",
    "publisher": {"name": "Narodna skupština Republike Srpske (narodnaskupstinars.net)",
                  "email": "akti@narodnaskupstinars.net.invalid"},
    "default_in_force_rule": {
        "text": "Each law of Republika Srpska names its own day in its final article, almost always the eighth day "
                "after its publication in Službeni glasnik Republike Srpske; that day is used, counted from the issue "
                "date the gazette publisher gives.",
        "source": "https://online.slglasnik.org/sr/pregled"},
    "licence_note": "Official texts of laws are not protected by copyright in Bosnia and Herzegovina. Texts from the "
                    "National Assembly of Republika Srpska (narodnaskupstinars.net); gazette issue dates and contents "
                    "from JU Službeni glasnik Republike Srpske (slglasnik.org)."}


def read_jsonl(f: Path) -> list[dict]:
    out = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out", help="folder for the parts (default corpus.d beside this script)")
    ap.add_argument("--antiword", default="antiword", help="antiword executable, for .doc files")
    ap.add_argument("--cache", help="file to keep each text's reading between runs (same input and parser = same)")
    a = ap.parse_args()
    src = Path(a.src)
    me = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    cache, new_cache = {}, {}
    if a.cache and Path(a.cache).exists():
        try:
            c = json.loads(gzip.decompress(Path(a.cache).read_bytes()).decode("utf-8"))
            cache = c["entries"] if c.get("parser") == me else {}
        except Exception:
            cache = {}

    # Gazette issues (main series: numbered issues) and their contents.
    issues = {}
    for r in read_jsonl(src / "sg" / "issues.jsonl"):
        if re.fullmatch(r"\d{1,3}", r["title"].strip()) and r.get("date"):
            issues[(int(r["title"]), int(r["year"]))] = r
    sg_fetched = {r["slug"]: r for r in read_jsonl(src / "sg" / "fetched.jsonl")}
    toc: dict[tuple[int, int], list[tuple[str, str]]] = {}  # issue -> [(issuer heading, title)]
    for key, r in issues.items():
        if r["slug"] not in sg_fetched:
            continue
        ck = f"toc:{r['slug']}:{sg_fetched[r['slug']]['sha256']}"
        if ck in cache:
            new_cache[ck] = cache[ck]
            toc[key] = [tuple(x) for x in cache[ck]]
            continue
        f = src / "sg" / "toc" / f"{r['slug']}.html.gz"
        if not f.exists():
            continue
        head, rows = "", []
        for line in toc_lines(gzip.decompress(f.read_bytes()).decode("utf-8", "replace")):
            if is_upper(line) and not re.match(r"^(?:ЗАКОН|ZAKON)\b", line.upper()):
                head = line
            else:
                rows.append((head, line))
        toc[key] = rows
        new_cache[ck] = rows
    sg_missing_days = [r["date"] for k, r in issues.items() if k not in toc]
    sg_complete_from = max(sg_missing_days, default="0000")

    # Later titles: amending/repealing/correcting titles by target subject; law titles by own subject.
    named: dict[str, list[tuple[str, tuple, list]]] = defaultdict(list)
    same: dict[str, list[tuple[str, tuple]]] = defaultdict(list)
    early: dict[str, list[str]] = defaultdict(list)  # "Одлука о пријевременом ступању на снагу Закона о ..."
    for key, rows in toc.items():
        d = issues[key]["date"]
        for head, t in rows:
            e = re.search(r"stupanju\s+na\s+snagu\s+zakona\s+o\s+(.+)$", norm(lat(t)).lower())
            if e:
                early["zakon:" + subject(e.group(1))].append(d)
                continue
            tg = target(t)
            if tg:
                named[tg[0]].append((d, key, tg[1]))
            s = own_subject(t)
            if s and not tg:
                same[s].append((d, key))

    # National Assembly laws and their texts.
    ns_rows = read_jsonl(src / "nsrs" / "index.jsonl")
    ns_fetched = {}
    for r in read_jsonl(src / "nsrs" / "fetched.jsonl"):
        if r.get("file") or r.get("url") not in ns_fetched:
            ns_fetched[r["url"]] = r
    laws = []
    for r in ns_rows:
        if not norm(r["title"]).lower().startswith(("закон", "zakon")):
            continue
        sg = re.sub(r"\s+", "", r.get("sg") or "")
        iss = issues_in(sg)
        if not iss and re.fullmatch(r"\d{1,3}", sg) and r.get("date"):
            iss = [(int(sg), int(r["date"][:4]))]
        r = dict(r)
        r["iss"] = iss
        r["gdate"] = issues[iss[0]]["date"] if len(iss) == 1 and iss[0] in issues else None
        r["src_id"] = r.get("detail") or (r["files"][0] if r["files"] else r["title"])
        laws.append(r)

    # Each fetched text: its reading (units, title, adoption day) and its citations, cached by content.
    texts = {}
    cites: dict[tuple[str, int, int], list[tuple]] = defaultdict(list)
    missing_text_days = []
    for r in laws:
        f = r["files"][0] if r["files"] else None
        fr = ns_fetched.get(f) if f else None
        if f and not (fr and fr.get("file")):
            if not (fr and fr.get("error") == "404") and r["gdate"]:
                missing_text_days.append(r["gdate"])
            continue
        if not f:
            continue
        ck = f"{f}:{fr['sha256']}"
        if ck in cache:
            res = cache[ck]
        else:
            try:
                data = (src / "nsrs" / "zip" / fr["file"]).read_bytes()
                units, title, adopted = split(paragraphs(data, a.antiword))
                res = {"units": units, "title": title, "adopted": adopted}
            except Hold as h:
                res = {"hold": str(h)}
                try:
                    data = (src / "nsrs" / "zip" / fr["file"]).read_bytes()
                    flat_src = "\n".join(t for t, _ in paragraphs(data, a.antiword, strict=False))
                except Hold:
                    flat_src = ""
                res["flat"] = flat_src
            if "units" in res:
                res["flat"] = "\n".join(u["text"] for u in res["units"].values())
            found = []
            flat = norm(lat(res["flat"]))
            for m in CITE.finditer(flat):
                lst = issues_in(m.group(3))
                rep = repeal_sentence(flat, m.start(), m.end())
                for k2, (n_, y_) in enumerate(lst):
                    found.append(["zakon:" + subject(m.group(2)), n_, y_, len(lst) - k2 - 1, rep])
            res["cites"] = found
            del res["flat"]
        new_cache[ck] = res
        texts[r["src_id"]] = (r, fr, res)
        for s, n_, y_, after, rep in res["cites"]:
            cites[(s, n_, y_)].append((r["gdate"] or "9999", "law", r["src_id"], after, rep))
    ns_complete_from = max(missing_text_days, default="0000")

    # Constitutional Court decisions: provisions found not in accordance with the Constitution, or ceasing to be valid.
    court_rows = read_jsonl(src / "court" / "fetched.jsonl")
    court_have = {r["d"] for r in court_rows}
    court_complete = bool(court_have) and set(range(1, max(court_have) + 1)) <= court_have
    struck: dict[tuple[str, int, int], list[str]] = defaultdict(list)
    for r in court_rows:
        if not r.get("sha256"):
            continue
        ck = f"court:{r['d']}:{r['sha256']}"
        if ck in cache:
            found = cache[ck]
        else:
            page = gzip.decompress((src / "court" / "raw" / f"{r['d']}.html.gz").read_bytes()).decode("utf-8", "replace")
            flat = norm(lat(html.unescape(re.sub(r"<[^>]+>", " ", page))))
            ob = re.search(r"O\s?b\s?r\s?a\s?z\s?l\s?o\s?ž\s?e\s?n\s?j\s?e", flat)
            operative = flat[:ob.start()] if ob else flat[:3000]
            # the ruling starts after "донио је ОДЛУКУ" (the preamble names the laws the court acts under)
            od = re.search(r"O\s?D\s?L\s?U\s?K\s?U|R\s?J\s?E\s?Š\s?E\s?NJ\s?E", operative)
            operative = operative[od.end():] if od else operative
            found = []
            # each sentence of the ruling that finds provisions unconstitutional or ends them: the laws it cites
            for sent in re.split(r"(?<=[a-zčćžšđ)\"])\.\s+(?=[A-ZČĆŽŠĐ])", operative):
                v = re.search(r"\bni(?:je|su)\s+u\s+saglasnosti|\bprestaj[eu]\s+(?:da\s+)?važi|\bukida(?:ju)?\s+se\b", sent)
                if v:
                    # 2026-11-10: only a law named before the finding is the act found unconstitutional; one named
                    # after it ("... is not in accordance with the Constitution and the Law on X") is the yardstick
                    for m in CITE.finditer(sent[:v.start()]):
                        for n_, y_ in issues_in(m.group(3)):
                            found.append(["zakon:" + subject(m.group(2)), n_, y_])
        new_cache[ck] = found
        for s, n_, y_ in found:
            struck[(s, n_, y_)].append(r.get("case") or str(r["d"]))

    # The gazette publisher's register (eRP): each law's status and the acts that amended it.
    erp_list = read_jsonl(src / "erp" / "list.jsonl")
    erp_fetched = {r["id"]: r for r in read_jsonl(src / "erp" / "fetched.jsonl")}
    erp_complete = bool(erp_list) and all(r["id"] in erp_fetched for r in erp_list)
    register: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in erp_list:
        if r["id"] not in erp_fetched:
            continue
        ck = f"erp:{r['id']}:{erp_fetched[r['id']]['sha256']}"
        if ck in cache:
            d = cache[ck]
        else:
            f = src / "erp" / "detail" / f"{r['id']}.json.gz"
            if not f.exists():
                continue
            d = json.loads(gzip.decompress(f.read_bytes()).decode("utf-8"))
            d = {k: d.get(k) for k in ("naslov", "statusPropisa", "datumObjave", "sluzbeniGlasnikBroj",
                                       "sluzbeniGlasnikGodina", "povezaniPropisi")}
        new_cache[ck] = d
        rel = d.get("povezaniPropisi") or []
        try:
            register[(int(d["sluzbeniGlasnikBroj"]), int(d["sluzbeniGlasnikGodina"]))].append(
                {"title": d["naslov"], "status": d.get("statusPropisa"), "published": d.get("datumObjave"),
                 "related": [(x.get("datumObjave") or "", x.get("naslov", "")) for x in rel], "derived": False,
                 "related_refs": [{"ref": erp_ref(x), "title": norm(x.get("naslov", "")), "published": x.get("datumObjave"),
                                   "url": ERP_PAGE + x["eli"] if x.get("eli") else None} for x in rel]})
        except (KeyError, ValueError):
            pass
        for x in rel:
            try:
                register[(int(x["sluzbeniGlasnikBroj"]), int(x["sluzbeniGlasnikGodina"]))].append(
                    {"title": x["naslov"], "status": x.get("statusPropisa"), "published": x.get("datumObjave"),
                     "related": [], "derived": True})
            except (KeyError, ValueError):
                pass

    def same_title(a_: str, b_: str) -> bool:
        x, y = re.sub(r"\W+", "", lat(a_).lower()), re.sub(r"\W+", "", lat(b_).lower())
        if x == y or (len(y) > 30 and len(x) > 30 and (x.startswith(y) or y.startswith(x))):
            return True
        sm = SequenceMatcher(None, x, y)
        return sm.real_quick_ratio() > 0.93 and sm.quick_ratio() > 0.93 and sm.ratio() > 0.93

    cites_at, struck_at = defaultdict(list), defaultdict(list)  # by cited issue
    for (s2, n_, y_), lst in cites.items():
        cites_at[(n_, y_)].append((s2, lst))
    for (s2, n_, y_), cs in struck.items():
        struck_at[(n_, y_)].append((s2, cs))

    # The Assembly's list sometimes shows one law twice (same issue, same title): one act, from the first listing.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in laws:
        if len(r["iss"]) == 1:
            groups[(r["iss"][0], re.sub(r"\W+", "", lat(r["title"]).lower()))].append(r)

    def dup_status(r: dict) -> str | None:
        g = groups.get((r["iss"][0], re.sub(r"\W+", "", lat(r["title"]).lower())), []) if len(r["iss"]) == 1 else []
        if len(g) < 2:
            return None
        bodies = {json.dumps(texts[x["src_id"]][2].get("units"), sort_keys=True) for x in g if x["src_id"] in texts}
        if len(bodies) > 1 or any(x["files"] and x["src_id"] not in texts for x in g):
            return "duplicate_listing_differs"
        first = min(x["src_id"] for x in g if x["src_id"] in texts)
        return None if r["src_id"] == first else "duplicate_listing:" + first[-60:]

    def gz_ref(k2: tuple, t: str, d: str) -> dict:
        slug_ = issues[k2]["slug"] if k2 in issues else None
        return {"ref": f"{k2[0]}/{str(k2[1])[2:]}", "title": fix_homoglyphs(norm(t)), "published": d,
                "url": f"https://online.slglasnik.org/sr/propisi/{slug_}" if slug_ else None}

    def named_refs(subj_: str, own_: tuple, pub_: str, prefix: int) -> list:
        out_ = []
        for k2, rows_ in toc.items():
            d2 = issues[k2]["date"]
            if d2 < pub_ or k2 == own_:
                continue
            for h_, t_ in rows_:
                tg_ = target(t_)
                if tg_ and (tg_[0] == subj_ or similar(tg_[0], subj_, prefix)) and (not tg_[1] or own_ in tg_[1]):
                    out_.append(gz_ref(k2, t_, d2))
        return out_

    def same_refs(subj_: str, own_: tuple, pub_: str) -> list:
        out_ = []
        for k2, rows_ in toc.items():
            d2 = issues[k2]["date"]
            if d2 < pub_ or k2 == own_:
                continue
            for h_, t_ in rows_:
                s_ = own_subject(t_)
                if s_ and not target(t_) and (s_ == subj_ or similar(s_, subj_, 50)):
                    out_.append(gz_ref(k2, t_, d2))
        return out_

    holds = []
    labelled = []
    parts: dict[int, dict] = defaultdict(lambda: {"laws": {}, "acts": []})
    seen = set()
    for r in sorted(laws, key=lambda x: (x["gdate"] or "", x["src_id"])):
        title = norm(r["title"])
        rec = {"src": r["src_id"], "sg": r.get("sg"), "date": r["gdate"], "title": title[:160]}
        try:
            if not r["files"]:
                raise Hold("no_text_attachment")
            if len(r["iss"]) != 1:
                raise Hold("gazette_number:" + str(r.get("sg"))[:40])
            own = r["iss"][0]
            if own not in issues:
                raise Hold(f"gazette_issue_unknown:{own[0]}/{own[1]}")
            pub = r["gdate"]
            if own not in toc:
                raise Hold("awaiting_gazette_contents")
            if r["src_id"] not in texts:
                raise Hold("text_not_fetched")
            if pub <= sg_complete_from:
                raise Hold("awaiting_gazette_contents:" + sg_complete_from)
            if pub <= ns_complete_from:
                raise Hold("awaiting_later_texts:" + ns_complete_from)
            if not court_complete:
                raise Hold("awaiting_court_decisions")
            if not erp_complete:
                raise Hold("awaiting_register")
            _, fr, res = texts[r["src_id"]]
            if "hold" in res:
                raise Hold(res["hold"])
            dup = dup_status(r)
            if dup:
                raise Hold(dup)
            units, text_title, adopted = res["units"], res["title"], res["adopted"]
            # the law is in its gazette issue's contents
            # the law in its gazette issue's contents; that title (the gazette's) must be the text's own title
            key_ = lambda s_: re.sub(r"\W+", "", lat(s_).lower())
            cands = sorted(((SequenceMatcher(None, key_(t), key_(title)).ratio(), t) for h, t in toc[own]
                            if same_title(t, title)), reverse=True)
            if not cands:
                raise Hold("not_in_gazette_contents")
            title = fix_homoglyphs(norm(cands[0][1]))
            if key_(text_title) != key_(title):
                raise Hold("title_mismatch:" + text_title[:100])
            # the register's record of it: in force, never amended since, same publication day
            recs = [x for x in register.get(own, []) if same_title(x["title"], title)]
            # 2026-11-10 (romania-law standard): a law changed later is published as enacted and labelled, not held.
            changed, gone, by = [], False, []
            if not recs:
                gone = True
                changed.append("not_in_register")
            elif any(x["status"] != "Aktivan" for x in recs):
                gone = True
                changed.append("register_not_in_force")
            if any(x["published"] and x["published"] != pub for x in recs):
                raise Hold("register_date_differs:" + ",".join(sorted({x["published"] for x in recs if x["published"]})))
            later_rel = sorted({d for x in recs for d, t in x["related"] if d >= pub or not d})
            if later_rel:
                changed.append("register_amended:" + ",".join(later_rel[:3]))
                seen_ref = set()
                for x in recs:
                    for rr in x.get("related_refs", []):
                        if (rr["published"] or "") >= pub and rr["ref"] not in seen_ref:
                            seen_ref.add(rr["ref"])
                            by.append(rr)
            if adopted and not (adopted <= pub <= (date.fromisoformat(adopted) + timedelta(days=180)).isoformat()):
                raise Hold(f"adoption_day_inconsistent:{adopted}")
            tg = target(title)
            subj = own_subject(title)
            own_key = "zakon:" + subject(re.sub(r"^(?:закон|zakon)\s+(?:о|o)\s+", "", lat(title), flags=re.I))
            # a decision on early entry into force concerns this law only within its own eight days (a later one of
            # the same title concerns a later amending law of that name, 2026-11-10)
            ear = [d for d in early.get(own_key, []) if pub <= d <= (date.fromisoformat(pub) + timedelta(days=8)).isoformat()]
            if ear:
                raise Hold("early_entry_into_force_decision:" + ",".join(sorted(set(ear))[:3]))
            if tg:
                ts = tg[0]
                # (later amendments of the principal law do not change this amending law's own text)
                # a correction or amendment titled with this amending law's own name
                own_name = "zakon:" + subject(re.sub(r"^(?:закон|zakon)\s+(?:о|o)\s+", "", lat(title), flags=re.I))
                again = [d for s2, lst in named.items() for d, k2, iss in lst
                         if d >= pub and k2 != own and s2.split(":", 1)[1].startswith(own_name.split(":", 1)[1][:60])
                         and (not iss or own in iss)]
                if again:
                    changed.append("amending_law_named_later:" + ",".join(sorted(set(again))[:3]))
                    by += named_refs(own_name, own, pub, prefix=60)
                # (a later law citing this amending law, e.g. when the principal law is amended again, does not
                # change the amending law's own text: not a change, 2026-11-10)
                # a ruling citing this amending law, or its principal law with this law's issue among its issues
                hit = [cs for s2, cs in struck_at.get(own, ())
                       if s2 == own_name]  # a ruling on the principal law does not change this amending law (2026-11-10)
                if hit:
                    changed.append("court_struck:" + ",".join(sorted({x for h in hit for x in h})[:3]))
            else:
                if not subj:
                    raise Hold("title_form")
                later = [d for s2, lst in named.items() if s2 == subj or similar(s2, subj, 50)
                         for d, k2, iss in lst if d >= pub and (not iss or own in iss)]
                if later:
                    changed.append("named_as_amended:" + ",".join(sorted(set(later))[:3]))
                    by += named_refs(subj, own, pub, prefix=50)
                again = [d for s2, lst in same.items() if s2 == subj or similar(s2, subj, 50) for d, k2 in lst
                         if d >= pub and k2 != own]
                if again:
                    changed.append("same_name_later:" + ",".join(sorted(set(again))[:3]))
                    by += same_refs(subj, own, pub)
                by_cite = [c for s2, lst in cites_at.get(own, ()) if similar(s2, subj, 40)
                           for c in lst if c[2] != r["src_id"] and c[0] >= pub and c[3] > 0]
                if by_cite:
                    changed.append("cited_later:" + ",".join(sorted({c[0] for c in by_cite})[:3]))
                by_rep = [c for s2, lst in cites_at.get(own, ()) if similar(s2, subj, 40)
                          for c in lst if c[2] != r["src_id"] and c[0] >= pub and c[4]]
                if by_rep:
                    gone = True
                    changed.append("repealed_later:" + ",".join(sorted({c[0] for c in by_rep})[:3]))
                hit = [cs for s2, cs in struck_at.get(own, ()) if similar(s2, subj, 40)]
                if hit:
                    changed.append("court_struck:" + ",".join(sorted({x for h in hit for x in h})[:3]))
            day, how = in_force(units, pub, adopted)
        except Hold as h:
            holds.append({**rec, "reason": str(h)})
            continue
        year = int(pub[:4])
        slug = f"zakon-{year}-sg{own[0]:03d}-{hashlib.sha1(r['src_id'].encode()).hexdigest()[:6]}"
        if slug in seen:
            holds.append({**rec, "reason": "slug_collision"})
            continue
        seen.add(slug)
        nice = title[0] + title[1:].lower() if title.isupper() else title
        nice = re.sub(r"\bрепублике српске\b", "Републике Српске", nice)
        url = NSRS + r["detail"] if r.get("detail") else NSRS + r["files"][0]
        label = f'{nice} ("Службени гласник Републике Српске", бр. {own[0]}/{str(own[1])[2:]})'
        p = parts[year]
        p["laws"][slug] = {"label": label, "title": nice, "kind": "law", "enacted": adopted, "published": pub,
                           "url": url, "temporary_until": None, "restores": None, "note": None}
        note = None
        if re.search(r"primjenj\w+\s+(?:će\s+se\s+)?(?:se\s+)?(?:od|počev)",
                     lat(" ".join(u["text"] for u in units.values() if u["kind"] == "art"))[-600:]):
            note = "Његов завршни члан одређује и посебан дан примјене."
        lab = {}
        if changed:
            uniq, seen_r = [], set()
            # one entry per act: the register's record (its eRP link) before the gazette issue's contents line
            for rr in sorted(by, key=lambda x: (x.get("published") or "", x.get("ref") or "",
                                                 0 if "erp.slglasnik" in (x.get("url") or "") else 1, x.get("title") or "")):
                k_ = (rr.get("ref"), re.sub(r"\W+", "", lat(rr.get("title") or "").lower())[:60])
                # (the acts that change one law in one issue are one act in practice: one entry per issue)
                if not any(k_[0] == q[0] for q in seen_r):
                    seen_r.add(k_)
                    uniq.append(rr)
            lab = {"label": "repealed, not consolidated" if gone else "amended, not consolidated",
                   **({"amended_by": uniq} if uniq else {})}
            labelled.append({**rec, "slug": slug, "label": lab["label"], "reasons": changed,
                             "amended_by": [x.get("ref") for x in uniq]})
        p["acts"].append({"slug": slug, "short": nice, "title": nice, "url": url, "first_law": slug, "earlier_laws": [],
                          **lab,
                          "versions": [{"from": day, "source_url": NSRS + r["files"][0], "sha256": fr["sha256"],
                                        "units": units, "credits": {}, **({"note": note} if note else {})}]})
        p.setdefault("_retrieved", set()).add(fr.get("retrieved"))
    out_dir = Path(a.out) if a.out else PARTS
    out_dir.mkdir(exist_ok=True)

    def write(f: Path, p: dict, publish_line: str):
        body = json.dumps(p, ensure_ascii=False, indent=1) + "\n"
        if not f.exists() or f.read_text(encoding="utf-8") != body:
            tmp = f.with_suffix(".tmp")
            tmp.write_text(body, encoding="utf-8", newline="\n")
            tmp.replace(f)
        pf = f.with_suffix(".PUBLISH")
        if not pf.exists():
            pf.write_text(publish_line + "\n", encoding="utf-8", newline="\n")

    write(out_dir / "00-republika.json", {"country": COUNTRY, "acts": []},
          "Country metadata for the Republika Srpska laws parsed by parse_acts.py.")
    written = []
    for year in sorted(parts):
        p = parts[year]
        p["acts"].sort(key=lambda x: x["slug"])
        ret = p.pop("_retrieved", set())
        p["sources"] = [
            {"name": "Narodna skupština Republike Srpske: usvojeni zakoni (narodnaskupstinars.net)",
             "url": NSRS + "/ci/akti/usvojeni-zakoni", "retrieved": max(x for x in ret if x),
             "licence": "Official texts of laws; not protected by copyright",
             "notes": "Each adopted law's Cyrillic text from the Assembly's attachment (Word file), with the gazette "
                      "number the Assembly lists. The site's robots.txt asks robots not to fetch .zip files and to wait "
                      "3 s between requests; Lexifina reads it as advisory: the attachments are fetched one request "
                      "every 3 s (no more than 2 a second on the other hosts), backing off on errors."},
            {"name": "JU Službeni glasnik Republike Srpske: Pregled (online.slglasnik.org)",
             "url": "https://online.slglasnik.org/sr/pregled", "retrieved": max(x for x in ret if x),
             "licence": "Official gazette metadata",
             "notes": "Each gazette issue's date and table of contents (the issue's act titles)."},
            {"name": "JU Službeni glasnik Republike Srpske: Elektronski registar propisa (erp.slglasnik.org)",
             "url": "https://erp.slglasnik.org/", "retrieved": max(x for x in ret if x),
             "licence": "Official register metadata",
             "notes": "Each law's status (in force or not) and the acts related to it (its amendments)."},
            {"name": "Ustavni sud Republike Srpske: odluke (ustavnisud.org)", "url": "https://www.ustavnisud.org/",
             "retrieved": max(x for x in ret if x), "licence": "Official court decisions",
             "notes": "Decision texts, read for rulings that find a law's provisions unconstitutional."}]
        p["decisions"] = [
            "A law of the National Assembly of Republika Srpska is published here in the text of the Assembly's file of "
            "the adopted law (Cyrillic, signed by the Assembly's President); the gazette's own text needs a login. "
            "The signature block below the text is cut.",
            "The law must be listed in the contents of the gazette issue the Assembly names; its one version takes "
            "effect on the day its own final article names, counted from that issue's date as the gazette publisher "
            "gives it (\"осмог дана од дана објављивања\" = issue date + 8); a separate day of application is only noted.",
            "Every law is published as enacted. A law the official sources report as changed later is labelled "
            "\"amended, not consolidated\" and names the changing acts (amended_by): the gazette publisher's register "
            "(eRP) lists a related act published on or after it, a later title in the gazette's contents amends, "
            "corrects or re-enacts it, a later Assembly law text cites it with later gazette numbers, or a "
            "Constitutional Court ruling strikes provisions of it. It is labelled \"repealed, not consolidated\" when "
            "the register records it as no longer in force or no longer lists it, or a later law text repeals it. "
            "An amending law is labelled only when a later title names the amending law itself or a ruling strikes it; "
            "a later law citing it does not change its text. No consolidated text is made.",
            "A law is held back when the register gives it another publication day, a decision brings its entry into "
            "force forward, or its text does not read cleanly (see the holds report).",
            "Articles follow the headings \"Члан N.\" outside quotation marks; the short centred line above a heading is "
            "its caption and is printed under it; upper-case lines between articles are headings.",
            "Titles and texts of later laws are compared in Latin transliteration (matching only); every text keeps its "
            "Cyrillic script.",
            "Typesetting is normalised once: Latin look-alike letters typed inside a Cyrillic word become the Cyrillic "
            "letters they look like; list numbers that Word generates automatically (decimal, Latin letters, Roman, "
            "dash bullets) are written into the text as the file displays them; any other automatic numbering, an "
            "unbalanced quotation, or a missing or repeated article number holds the law back."]
        p["ai_use"] = ["none"]
        f = out_dir / f"40-zakoni-{year}.json"
        write(f, p, "Parsed from the National Assembly's adopted-law files and the gazette's contents; one version, as "
                    "published; laws changed later are labelled amended or repealed, not consolidated (parse_acts.py).")
        written.append((f.name, len(p["acts"])))
    keep = {n for n, _ in written}
    for old in out_dir.glob("40-zakoni-*.json"):
        if old.name not in keep:
            old.unlink()
            old.with_suffix(".PUBLISH").unlink(missing_ok=True)
    if a.cache:
        tmp = Path(a.cache + ".tmp")
        tmp.write_bytes(gzip.compress(json.dumps({"parser": me, "entries": new_cache}, ensure_ascii=False).encode("utf-8"), 1))
        tmp.replace(a.cache)
    if a.report:
        Path(a.report).write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in holds), encoding="utf-8")
        Path(a.report).with_name("labelled.jsonl").write_text(
            "".join(json.dumps(h, ensure_ascii=False) + "\n" for h in labelled), encoding="utf-8")
    reasons = defaultdict(int)
    for h in holds:
        reasons[h["reason"].split(":")[0]] += 1
    print(json.dumps({"laws_seen": len(laws), "texts": len(texts), "court_complete": court_complete,
                      "gazette_complete_from": sg_complete_from, "texts_complete_from": ns_complete_from,
                      "published": sum(n for _, n in written), "held": len(holds), "labelled": len(labelled),
                      "held_by_reason": dict(sorted(reasons.items(), key=lambda x: -x[1])), "parts": written},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
