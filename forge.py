"""ForgeAI: brief + document folder -> tested agent + honest report.

    python forge.py --brief demos/crew_rest/brief.txt --docs demos/crew_rest/docs --out runs/crew_rest
    python forge.py ... --auto          # no questions asked, no checkpoint (unattended)
"""
import argparse
import os
import shutil
import time

from forgeai.docs import load_folder
from forgeai.evalgen import generate_evals
from forgeai.generator import generate
from forgeai.intake import run_intake
from forgeai.judge import Judge, scorecard
from forgeai.llm import LLM
from forgeai.optimizer import optimize, run_evals
from forgeai.report import build_report
from forgeai.util import save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True, help="text file with the brief, or the brief itself in quotes")
    ap.add_argument("--docs", required=True, help="document folder")
    ap.add_argument("--out", required=True, help="where to write the run")
    ap.add_argument("--auto", action="store_true", help="unattended: assume intake answers, skip checkpoint")
    ap.add_argument("--model", default=None, help="default: $FORGE_MODEL or qwen2.5:3b")
    ap.add_argument("--judge-model", default=None, help="separate judge model (reduces self-preference)")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--budget", type=int, default=None, help="max tokens for the whole run")
    ap.add_argument("--tournament", action="store_true", help="generate 2 candidate prompts, keep the better one")
    a = ap.parse_args()

    brief = open(a.brief, encoding="utf-8").read().strip() if os.path.isfile(a.brief) else a.brief
    if os.path.exists(a.out) and os.listdir(a.out):
        # only ever wipe a folder that is clearly an old ForgeAI run
        if not os.path.exists(os.path.join(a.out, "requirements.json")):
            raise SystemExit(f"{a.out} is not empty and is not a previous run; pick another --out")
        shutil.rmtree(a.out)
    os.makedirs(os.path.join(a.out, "iterations"))
    t0 = time.time()

    llm = LLM(model=a.model, max_tokens_budget=a.budget)
    judge_llm = LLM(model=a.judge_model) if a.judge_model else llm
    docs = load_folder(a.docs)
    if not docs:
        raise SystemExit(f"no readable documents in {a.docs}")
    print(f"Loaded {len(docs)} documents: {', '.join(d.name for d in docs)}")

    print("\n[1/5] Intake")
    req = run_intake(brief, docs, llm, a.out, auto=a.auto)
    if req["unsupported_topics"]:
        print(f"  FLAG: documents cannot support: {req['unsupported_topics']} -> moved to must-refuse")

    print("\n[2/5] Generating eval set from the documents")
    cases, eval_log = generate_evals(req, docs, llm)
    save_json(os.path.join(a.out, "evalset.json"), {"cases": cases, "generation_log": eval_log})
    print(f"  {eval_log['kept']} cases kept, {len(eval_log['discarded'])} discarded")

    print("\n[3/5] Generating agent definition")
    defn, tool_decisions = generate(req, docs, a.docs, a.out, llm)
    tournament = None
    if a.tournament:
        alt, _ = generate(req, docs, a.docs, a.out, llm, temperature=0.8)
        alt["tools"], alt["data_files"] = defn["tools"], defn["data_files"]  # compare prompts only
        dev = [c for c in cases if c["split"] == "dev"]
        j = Judge(judge_llm)
        s1 = scorecard(run_evals(defn, dev, llm, j, a.out, "candidate A"))["overall"]
        s2 = scorecard(run_evals(alt, dev, llm, j, a.out, "candidate B"))["overall"]
        tournament = [{"name": "A (temperature 0)", "dev": s1, "winner": s1 >= s2},
                      {"name": "B (temperature 0.8)", "dev": s2, "winner": s2 > s1}]
        if s2 > s1:
            defn = alt
        save_json(os.path.join(a.out, "iterations", "tournament_candidate_B.json"), alt)
    print("  tools attached:", [t["name"] for t in defn["tools"]] or "none")

    print("\n[4/5] Evaluate -> diagnose -> fix loop")
    best, results, history, snaps, jstats = optimize(defn, cases, llm, judge_llm, a.out, a.iters)
    for i, (d, r) in enumerate(snaps):
        save_json(os.path.join(a.out, "iterations", f"agent_v{i}.json"), d)
        save_json(os.path.join(a.out, "iterations", f"results_v{i}.json"), r)
    save_json(os.path.join(a.out, "agent.json"), best)
    save_json(os.path.join(a.out, "iteration_log.json"), history)
    save_json(os.path.join(a.out, "scorecard.json"),
              [{"iteration": h["iteration"], "accepted": h["accepted"], "change": h.get("change"), **h["scorecard"]}
               for h in history if "scorecard" in h])
    save_json(os.path.join(a.out, "final_results.json"), results)

    print("\n[5/5] Writing report")
    meta = {"model": llm.model, "judge_model": judge_llm.model, "llm_calls": llm.calls + (judge_llm.calls if judge_llm is not llm else 0),
            "tokens": llm.tokens + (judge_llm.tokens if judge_llm is not llm else 0), "seconds": round(time.time() - t0)}
    save_json(os.path.join(a.out, "run_meta.json"), {**meta, "brief": brief, "docs": a.docs, "auto": a.auto,
                                                       "tool_decisions": tool_decisions, "judge": jstats})
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(build_report(req, best, tool_decisions, eval_log, cases, history, results, meta, jstats, tournament))
    final = scorecard(results)
    print(f"\nDone. {final['passed']}/{final['n']} pass ({final['overall']}%), holdout {final['holdout']}%.")
    print(f"Agent: {a.out}/agent.json   Report: {a.out}/report.md")
    print(f"Chat with it: python chat.py {a.out}/agent.json")


if __name__ == "__main__":
    main()
