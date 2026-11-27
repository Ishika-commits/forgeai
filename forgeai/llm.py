"""Thin LLM client. Talks to Ollama by default, or any OpenAI-compatible server.

Also keeps a running count of calls and tokens so the factory can enforce a budget.
"""
import json
import os
import re
import time

import requests


class BudgetExceeded(Exception):
    pass


class LLM:
    def __init__(self, model=None, backend=None, base_url=None, max_tokens_budget=None):
        self.backend = backend or os.getenv("FORGE_BACKEND", "ollama")
        self.model = model or os.getenv("FORGE_MODEL", "qwen2.5:3b")
        if self.backend == "ollama":
            self.base_url = base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        else:
            self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY", "none")
        self.budget = max_tokens_budget
        self.calls = 0
        self.tokens = 0
        self.seconds = 0.0

    # ---- low level -------------------------------------------------------
    def chat(self, messages, temperature=0.0, json_mode=False, max_tokens=800):
        if self.budget and self.tokens >= self.budget:
            raise BudgetExceeded(f"token budget {self.budget} used up")
        t0 = time.time()
        if self.backend == "ollama":
            text, used = self._ollama(messages, temperature, json_mode, max_tokens)
        else:
            text, used = self._openai(messages, temperature, json_mode, max_tokens)
        self.calls += 1
        self.tokens += used
        self.seconds += time.time() - t0
        return text

    def _ollama(self, messages, temperature, json_mode, max_tokens):
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "seed": 7},
        }
        if json_mode:
            body["format"] = "json"
        r = requests.post(f"{self.base_url}/api/chat", json=body, timeout=300)
        r.raise_for_status()
        data = r.json()
        used = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        return data["message"]["content"], used

    def _openai(self, messages, temperature, json_mode, max_tokens):
        body = {"model": self.model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(5):
            r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=300,
                              headers={"Authorization": f"Bearer {self.api_key}"})
            if r.status_code == 400 and "response_format" in body:
                # some providers reject JSON mode; parse_json copes with plain text
                body.pop("response_format")
                continue
            if r.status_code not in (429, 500, 502, 503):
                break
            # free hosted tiers rate-limit per minute; wait and retry
            time.sleep(float(r.headers.get("retry-after", 2 ** attempt * 3)))
        r.raise_for_status()
        data = r.json()
        used = data.get("usage", {}).get("total_tokens", 0)
        return data["choices"][0]["message"]["content"], used

    # ---- helpers -----------------------------------------------------------
    def ask(self, prompt, system=None, temperature=0.0, max_tokens=800):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return self.chat(msgs, temperature=temperature, max_tokens=max_tokens)

    def ask_json(self, prompt, system=None, temperature=0.0, retries=2, max_tokens=1200):
        """Ask for JSON. Small models break JSON often, so we parse loosely and retry
        with the parse error fed back."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        last_err = None
        for _ in range(retries + 1):
            raw = self.chat(msgs, temperature=temperature, json_mode=True, max_tokens=max_tokens)
            try:
                return parse_json(raw)
            except ValueError as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That was not valid JSON ({e}). Reply with only the JSON object."},
                ]
        raise ValueError(f"model never returned valid JSON: {last_err}")

    def stats(self):
        return {"model": self.model, "backend": self.backend, "calls": self.calls,
                "tokens": self.tokens, "seconds": round(self.seconds, 1)}


def parse_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # grab the outermost {...}
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError as e:
            raise ValueError(str(e))
    raise ValueError("no JSON object found")


def load_prompt(prompt_name, **kwargs):
    """Prompts live in prompts/*.txt so they are committed and easy to diff."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "prompts", f"{prompt_name}.txt"), encoding="utf-8") as f:
        text = f.read()
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def make_llm(model=None, max_tokens_budget=None):
    """FORGE_BACKEND=fake swaps in the scripted test model (tests/fake_llm.py).
    For trying the UI and plumbing without Ollama only; its scores mean nothing."""
    if os.getenv("FORGE_BACKEND") == "fake":
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))
        from fake_llm import FakeLLM
        return FakeLLM()
    return LLM(model=model, max_tokens_budget=max_tokens_budget)
