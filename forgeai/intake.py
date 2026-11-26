"""Stage 1+2: intake interview, requirements, groundability guard, human checkpoint."""
import json
import os

from .docs import folder_profile
from .llm import load_prompt
from .rag import Index
from .util import fact_in_text, load_json, save_json, topic_overlap


def describe_folder(docs, llm):
    """Deterministic profile + a short model summary per text document."""
    profile = folder_profile(docs)
    for p, d in zip(profile, docs):
        if d.kind == "csv":
            p["summary"] = f"CSV table with {p['rows']} rows, columns: {', '.join(p['columns'])}"
            p["topics"] = p["columns"]
        else:
            print(f"  reading {d.name}", flush=True)
            s = llm.ask_json(load_prompt("intake_summarize", name=d.name, text=d.text[:6000]))
            p["summary"] = s.get("summary", "")
            p["topics"] = s.get("topics", [])
        p.pop("opening", None)
        p.pop("sample_row", None)
    return profile


def folder_text(profile):
    return "\n".join(f"- {p['name']} ({p['kind']}): {p['summary']} Topics: {', '.join(map(str, p['topics']))}"
                     for p in profile)


def interview(brief, profile, llm, auto):
    qs = llm.ask_json(load_prompt("intake_questions", brief=brief, folder=folder_text(profile))).get("questions", [])
    qs = [q for q in qs if isinstance(q, str) and q.strip()][:5]  # hard cap, whatever the model says
    print(f"  {len(qs)} clarifying questions" + (" (answers assumed, --auto)" if auto else ""), flush=True)
    if not qs:
        return []
    if auto:
        res = llm.ask_json(load_prompt("intake_autoanswer", brief=brief, folder=folder_text(profile),
                                       questions="\n".join(f"- {q}" for q in qs)))
        qa = [{"question": q, "answer": a.get("answer", "") if isinstance(a, dict) else str(a), "assumed": True}
              for q, a in zip(qs, res.get("answers", []))]
        return qa
    print("\nA few questions before I build this (press Enter to let me decide):\n")
    qa = []
    for i, q in enumerate(qs, 1):
        ans = input(f"  Q{i}. {q}\n  > ").strip()
        qa.append({"question": q, "answer": ans or "No preference - use your judgement.", "assumed": not ans})
    return qa


def groundability(req, docs, llm):
    """For each must-answer topic: does the folder actually support it?
    The model's 'yes' only counts if its evidence quote really is in the passages."""
    idx = Index(docs)
    results = []
    for topic in req["must_answer"]:
        hits = idx.search(f"{topic} {req.get('scope', '')}", k=4)
        hits = sorted(hits, key=lambda h: -h["score"])[:4]
        passages = "\n---\n".join(h["text"] for h in hits)
        best = hits[0]["score"] if hits else 0.0
        if not hits:
            results.append({"topic": topic, "status": "unsupported", "why": "no passage matched at all", "best_score": 0})
            continue
        v = llm.ask_json(load_prompt("guard_check", topic=topic, passages=passages[:5000]))
        claim = str(v.get("supported", "no")).lower()
        evidence = v.get("evidence", "") or ""
        # the quote must exist in the passages AND actually be about the topic.
        # Small models love quoting a real but unrelated sentence.
        verified = (bool(evidence) and fact_in_text(evidence, passages) >= 0.9
                    and topic_overlap(topic, evidence) >= 0.5)
        if claim == "yes" and verified:
            status, why = "supported", f'evidence: "{evidence}"'
        elif claim in ("yes", "partial") and (verified or (best >= 0.15 and topic_overlap(topic, passages) >= 0.5)):
            status = "weak"
            why = ("model said yes but its evidence quote was missing or off-topic" if claim == "yes"
                   else "only partly covered") + f" (best retrieval score {best})"
        else:
            status = "unsupported"
            why = f"model said '{claim}'" + ("" if verified or not evidence else "; its evidence quote was missing or not about the topic")
        print(f"  groundability: {topic} -> {status}", flush=True)
        results.append({"topic": topic, "status": status, "why": why, "best_score": best,
                        "sources": sorted({h["source"] for h in hits[:2]}),
                        "model_claim": claim, "evidence_verified": verified})
    return results


def apply_guard(req, guard):
    unsupported = [g["topic"] for g in guard if g["status"] == "unsupported"]
    req["must_answer"] = [t for t in req["must_answer"] if t not in unsupported]
    req["unsupported_topics"] = unsupported
    # anything the documents can't back must be refused, not improvised
    req["must_refuse"] = list(dict.fromkeys(req["must_refuse"] + [f"{t} (not covered by the documents)" for t in unsupported]))
    req["weak_topics"] = [g["topic"] for g in guard if g["status"] == "weak"]
    return req


def requirements_md(req, guard):
    lines = [f"# Requirements: {req['name']}", "", f"**Brief:** {req['brief']}", "",
             f"**Scope:** {req['scope']}", f"**Audience:** {req['audience']}", f"**Tone:** {req['tone']}", "",
             "## Must answer"] + [f"- {t}" for t in req["must_answer"]] + ["", "## Must refuse"] + \
            [f"- {t}" for t in req["must_refuse"]] + ["", "## Groundability check", "",
             "| Topic | Status | Why |", "|---|---|---|"] + \
            [f"| {g['topic']} | {g['status'].upper()} | {g['why']} |" for g in guard]
    if req["unsupported_topics"]:
        lines += ["", "> **FLAG:** the brief asks for topics the documents cannot support: "
                  + ", ".join(req["unsupported_topics"])
                  + ". The agent will refuse these instead of guessing. Add documents to cover them."]
    lines += ["", "## Clarifying Q&A"] + [f"- **Q:** {x['question']}  \n  **A:** {x['answer']}"
                                          + (" _(assumed)_" if x.get("assumed") else "") for x in req["qa"]]
    return "\n".join(lines) + "\n"


def checkpoint(req_path, md_path):
    """Human approves or edits requirements before generation."""
    while True:
        print("\n" + open(md_path, encoding="utf-8").read())
        c = input("[a]pprove, [e]dit requirements.json then continue, [q]uit? ").strip().lower()
        if c in ("a", ""):
            return load_json(req_path)
        if c == "q":
            raise SystemExit("stopped at requirements checkpoint")
        if c == "e":
            input(f"Edit {req_path} in any editor, save it, then press Enter...")
            return load_json(req_path)


def run_intake(brief, docs, llm, out_dir, auto=False):
    profile = describe_folder(docs, llm)
    qa = interview(brief, profile, llm, auto)
    req = llm.ask_json(load_prompt("intake_requirements", brief=brief, folder=folder_text(profile),
                                   qa=json.dumps(qa, indent=1) if qa else "(none)"))
    req = {
        "name": req.get("name") or "Assistant",
        "scope": req.get("scope", ""),
        "audience": req.get("audience", ""),
        "tone": req.get("tone", "clear and professional"),
        "must_answer": [str(x) for x in req.get("must_answer", [])][:10],
        "must_refuse": [str(x) for x in req.get("must_refuse", [])][:8],
        "brief": brief, "qa": qa, "folder": profile,
    }
    guard = groundability(req, docs, llm)
    req = apply_guard(req, guard)
    req["groundability"] = guard

    req_path = os.path.join(out_dir, "requirements.json")
    md_path = os.path.join(out_dir, "requirements.md")
    save_json(req_path, req)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(requirements_md(req, guard))
    if not auto:
        req = checkpoint(req_path, md_path)
        req["approved_by_human"] = True
        save_json(req_path, req)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(requirements_md(req, req["groundability"]))
    return req
