"""Stage 7: the honest report."""
import datetime as dt


def pct(x):
    return "-" if x is None else f"{x:.0f}%"


def build_report(req, defn, tool_decisions, eval_log, cases, history, final_results, meta, judge_stats, tournament=None):
    final = [h for h in history if "scorecard" in h and h.get("accepted")][-1]["scorecard"]
    L = [f"# ForgeAI report: {defn['name']}", "",
         f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} · model `{meta['model']}` · judge `{meta['judge_model']}` · "
         f"{meta['llm_calls']} LLM calls · ~{meta['tokens']} tokens · {meta['seconds']}s", "",
         "## Result", "",
         f"**{final['passed']}/{final['n']} cases pass ({pct(final['overall'])}).** "
         f"Dev {pct(final['dev'])}, holdout {pct(final['holdout'])}. "
         f"Correct {pct(final['correct_rate'])}, grounded {pct(final['grounded_rate'])}, "
         f"refusal accuracy {pct(final['refusal_accuracy'])}.", "",
         "Holdout cases were never used to pick fixes, so the holdout number is the fairer estimate of how this agent "
         "does on new questions.", ""]

    # requirements flags
    L += ["## Requirements flags", ""]
    if req.get("unsupported_topics"):
        L.append("The brief asks for things the documents cannot support. The agent refuses these instead of guessing:")
        L += [f"- **{t}**" for t in req["unsupported_topics"]]
    else:
        L.append("Every must-answer topic was found in the documents.")
    if req.get("weak_topics"):
        L += ["", "Only weakly covered (expect thinner answers): " + ", ".join(req["weak_topics"])]
    if any(q.get("assumed") for q in req.get("qa", [])):
        L += ["", f"{sum(q.get('assumed', False) for q in req['qa'])} intake answers were assumed, not given by a person "
              "(see requirements.md)."]
    L.append("")

    # tools
    L += ["## Tool selection", "", "| Tool | Model said | Decision | Why |", "|---|---|---|---|"]
    L += [f"| {d['tool']} | {d['model_said']} | {d['decision']} | {d['why']} |" for d in tool_decisions]
    L.append("")

    if tournament:
        L += ["## Prompt tournament", "", "| Candidate | Dev score | |", "|---|---|---|"]
        L += [f"| {t['name']} | {pct(t['dev'])} | {'winner' if t['winner'] else ''} |" for t in tournament]
        L.append("")

    # eval set
    L += ["## Eval set", "",
          f"{eval_log['kept']} cases kept out of {eval_log['generated']} generated "
          f"({len(eval_log['discarded'])} discarded by the checks). By type: "
          + ", ".join(f"{k} {v}" for k, v in eval_log["by_type"].items()) + ". "
          f"Split: {sum(c['split'] == 'dev' for c in cases)} dev / {sum(c['split'] == 'holdout' for c in cases)} holdout.", ""]
    if eval_log["kept"] < 20:
        L += [f"> **Warning:** only {eval_log['kept']} cases survived the checks (target 20+). Scores are noisy.", ""]
    if eval_log["discarded"]:
        L += ["Discarded cases (the generator's own mistakes that were caught):", "", "| Type | Question | Why |", "|---|---|---|"]
        L += [f"| {d['type']} | {d['question'][:90]} | {d['why'][:120]} |" for d in eval_log["discarded"][:15]]
        L.append("")

    # scorecard
    L += ["## Scorecard per iteration", "",
          "| Iter | Change | Dev | Holdout | Overall | Correct | Grounded | Refusal | Kept? |",
          "|---|---|---|---|---|---|---|---|---|"]
    for h in history:
        if "scorecard" not in h:
            continue
        s = h["scorecard"]
        L.append(f"| {h['iteration']} | {h.get('change') or 'baseline'} | {pct(s['dev'])} | {pct(s['holdout'])} | "
                 f"{pct(s['overall'])} | {pct(s['correct_rate'])} | {pct(s['grounded_rate'])} | "
                 f"{pct(s['refusal_accuracy'])} | {'yes' if h['accepted'] else 'no, reverted'} |")
    L.append("")

    L += ["## Change log", ""]
    for h in history[1:]:
        if "stopped" in h:
            L += [f"- **Iteration {h['iteration']}:** stopped: {h['stopped']}"]
            continue
        L += [f"- **Iteration {h['iteration']}:** targeted `{h['targeted_category']}` "
              f"(dev failures by category: {h['category_counts_dev']})",
              f"  - Change: {h['change']}",
              f"  - Why: {h['why']}" + (f" ({h['note']})" if h.get("note") else ""),
              f"  - Targeted cases: {', '.join(h['targeted_cases'])}",
              f"  - Dev {pct(h['score_before']['dev'])} → {pct(h['score_after']['dev'])}, "
              f"holdout {pct(h['score_before']['holdout'])} → {pct(h['score_after']['holdout'])}. "
              f"Fixed: {', '.join(h['fixed']) or 'none'}. Newly broken: {', '.join(h['newly_broken']) or 'none'}.",
              f"  - Decision: {h['decision']}"]
    if len(history) == 1:
        L.append("No iterations ran.")
    L.append("")

    # what still fails
    fails = [r for r in final_results if not r["passed"]]
    L += ["## What still fails, and why", ""]
    if not fails:
        L += ["Nothing in this eval set. Treat that with suspicion: the set is small and was written by the same "
              "family of model that answers it.", ""]
    else:
        cats = {}
        for r in fails:
            cats.setdefault(r["category"], []).append(r)
        explain = {
            "retrieval_miss": "the retriever never brought back the passage with the answer",
            "prompt_defect": "the right passage was retrieved but the answer dropped facts, skipped citations or broke format",
            "hallucination": "the answer stated things that were not in its context, or answered something it should have refused",
            "wrong_refusal": "the agent refused even though the answer was in front of it",
        }
        for cat, rs in sorted(cats.items(), key=lambda x: -len(x[1])):
            L += [f"### {cat} ({len(rs)}): {explain.get(cat, '')}", "", "| Case | Type | Split | Question | Detail |", "|---|---|---|---|---|"]
            L += [f"| {r['id']} | {r['type']} | {r['split']} | {r['question'][:80]} | {str(r.get('reason', ''))[:160]} |" for r in rs]
            L.append("")

    # caveats
    L += ["## Caveats", ""]
    gap = (final["dev"] or 0) - (final["holdout"] or 0)
    if gap >= 15:
        L.append(f"- Dev is {gap:.0f} points above holdout: some of the fixes probably fit the dev questions more than the task.")
    L.append(f"- The LLM judge was consulted {judge_stats['llm_judge_calls']} times (only when string matching was unsure); "
             f"its two orderings disagreed {judge_stats['judge_disagreements']} times. Disagreements count as a miss.")
    unsure = sum(1 for r in final_results if r.get("judge_unsure"))
    if unsure:
        L.append(f"- {unsure} final cases had an unsure judge verdict; a human should look at those first.")
    L.append("- Eval questions are generated by a small model. Checks guarantee each expected fact really is in its "
             "source document, not that the question is one a real user would ask.")
    L.append("- Key-fact matching is strict about numbers on purpose (a small judge model is too lenient on them). "
             "An answer that converts units (e.g. '2 weeks' for '14 days') is marked wrong.")
    return "\n".join(L) + "\n"
