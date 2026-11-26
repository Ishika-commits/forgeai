"""Stage 6: critic-optimizer loop.

run evals -> classify failures -> ONE targeted fix -> re-run -> keep it only if the
dev score went up. Holdout cases are scored every round but never used to choose fixes.
"""
import copy
import re
from collections import Counter

from .agent import Agent
from .judge import Judge, scorecard
from .llm import BudgetExceeded, load_prompt
from .util import fact_in_text, numbers_in

PRIORITY = ["retrieval_miss", "hallucination", "wrong_refusal", "prompt_defect"]

FALLBACK_RULES = {
    "hallucination": "If the context does not state something explicitly, do not add it. Refuse rather than fill gaps.",
    "wrong_refusal": "If the context answers the question even partly, answer with what it says instead of refusing.",
    "prompt_defect": "Include every specific figure, limit and condition from the relevant passage in your answer, and cite its file.",
}


def run_evals(defn, cases, llm, judge, base_dir, label=""):
    agent = Agent(defn, llm, base_dir=base_dir)
    results = []
    for i, c in enumerate(cases, 1):
        print(f"\r  [{label}] case {i}/{len(cases)}", end="", flush=True)
        try:
            out = agent.answer(c["question"])
            results.append(judge.score(c, out))
        except BudgetExceeded:
            raise
        except Exception as e:
            results.append({"id": c["id"], "type": c["type"], "split": c.get("split", "dev"),
                            "question": c["question"], "answer": "", "passed": False, "grounded": False,
                            "correct": False, "category": "prompt_defect", "reason": f"agent crashed: {e}"})
    print()
    return results


def leaks(rule, cases):
    """A 'fix' that smuggles test answers into the prompt is cheating, not fixing."""
    for c in cases:
        for f in c["key_facts"]:
            if len(f) > 3 and (fact_in_text(f, rule) >= 0.9 or (numbers_in(f) and numbers_in(f) <= numbers_in(rule))):
                return f
    return None


def critic_rule(category, defn, failures, cases, llm):
    examples = "\n".join(f"- Q: {r['question']}\n  A: {r['answer'][:300]}\n  Problem: {r.get('reason', '')}"
                         for r in failures[:5])
    try:
        r = llm.ask_json(load_prompt("critic_rule", category=category, rules="\n".join(defn["rules"]),
                                     examples=examples), temperature=0.2)
        rule = str(r.get("rule", "")).strip()
    except ValueError:
        rule = ""
    note = ""
    if rule:
        leaked = leaks(rule, cases)
        if re.search(r"\d", rule):
            note = f"critic's rule rejected: it contains specific numbers ('{rule}'), which overfits the tests"
            rule = ""
        elif leaked:
            note = f"critic's rule rejected: it contained a test answer ('{leaked}')"
            rule = ""
        elif len(rule.split()) > 40:
            note, rule = "critic's rule rejected: too long", ""
    if not rule:
        rule = FALLBACK_RULES[category]
        note = note or "critic gave no usable rule"
        note += "; used fallback rule"
    return rule, note


