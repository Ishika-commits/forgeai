"""Generic chat runner: loads any agent.json that ForgeAI produced.

    python chat.py runs/crew_rest/agent.json
"""
import argparse

from forgeai.agent import load_agent
from forgeai.llm import make_llm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--model", default=None)
    ap.add_argument("--debug", action="store_true", help="show retrieved chunks")
    a = ap.parse_args()

    agent = load_agent(a.agent, make_llm(model=a.model))
    d = agent.defn
    print(f"\n{d['name']}  (tools: {', '.join(t['name'] for t in d['tools']) or 'none'})")
    print("Type a question, or 'quit'.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("quit", "exit", "q"):
            break
        if not q:
            continue
        out = agent.answer(q)
        print(f"\nbot> {out['answer']}")
        if out.get("sources"):
            print(f"     sources: {', '.join(map(str, out['sources']))}")
        for t in out.get("tool_calls", []):
            print(f"     used {t['tool']}({t['args']})")
        if a.debug:
            for h in out["retrieved"]:
                print(f"     [{h['score']}] {h['id']}: {h['text'][:100]}...")
        print()


if __name__ == "__main__":
    main()
