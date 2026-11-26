"""Stage 4: generate the eval set from the documents.

Every generated case goes through checks before it is kept, because a small model
writing its own exam will happily invent "facts". Discards are counted and reported.
"""
import random

from .llm import load_prompt
from .rag import Index, chunk_doc
from .util import fact_in_text, norm

TARGET = {"answerable": 12, "multi_doc": 3, "ambiguous": 3, "out_of_scope": 5}


def candidate_chunks(docs):
    by_doc = {}
    for d in docs:
        if d.kind == "csv":
            cs = chunk_doc(d, csv_rows=1)
        else:
            # small windows (~60 words) so short policy docs still give enough distinct questions
            cs = [c for c in chunk_doc(d, size=60, overlap=0) if len(c["text"].split()) >= 20]
        if cs:
            by_doc[d.name] = cs
    return by_doc


def verified_facts(facts, passage):
    return [str(f) for f in (facts or []) if str(f).strip() and fact_in_text(f, passage) >= 0.9]


def is_dup(q, facts, seen):
    """Near-identical wording AND the same expected facts. Two tariff questions that
    differ only in the port name are different tests, not duplicates."""
    a = set(norm(q).split())
    fa = {norm(f) for f in facts}
    for s, sf in seen:
        b = set(norm(s).split())
        if a and len(a & b) / len(a | b) > 0.8 and fa == {norm(f) for f in sf}:
            return True
    return False