def propose_fix(category, defn, failures, cases, llm, tried):
    new = copy.deepcopy(defn)
    r = new["retrieval"]
    if category == "retrieval_miss":
        if "top_k" not in tried and r["top_k"] < 8:
            old = r["top_k"]
            r["top_k"] = min(8, old + 2)
            return new, {"what": f"retrieval.top_k {old} -> {r['top_k']}", "key": "top_k",
                         "why": "needed passages were not in the top results; widen the net"}
        if "chunk_size" not in tried and r["chunk_size"] > 90:
            old = r["chunk_size"]
            r["chunk_size"] = max(80, int(old * 0.65))
            r["overlap"] = max(r["overlap"], r["chunk_size"] // 4)
            return new, {"what": f"retrieval.chunk_size {old} -> {r['chunk_size']} (overlap {r['overlap']})",
                         "key": "chunk_size", "why": "facts were buried in long chunks that scored low; smaller chunks match questions more tightly"}
        if "hybrid" not in tried and r.get("method") != "hybrid":
            r["method"] = "hybrid"
            return new, {"what": "retrieval.method tfidf -> hybrid (tfidf + embeddings)", "key": "hybrid",
                         "why": "keyword retrieval misses paraphrased questions"}
        return None, None
    key = f"rule:{category}"
    if key in tried:
        return None, None
    rule, note = critic_rule(category, defn, failures, cases, llm)
    # insert before the final "Refuse questions about" rule so it stays last
    new["rules"].insert(len(new["rules"]) - 1, rule)
    if category == "hallucination":
        new["temperature"] = 0.0
    return new, {"what": f'added rule: "{rule}"', "key": key, "note": note,
                 "why": {"hallucination": "answers stated things the context did not support",
                         "wrong_refusal": "the agent refused although the answer was in its context",
                         "prompt_defect": "the right passage was retrieved but the answer left facts out or skipped citations"}[category]}


def optimize(defn, cases, llm, judge_llm, base_dir, max_iters=3):
    judge = Judge(judge_llm)
    history, tried = [], set()
    try:
        results = run_evals(defn, cases, llm, judge, base_dir, "baseline")
    except BudgetExceeded as e:
        raise SystemExit(f"budget ran out during the baseline eval: {e}")
    card = scorecard(results)
    history.append({"iteration": 0, "change": None, "scorecard": card, "accepted": True})
    snapshots = [(copy.deepcopy(defn), results)]
    best, best_results = defn, results

    for it in range(1, max_iters + 1):
        dev_fail = [r for r in best_results if not r["passed"] and r["split"] == "dev"]
        if not dev_fail:
            history.append({"iteration": it, "stopped": "all dev cases pass; nothing to fix"})
            break
        counts = Counter(r["category"] for r in dev_fail)
        order = sorted(counts, key=lambda c: (-counts[c], PRIORITY.index(c)))
        new, change, cat = None, None, None
        for cat in order:
            new, change = propose_fix(cat, best, [r for r in dev_fail if r["category"] == cat], cases, llm, tried)
            if new:
                break
        if not new:
            history.append({"iteration": it, "stopped": f"no untried fix left for {dict(counts)}"})
            break
        tried.add(change["key"])
        new["version"] = it
        targeted = [r["id"] for r in dev_fail if r["category"] == cat]
        print(f"  iteration {it}: fixing {cat} ({len(targeted)} dev cases) -> {change['what']}")
        before = scorecard(best_results)
        try:
            new_results = run_evals(new, cases, llm, judge, base_dir, f"iter {it}")
        except BudgetExceeded as e:
            history.append({"iteration": it, "stopped": f"budget exhausted ({e}); kept best so far"})
            break
        after = scorecard(new_results)
        old_pass = {r["id"]: r["passed"] for r in best_results}
        fixed = [r["id"] for r in new_results if r["passed"] and not old_pass[r["id"]]]
        broke = [r["id"] for r in new_results if not r["passed"] and old_pass[r["id"]]]
        accepted = (after["dev"] or 0) > (before["dev"] or 0)
        history.append({
            "iteration": it, "targeted_category": cat, "category_counts_dev": dict(counts),
            "change": change["what"], "why": change["why"], "note": change.get("note", ""),
            "targeted_cases": targeted, "fixed": fixed, "newly_broken": broke,
            "score_before": {k: before[k] for k in ("dev", "holdout", "overall")},
            "score_after": {k: after[k] for k in ("dev", "holdout", "overall")},
            "scorecard": after, "accepted": accepted,
            "decision": "kept (dev score improved)" if accepted else "reverted (dev score did not improve)",
        })
        snapshots.append((copy.deepcopy(new), new_results))
        if accepted:
            best, best_results = new, new_results
    return best, best_results, history, snapshots, {"llm_judge_calls": judge.llm_calls,
                                                    "judge_disagreements": judge.disagreements}
