"""End-to-end smoke test with the fake LLM. Run: python -m pytest tests -q
(or just: python tests/test_pipeline.py)"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fake_llm import FakeLLM  # noqa: E402
from forgeai.agent import load_agent  # noqa: E402
from forgeai.docs import load_folder  # noqa: E402
from forgeai.evalgen import generate_evals  # noqa: E402
from forgeai.generator import generate  # noqa: E402
from forgeai.intake import run_intake  # noqa: E402
from forgeai.optimizer import leaks, optimize  # noqa: E402
from forgeai.report import build_report  # noqa: E402
from forgeai.tools import calculator  # noqa: E402
from forgeai.util import fact_in_text, save_json  # noqa: E402


def run_demo(name):
    docs_dir = os.path.join(ROOT, "demos", name, "docs")
    brief = open(os.path.join(ROOT, "demos", name, "brief.txt")).read()
    out = tempfile.mkdtemp()
    llm = FakeLLM()
    docs = load_folder(docs_dir)
    req = run_intake(brief, docs, llm, out, auto=True)
    cases, elog = generate_evals(req, docs, llm)
    defn, decisions = generate(req, docs, docs_dir, out, llm)
    best, results, history, snaps, js = optimize(defn, cases, llm, llm, out, 3)
    save_json(os.path.join(out, "agent.json"), best)
    rep = build_report(req, best, decisions, elog, cases, history, results,
                       {"model": "fake", "judge_model": "fake", "llm_calls": llm.calls, "tokens": 0, "seconds": 0}, js)
    return req, cases, elog, defn, decisions, history, rep, out, llm


def test_crew_rest():
    req, cases, elog, defn, decisions, history, rep, out, llm = run_demo("crew_rest")
    assert len(req["qa"]) <= 5
    assert "overtime pay rates" in req["unsupported_topics"]          # guard caught the gap
    assert defn["tools"] == []                                         # no weather tool on a policy bot
    assert any(d["tool"] == "weather" and d["decision"] == "rejected" for d in decisions)
    assert any("999 widgets" in str(d) or "key facts" in d["why"] for d in elog["discarded"])
    for c in cases:                                                    # every kept fact is really in its source
        assert c["should_refuse"] or c["key_facts"]
    assert {c["split"] for c in cases} == {"dev", "holdout"}
    assert "What still fails" in rep
    agent = load_agent(os.path.join(out, "agent.json"), llm)
    a = agent.answer("How many hours of rest in any 24-hour period?")
    assert "10 hours" in a["answer"]


def test_port_costs():
    req, cases, elog, defn, decisions, history, rep, out, llm = run_demo("port_costs")
    names = sorted(t["name"] for t in defn["tools"])
    assert names == ["calculator", "csv_lookup"], names
    agent = load_agent(os.path.join(out, "agent.json"), llm)
    a = agent.answer("What is the pilotage cost in Singapore?")
    assert [t["tool"] for t in a["tool_calls"]] == ["csv_lookup"]     # weather call was dropped


def test_helpers():
    assert calculator("1,450 * 0.3") == 435.0
    assert fact_in_text("77 hours", "at least 77 hours of rest") == 1.0
    assert fact_in_text("77 hours", "at least 70 hours of rest") == 0.0
    assert leaks("Always say 77 hours", [{"key_facts": ["77 hours"]}])
    assert not leaks("Quote limits exactly", [{"key_facts": ["77 hours"]}])


if __name__ == "__main__":
    test_helpers()
    test_crew_rest()
    test_port_costs()
    print("all tests passed")
