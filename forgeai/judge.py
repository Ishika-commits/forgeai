"""Stage 5: score each case.

Deterministic checks decide whenever they can. The LLM judge is only asked the
narrow question "is this one fact in this answer?" when string matching is unsure.

Defences against the usual LLM-judge failure modes:
- position bias: judging is pointwise (one answer, one fact), never A-vs-B. On top of
  that every LLM verdict is asked twice with the sections in opposite order; if the two
  disagree the fact counts as missing and the case is flagged "judge_unsure".
- verbosity bias: the judge sees a yes/no checklist, not "rate this answer", and facts
  are checked one at a time, so a long answer earns nothing extra.
- self-preference: the judge never sees a reference answer written by a model, only
  key facts copied from the source documents. A separate judge model can be set with
  --judge-model.
"""
import json

from .llm import load_prompt
from .util import fact_in_text, looks_like_refusal, numbers_in


class Judge:
    def __init__(self, llm):
        self.llm = llm
        self.llm_calls = 0
        self.disagreements = 0

    def fact_present(self, fact, answer):
        s = fact_in_text(fact, answer)
        if s >= 0.9:
            return True, "string match"
        fact_nums = numbers_in(fact)
        if fact_nums and not fact_nums <= numbers_in(answer):
            return False, "number missing"
        if s == 0 and not answer.strip():
            return False, "empty answer"
        # unsure -> ask the model twice, in both orders
        p1 = load_prompt("judge_facts", fact=fact, answer=answer[:2000])
        p2 = (f'### task: judge_facts\nAnswer to check:\n"""\n{answer[:2000]}\n"""\n\n'
              f'Required fact: "{fact}"\n\nIgnore style and length. Does the answer state this fact '
              '(same meaning)? Return JSON: {"present": true | false}')
        votes = []
        for p in (p1, p2):
            try:
                v = self.llm.ask_json(p, max_tokens=50).get("present")
            except ValueError:
                v = None
            votes.append(v is True or str(v).lower() == "true")
            self.llm_calls += 1
        if votes[0] != votes[1]:
            self.disagreements += 1
            return False, "judge_unsure"
        return votes[0], "llm judge (agreed twice)"

    def score(self, case, out):
        answer = str(out.get("answer", ""))
        refused = bool(out.get("refused")) or looks_like_refusal(answer)
        context = "\n".join(h["text"] for h in out.get("retrieved", [])) + "\n" + \
            json.dumps([t.get("result") for t in out.get("tool_calls", [])])
        # numbers in the answer that appear nowhere in the context or question
        extra_nums = {n for n in numbers_in(answer) - numbers_in(context) - numbers_in(case["question"])
                      if len(n.replace(".", "")) >= 2}
        res = {"id": case["id"], "type": case["type"], "split": case.get("split", "dev"),
               "question": case["question"], "answer": answer, "refused": refused,
               "cited": out.get("sources", []), "retrieved_sources": sorted({h["source"] for h in out.get("retrieved", [])}),
               "tools_used": [t["tool"] for t in out.get("tool_calls", [])]}

        if case["should_refuse"]:
            res["passed"] = refused
            res["grounded"] = True
            res["correct"] = refused
            if not refused:
                res["category"] = "hallucination" if extra_nums else "prompt_defect"
                res["reason"] = "answered a question it should have refused" + (
                    f" and stated unsupported numbers {sorted(extra_nums)}" if extra_nums else "")
            return res

        facts = case["key_facts"]
        in_ctx = [fact_in_text(f, context) >= 0.9 for f in facts]
        res["facts_in_context"] = sum(in_ctx)
        if refused:
            res.update(passed=False, correct=False, grounded=True, coverage=0.0)
            if any(in_ctx):
                res["category"], res["reason"] = "wrong_refusal", "refused although the facts were in the retrieved context"
            else:
                res["category"], res["reason"] = "retrieval_miss", "refused, and the retriever never surfaced the needed passage"
            return res

        checks = [self.fact_present(f, answer) for f in facts]
        present = [c[0] for c in checks]
        res["fact_checks"] = [{"fact": f, "present": p, "how": how} for f, (p, how) in zip(facts, checks)]
        if any(c[1] == "judge_unsure" for c in checks):
            res["judge_unsure"] = True
        cov = sum(present) / len(facts)
        valid_cites = [s for s in res["cited"] if s not in out.get("invalid_sources", [])]
        res["coverage"] = round(cov, 2)
        res["correct"] = cov >= 0.67
        res["grounded"] = bool(valid_cites) and not extra_nums and not out.get("invalid_sources")
        res["passed"] = res["correct"] and res["grounded"] and not out.get("contract_broken")

        if res["passed"]:
            return res
        missing = [f for f, p in zip(facts, present) if not p]
        missing_not_in_ctx = [f for f, ok in zip(facts, in_ctx) if not ok and f in missing]
        if extra_nums or out.get("invalid_sources"):
            res["category"] = "hallucination"
            res["reason"] = (f"numbers not in context: {sorted(extra_nums)} " if extra_nums else "") + \
                            (f"cited files it never retrieved: {out['invalid_sources']}" if out.get("invalid_sources") else "")
        elif missing and len(missing_not_in_ctx) == len(missing):
            res["category"], res["reason"] = "retrieval_miss", f"needed facts were not in the retrieved passages: {missing}"
        else:
            res["category"] = "prompt_defect"
            why = []
            if missing:
                why.append(f"facts were retrieved but left out of the answer: {missing}")
            if not valid_cites:
                why.append("no valid source cited")
            if out.get("contract_broken"):
                why.append("output was not valid JSON")
            res["reason"] = "; ".join(why)
        return res


def scorecard(results):
    def rate(rs):
        return round(100 * sum(r["passed"] for r in rs) / len(rs), 1) if rs else None
    dev = [r for r in results if r["split"] == "dev"]
    hold = [r for r in results if r["split"] == "holdout"]
    ans = [r for r in results if r["type"] != "out_of_scope"]
    oos = [r for r in results if r["type"] == "out_of_scope"]
    cats = {}
    for r in results:
        if not r["passed"]:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
    return {
        "overall": rate(results), "dev": rate(dev), "holdout": rate(hold),
        "by_type": {t: rate([r for r in results if r["type"] == t]) for t in ("answerable", "multi_doc", "ambiguous", "out_of_scope")},
        "grounded_rate": rate([dict(r, passed=r.get("grounded", False)) for r in ans]),
        "correct_rate": rate([dict(r, passed=r.get("correct", False)) for r in ans]),
        "refusal_accuracy": rate(oos),
        "failures": cats, "n": len(results), "passed": sum(r["passed"] for r in results),
    }
