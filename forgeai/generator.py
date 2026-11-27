"""Stage 3: requirements + documents -> declarative agent definition."""
import json
import os
import statistics

from .llm import load_prompt
from .tools import REGISTRY, describe

# Rules every generated agent gets, whatever the model writes. These are the
# grounding guarantees; the optimizer may add rules but never removes these.
BASE_RULES = [
    "Answer only from the context passages and tool results you are given. If they do not contain the answer, refuse.",
    "Never guess numbers, dates, names or amounts. Quote them exactly as they appear in the context.",
    "In sources, list only the file names of passages you actually used.",
]


def short_req(req):
    keep = ["name", "scope", "audience", "tone", "must_answer", "must_refuse"]
    return json.dumps({k: req[k] for k in keep}, indent=1)


def pick_tools(req, docs, llm):
    names = [d.name for d in docs]
    picked = llm.ask_json(load_prompt("gen_tools", requirements=short_req(req), doc_names=names,
                                      tools=describe())).get("tools", [])
    decisions, final = [], []
    for t in picked:
        name = t.get("name") if isinstance(t, dict) else t
        if name not in REGISTRY:
            decisions.append({"tool": name, "model_said": "attach", "decision": "rejected", "why": "not in registry"})
            continue
        ok = REGISTRY[name]["needs"](req, docs)
        decisions.append({"tool": name, "model_said": "attach", "model_reason": t.get("reason", "") if isinstance(t, dict) else "",
                          "decision": "attached" if ok else "rejected",
                          "why": "requirement check passed" if ok else f"rule: {REGISTRY[name]['needs_reason']}"})
        if ok and name not in [f["name"] for f in final]:
            final.append({"name": name, "reason": t.get("reason", "") if isinstance(t, dict) else ""})
    for name in REGISTRY:
        if name not in [d["tool"] for d in decisions]:
            decisions.append({"tool": name, "model_said": "skip", "decision": "not attached",
                              "why": "model did not pick it" + (" (rule would have allowed it)" if REGISTRY[name]["needs"](req, docs) else "")})
    return final, decisions


def retrieval_params(docs):
    text_docs = [d for d in docs if d.kind != "csv"]
    words = [len(d.text.split()) for d in text_docs] or [0]
    med = statistics.median(words)
    # short policy docs -> smaller chunks so one chunk = roughly one clause
    size = 140 if med < 1500 else 220
    return {"method": "tfidf", "chunk_size": size, "overlap": 30,
            "top_k": 5 if any(d.kind == "csv" for d in docs) else 4, "min_score": 0.02}


def docs_path_for(docs_dir, out_dir):
    """Relative path when possible so a run folder can be moved with the repo.
    On Windows there is no relative path between drives (C: vs D:), so fall back to absolute."""
    try:
        # forward slashes so a run made on Windows still loads on Linux (Render)
        return os.path.relpath(os.path.abspath(docs_dir), os.path.abspath(out_dir)).replace("\\", "/")
    except ValueError:
        return os.path.abspath(docs_dir)


def generate(req, docs, docs_dir, out_dir, llm, temperature=0.0):
    p = llm.ask_json(load_prompt("gen_persona", requirements=short_req(req),
                                 doc_names=[d.name for d in docs]), temperature=temperature)
    tools, decisions = pick_tools(req, docs, llm)
    rules = BASE_RULES + [str(r) for r in p.get("rules", [])][:7]
    rules.append("Refuse questions about: " + "; ".join(req["must_refuse"]) + ".")
    defn = {
        "name": req["name"],
        "generated_by": "forgeai",
        "version": 0,
        "persona": p.get("persona", f"You are {req['name']}. {req['scope']}"),
        "rules": rules,
        "refusal_message": p.get("refusal_message", "Sorry, I can't help with that. I can answer questions about "
                                 + req["scope"]),
        "retrieval": retrieval_params(docs),
        "tools": tools,
        "data_files": [{"file": d.name, "columns": d.columns} for d in docs if d.kind == "csv"] if tools else [],
        "output_contract": {"format": "json", "fields": {"answer": "string", "sources": "list of file names",
                                                         "refused": "boolean"}},
        "temperature": 0.0,
        "docs_dir": docs_path_for(docs_dir, out_dir),
    }
    return defn, decisions
