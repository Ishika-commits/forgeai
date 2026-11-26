"""A dumb, deterministic stand-in for the LLM so the whole pipeline can be tested
without Ollama. It reads the '### task:' tag in each prompt and returns plausible JSON.
It is deliberately imperfect (wrong facts, leaky critic rules, weather tool on everything)
so the factory's checks have something to catch."""
import json
import os
import re
import time


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if len(s.split()) >= 5]


def words(t):
    return set(re.findall(r"[a-z0-9]+", t.lower())) - {"the", "a", "of", "to", "is", "in", "and", "what", "how", "for", "my", "i", "do", "be", "on"}


class FakeLLM:
    def __init__(self):
        self.model, self.backend = "fake", "fake"
        self.calls = self.tokens = 0
        self.seconds = 0.0
        self.n = 0

    def stats(self):
        return {"model": "fake", "calls": self.calls}

    def ask(self, prompt, system=None, **kw):
        return self.chat([{"role": "user", "content": prompt}])

    def ask_json(self, prompt, system=None, **kw):
        return json.loads(self.chat([{"role": "user", "content": prompt}], json_mode=True))

    def chat(self, messages, temperature=0.0, json_mode=False, max_tokens=800):
        self.calls += 1
        self.n += 1
        if os.getenv("FAKE_DELAY"):
            time.sleep(float(os.getenv("FAKE_DELAY")))
        user = messages[-1]["content"]
        m = re.search(r"### task: (\w+)", user)
        task = m.group(1) if m else ("agent" if "Context passages:" in user else "tools" if "Tools you may call" in user else "?")
        out = getattr(self, "t_" + task)(user, messages)
        self.tokens += len(user.split())
        return json.dumps(out)

    def t_intake_summarize(self, u, _):
        heads = re.findall(r"^\d+\.\s+(.+)$", u, re.M)
        return {"summary": " ".join(sentences(u)[3:5]), "topics": heads[:8]}

    def t_intake_questions(self, u, _):
        return {"questions": ["Who will use it?", "What must it refuse?", "What tone?", "Anything else?",
                              "Which docs matter most?", "A sixth question that must be cut"]}

    def t_intake_autoanswer(self, u, _):
        qs = re.findall(r"^- (.+)$", u, re.M)
        return {"answers": [{"question": q, "answer": "Assume the narrowest reasonable scope."} for q in qs]}

    def t_intake_requirements(self, u, _):
        topics = []
        for line in re.findall(r"Topics: (.+)", u):
            topics += [t.strip() for t in line.split(",") if t.strip()]
        must = topics[:6]
        if "overtime pay" in u.lower():
            must.append("overtime pay rates")
        return {"name": "Test Assistant", "scope": "Answers questions using the company documents.",
                "audience": "staff", "tone": "plain", "must_answer": must,
                "must_refuse": ["weather forecasts", "legal advice", "medical diagnosis"]}

    def t_guard_check(self, u, _):
        topic = re.search(r"Topic: (.+)", u).group(1)
        passages = u.split('"""')[1]
        tw = words(topic)
        for s in sentences(passages):
            if len(tw & words(s)) >= max(1, len(tw) // 2):
                return {"supported": "yes", "evidence": " ".join(s.split()[:12])}
        return {"supported": "yes", "evidence": "a quote the model made up"}  # lie -> must be caught

    def t_gen_persona(self, u, _):
        return {"persona": "You are a helpful company assistant.", "rules": ["Be brief.", "Use plain English."],
                "refusal_message": "Sorry, I can only help with questions about the company documents."}

    def t_gen_tools(self, u, _):
        picks = [{"name": "weather", "reason": "might be useful"}]
        if ".csv" in u:
            picks += [{"name": "csv_lookup", "reason": "tariff sheet"}, {"name": "calculator", "reason": "costs"}]
        return {"tools": picks}

    def t_eval_answerable(self, u, _):
        passage = u.split('"""')[1]
        ss = sentences(passage)
        s = next((x for x in ss if re.search(r"\d", x)), ss[0] if ss else passage)
        num = re.search(r"\d[\d,.]*\s*\w+", s)
        fact = num.group(0) if num else " ".join(s.split()[-4:])
        if self.n % 5 == 0:
            fact = "999 widgets"  # invented fact -> must be discarded
        q = "Can you tell me about " + " ".join(w for w in s.split()[:7] if not re.search(r"\d", w)) + "?"
        return {"question": q, "key_facts": [fact], "answer": s}

    def t_eval_multidoc(self, u, _):
        parts = u.split('"""')
        fa = sentences(parts[1])[0].split()[:4]
        fb = sentences(parts[3])[0].split()[:4]
        return {"question": "How do " + " ".join(fa) + " and " + " ".join(fb) + " relate?",
                "key_facts_a": [" ".join(fa)], "key_facts_b": [" ".join(fb)]}

    def t_eval_ambiguous(self, u, _):
        q = re.search(r"Original: (.+)", u).group(1)
        return {"question": "pls " + q.lower().replace("can you tell me about", "whats")}

    def t_eval_out_of_scope(self, u, _):
        return {"questions": [{"question": q, "why_refuse": "off topic"} for q in [
            "What will the weather be in Oslo tomorrow?", "Can you write me a poem about cats?",
            "What is the capital of Peru?", "Should I sue my employer?", "What medicine should I take for a cold?",
            "Who won the football last night?", "How do I bake bread?"]]}

    def t_judge_facts(self, u, _):
        fact = re.search(r'Required fact: "(.+)"', u).group(1)
        ans = u.split('"""')[1]
        return {"present": len(words(fact) & words(ans)) >= max(1, len(words(fact)) // 2)}

    def t_critic_rule(self, u, _):
        if "Always state" not in u:
            return {"rule": "Always state 10 hours and 77 hours exactly.", "why": "leaky on purpose"}
        return {"rule": "Quote the specific limits from the passage.", "why": "general"}

    def t_tools(self, u, _):
        q = u.split("Question:")[1]
        for port in ["Singapore", "Rotterdam", "Mumbai"]:
            if port.lower() in q.lower():
                return {"calls": [{"tool": "csv_lookup", "args": {"file": "port_tariffs.csv", "column": "port", "value": port}},
                                  {"tool": "weather", "args": {"city": port}}]}  # weather not attached -> ignored
        return {"calls": []}

    def t_agent(self, u, msgs):
        ctx = u.split("Question:")[0]
        q = u.split("Question:")[1]
        best, score, src = None, 0, None
        cur = None
        for line in ctx.split("\n"):
            mm = re.match(r"\[(.+?)\]$", line.strip())
            if mm:
                cur = mm.group(1)
                continue
            for s in sentences(line):
                sc = len(words(q) & words(s))
                if sc > score:
                    best, score, src = s, sc, cur
        if score < 2:
            return {"answer": "Sorry, I can only help with questions about the company documents.", "sources": [], "refused": True}
        return {"answer": best, "sources": [src], "refused": False}

    def t_(self, u, m):
        return {}