def generate_evals(req, docs, llm, seed=13):
    rng = random.Random(seed)
    by_doc = candidate_chunks(docs)
    names = list(by_doc)
    for n in names:
        rng.shuffle(by_doc[n])
    all_chunks = {n: list(v) for n, v in by_doc.items()}  # multi-doc may reuse chunks
    cases, seen = [], []
    log = {"generated": 0, "kept": 0, "discarded": []}

    def discard(kind, q, why):
        log["discarded"].append({"type": kind, "question": q, "why": why})

    # 1. answerable: round-robin over documents so every doc is tested
    attempts, i = 0, 0
    while sum(c["type"] == "answerable" for c in cases) < TARGET["answerable"] and attempts < TARGET["answerable"] * 2:
        doc = names[i % len(names)]
        i += 1
        if not by_doc[doc]:
            continue
        ch = by_doc[doc].pop()
        attempts += 1
        log["generated"] += 1
        try:
            r = llm.ask_json(load_prompt("eval_answerable", scope=req["scope"], source=doc, passage=ch["text"]),
                             temperature=0.3)
        except ValueError:
            discard("answerable", "", "bad JSON")
            continue
        q = str(r.get("question", "")).strip()
        facts = verified_facts(r.get("key_facts"), ch["text"])
        if len(q) < 10:
            discard("answerable", q, "question too short")
        elif not facts:
            discard("answerable", q, f"none of the key facts {r.get('key_facts')} appear in the source passage")
        elif all(fact_in_text(f, q) >= 0.9 for f in facts):
            discard("answerable", q, "question gives away its own answer")
        elif is_dup(q, facts, seen):
            discard("answerable", q, "duplicate")
        else:
            seen.append((q, facts))
            cases.append({"type": "answerable", "question": q, "expected_sources": [doc],
                          "key_facts": facts, "should_refuse": False, "origin": [ch["id"]],
                          "reference_answer": r.get("answer", "")})

    # 2. multi-doc: two chunks from different docs, preferring a pair that shares words
    text_docs = [n for n in names if all_chunks[n]]
    used_pairs = set()
    for _ in range(TARGET["multi_doc"] * 3):
        if sum(c["type"] == "multi_doc" for c in cases) >= TARGET["multi_doc"] or len(text_docs) < 2:
            break
        a_doc, b_doc = rng.sample(text_docs, 2)
        a = rng.choice(all_chunks[a_doc])
        b = max(all_chunks[b_doc], key=lambda c: len(set(norm(a["text"]).split()) & set(norm(c["text"]).split())))
        if (a["id"], b["id"]) in used_pairs:
            continue
        used_pairs.add((a["id"], b["id"]))
        log["generated"] += 1
        try:
            r = llm.ask_json(load_prompt("eval_multidoc", scope=req["scope"], source_a=a_doc, source_b=b_doc,
                                         passage_a=a["text"], passage_b=b["text"]), temperature=0.3)
        except ValueError:
            discard("multi_doc", "", "bad JSON")
            continue
        q = str(r.get("question", "")).strip()
        fa, fb = verified_facts(r.get("key_facts_a"), a["text"]), verified_facts(r.get("key_facts_b"), b["text"])
        if not fa or not fb:
            discard("multi_doc", q, "needs a verified fact from BOTH passages")
        elif is_dup(q, fa + fb, seen):
            discard("multi_doc", q, "duplicate")
        else:
            seen.append((q, fa + fb))
            cases.append({"type": "multi_doc", "question": q, "expected_sources": [a_doc, b_doc],
                          "key_facts": fa + fb, "should_refuse": False, "origin": [a["id"], b["id"]]})

    # 3. ambiguous: vague rewrites of kept answerable questions (same expected facts)
    base = [c for c in cases if c["type"] == "answerable"]
    rng.shuffle(base)
    for c in base[:TARGET["ambiguous"] + 2]:
        if sum(x["type"] == "ambiguous" for x in cases) >= TARGET["ambiguous"]:
            break
        log["generated"] += 1
        r = llm.ask_json(load_prompt("eval_ambiguous", question=c["question"]), temperature=0.7)
        q = str(r.get("question", "")).strip()
        if not q or norm(q) == norm(c["question"]):
            discard("ambiguous", q, "rewrite identical to original")
            continue
        cases.append({**{k: c[k] for k in ("expected_sources", "key_facts", "origin")},
                      "type": "ambiguous", "question": q, "should_refuse": False, "rewrite_of": c["question"]})

    # 4. out-of-scope: must be refused. Throw away ones the docs clearly answer.
    idx = Index(docs, size=120, overlap=0)
    n = TARGET["out_of_scope"] + 2
    r = llm.ask_json(load_prompt("eval_out_of_scope", scope=req["scope"], n=n,
                                 must_refuse="; ".join(req["must_refuse"])), temperature=0.5)
    for item in r.get("questions", [])[:n]:
        q = str(item.get("question", "") if isinstance(item, dict) else item).strip()
        log["generated"] += 1
        if sum(x["type"] == "out_of_scope" for x in cases) >= TARGET["out_of_scope"]:
            break
        hits = idx.search(q, k=1)
        if hits and hits[0]["score"] >= 0.35:
            discard("out_of_scope", q, f"documents seem to answer it (retrieval score {hits[0]['score']})")
        elif not q or is_dup(q, [], seen):
            discard("out_of_scope", q, "empty or duplicate")
        else:
            seen.append((q, []))
            cases.append({"type": "out_of_scope", "question": q, "expected_sources": [], "key_facts": [],
                          "should_refuse": True, "why_refuse": item.get("why_refuse", "") if isinstance(item, dict) else ""})

    # ids + dev/holdout split (stratified). We optimise on dev only and report holdout
    # separately, so the loop can't just overfit the test set.
    for t in TARGET:
        group = [c for c in cases if c["type"] == t]
        rng.shuffle(group)
        cut = max(1, round(len(group) * 0.3)) if len(group) >= 3 else 0
        for j, c in enumerate(group):
            c["split"] = "holdout" if j < cut else "dev"
    for j, c in enumerate(cases, 1):
        c["id"] = f"case_{j:02d}"
    log["kept"] = len(cases)
    log["by_type"] = {t: sum(c["type"] == t for c in cases) for t in TARGET}
    return cases, log
