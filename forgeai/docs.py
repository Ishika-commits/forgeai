"""Load a document folder: PDF, TXT, MD and CSV."""
import csv
import logging
import os
from dataclasses import dataclass, field

from pypdf import PdfReader

# pypdf logs harmless repair warnings ("incorrect startxref pointer") for slightly
# damaged files; it still reads them fine, so keep the console clean.
logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass
class Doc:
    name: str
    path: str
    kind: str          # pdf | text | csv
    text: str
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)


def load_folder(folder):
    docs = []
    for fname in sorted(os.listdir(folder)):
        path = os.path.join(folder, fname)
        ext = fname.lower().rsplit(".", 1)[-1]
        if ext == "pdf":
            reader = PdfReader(path)
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            docs.append(Doc(fname, path, "pdf", clean(text)))
        elif ext in ("txt", "md"):
            with open(path, encoding="utf-8", errors="ignore") as f:
                docs.append(Doc(fname, path, "text", clean(f.read())))
        elif ext == "csv":
            with open(path, encoding="utf-8", errors="ignore", newline="") as f:
                rows = list(csv.DictReader(f))
            cols = list(rows[0].keys()) if rows else []
            # each row also becomes a line of text so retrieval can find it
            lines = ["; ".join(f"{k}: {v}" for k, v in r.items()) for r in rows]
            docs.append(Doc(fname, path, "csv", "\n".join(lines), cols, rows))
    return docs


def clean(text):
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    out, blank = [], 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip()


def folder_profile(docs):
    """Cheap, deterministic facts about the folder. Used by intake and the generator."""
    prof = []
    for d in docs:
        p = {"name": d.name, "kind": d.kind, "words": len(d.text.split())}
        if d.kind == "csv":
            p["columns"] = d.columns
            p["rows"] = len(d.rows)
            p["sample_row"] = d.rows[0] if d.rows else {}
        else:
            p["opening"] = " ".join(d.text.split()[:80])
        prof.append(p)
    return prof
