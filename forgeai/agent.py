"""Runs a produced agent definition. Used by both the chat runner and the judge,
so what gets tested is exactly what ships."""
import json
import os

from .docs import load_folder
from .llm import parse_json
from .rag import Index, format_context
from .tools import describe, run_tool


def render_system_prompt(defn):
    rules = "\n".join(f"{i}. {r}" for i, r in enumerate(defn["rules"], 1))
    return (f"{defn['persona']}\n\nRules:\n{rules}\n\n"
            f"If you must refuse, set refused=true and answer exactly: \"{defn['refusal_message']}\"\n\n"
            "Reply ONLY with JSON: {\"answer\": string, \"sources\": [file names you used], \"refused\": true|false}")


class Agent:
    def __init__(self, defn, llm, base_dir="."):
        self.defn = defn
        self.llm = llm
        docs = defn["docs_dir"].replace("\\", "/")  # runs made on Windows store backslashes
        self.docs_dir = os.path.normpath(docs if os.path.isabs(docs) else os.path.join(base_dir, docs))
        r = defn["retrieval"]
        self.index = Index(load_folder(self.docs_dir), r["chunk_size"], r["overlap"], r.get("method", "tfidf"))
        self.system = render_system_prompt(defn)

    def answer(self, question):
        r = self.defn["retrieval"]
        hits = [h for h in self.index.search(question, r["top_k"]) if h["score"] >= r.get("min_score", 0)]
        tool_results = self._use_tools(question) if self.defn["tools"] else []

        ctx = format_context(hits) if hits else "(no relevant passages found)"
        user = f"Context passages:\n{ctx}\n\n"
        if tool_results:
            user += "Tool results:\n" + "\n".join(json.dumps(t) for t in tool_results) + "\n\n"
        user += f"Question: {question}"

        raw = self.llm.chat([{"role": "system", "content": self.system},
                             {"role": "user", "content": user}],
                            temperature=self.defn.get("temperature", 0.0), json_mode=True)
        try:
            out = parse_json(raw)
        except ValueError:
            out = {"answer": raw, "sources": [], "refused": False, "contract_broken": True}

        out.setdefault("answer", "")
        out.setdefault("sources", [])
        out.setdefault("refused", False)
        if not isinstance(out["sources"], list):
            out["sources"] = [out["sources"]]
        # contract check: a cited source must be something we actually retrieved
        retrieved = {h["source"] for h in hits} | {t.get("file") for t in tool_results if t.get("file")}
        bad = [s for s in out["sources"] if os.path.basename(str(s)) not in retrieved]
        if bad:
            out["invalid_sources"] = bad
        out["retrieved"] = [{"id": h["id"], "source": h["source"], "score": h["score"], "text": h["text"]} for h in hits]
        out["tool_calls"] = tool_results
        return out

    def _use_tools(self, question):
        names = [t["name"] for t in self.defn["tools"]]
        files = self.defn.get("data_files", [])
        prompt = (f"Tools you may call:\n{describe(names)}\n"
                  f"CSV files available: {json.dumps(files)}\n\n"
                  f"Question: {question}\n\n"
                  "Decide which tool calls (at most 2) are needed to answer. Most questions need none.\n"
                  'Reply JSON: {"calls": [{"tool": name, "args": {...}}]}')
        try:
            plan = self.llm.ask_json(prompt, retries=1, max_tokens=300)
        except Exception:
            return []
        results = []
        for c in (plan.get("calls") or [])[:2]:
            name = c.get("tool")
            if name not in names:   # model asked for a tool this agent does not have
                continue
            args = c.get("args") or {}
            res = run_tool(name, args, self.docs_dir)
            results.append({"tool": name, "args": args, "result": res,
                            **({"file": os.path.basename(args.get("file", ""))} if name == "csv_lookup" else {})})
        return results


def load_agent(path, llm):
    with open(path, encoding="utf-8") as f:
        defn = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    # iteration snapshots live one folder down from the run folder
    if not os.path.isdir(os.path.join(base, defn["docs_dir"].replace("\\", "/"))):
        base = os.path.dirname(base)
    return Agent(defn, llm, base_dir=base)
