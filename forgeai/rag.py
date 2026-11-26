"""Chunking and retrieval.

Default retriever is TF-IDF (word 1-2 grams). It needs no model download, it is
deterministic, and on small policy-style folders it is surprisingly hard to beat.
"hybrid" mixes in Ollama embeddings if an embedding model is available.
"""
import os
import re

import numpy as np
import requests
from sklearn.feature_extraction.text import TfidfVectorizer


def chunk_doc(doc, size=180, overlap=40, csv_rows=5):
    """Return list of {id, source, text}. Size/overlap are in words."""
    chunks = []
    if doc.kind == "csv":
        lines = doc.text.split("\n")
        for i in range(0, len(lines), csv_rows):
            chunks.append("\n".join(lines[i:i + csv_rows]))
    else:
        # pack paragraphs until we hit the size, then step back by overlap
        words = []
        for para in re.split(r"\n\s*\n", doc.text):
            words.extend(para.split() + ["\n\n"])
        step = max(size - overlap, 20)
        for i in range(0, max(len(words), 1), step):
            piece = " ".join(words[i:i + size]).replace(" \n\n ", "\n\n").replace("\n\n", "\n").strip()
            if piece:
                chunks.append(piece)
            if i + size >= len(words):
                break
    return [{"id": f"{doc.name}#{n}", "source": doc.name, "text": t} for n, t in enumerate(chunks)]


class Index:
    def __init__(self, docs, size=180, overlap=40, method="tfidf", embed_model=None):
        self.chunks = []
        for d in docs:
            self.chunks.extend(chunk_doc(d, size, overlap))
        texts = [c["text"] for c in self.chunks] or [""]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        self.mat = self.vec.fit_transform(texts)
        self.method = method
        self.emb = None
        if method == "hybrid":
            self.embed_model = embed_model or os.getenv("FORGE_EMBED_MODEL", "nomic-embed-text")
            try:
                self.emb = self._embed(texts)
            except Exception as e:  # no embedding model -> fall back, but say so
                print(f"[rag] embeddings unavailable ({e}); using tfidf only")
                self.method = "tfidf"

    def _embed(self, texts):
        url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        r = requests.post(f"{url}/api/embed", json={"model": self.embed_model, "input": texts}, timeout=300)
        r.raise_for_status()
        m = np.array(r.json()["embeddings"], dtype=float)
        return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    def search(self, query, k=4):
        q = self.vec.transform([query])
        scores = (self.mat @ q.T).toarray().ravel()
        if self.method == "hybrid" and self.emb is not None:
            qe = self._embed([query])[0]
            dense = self.emb @ qe
            # put both on 0..1 before mixing
            scores = 0.5 * _norm(scores) + 0.5 * _norm(dense)
        order = np.argsort(-scores)[:k]
        return [dict(self.chunks[i], score=round(float(scores[i]), 4)) for i in order if scores[i] > 0]


def _norm(x):
    lo, hi = x.min(), x.max()
    return (x - lo) / (hi - lo + 1e-9)


def format_context(hits):
    return "\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
