"""ForgeAI dashboard. No extra dependencies: standard library server + one HTML page.

    python server.py            # then open http://localhost:8501
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from forgeai.agent import load_agent
from forgeai.llm import make_llm

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(ROOT, "runs")
UPLOADS = os.path.join(ROOT, "uploads")
UI = os.path.join(ROOT, "ui", "index.html")

JOBS = {}
AGENTS = {}
LOCK = threading.Lock()


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def run_summary(name):
    d = os.path.join(RUNS, name)
    meta = read_json(os.path.join(d, "run_meta.json"), {})
    cards = read_json(os.path.join(d, "scorecard.json"), [])
    final = [c for c in cards if c.get("accepted")]
    req = read_json(os.path.join(d, "requirements.json"), {})
    return {"name": name, "agent_name": req.get("name", name), "brief": meta.get("brief", req.get("brief", "")),
            "model": meta.get("model"), "final": final[-1] if final else None,
            "complete": os.path.exists(os.path.join(d, "report.md")),
            "mtime": os.path.getmtime(d)}


def run_detail(name):
    d = os.path.join(RUNS, name)
    out = {k: read_json(os.path.join(d, f"{k}.json")) for k in
           ("requirements", "evalset", "agent", "scorecard", "iteration_log", "final_results", "run_meta")}
    try:
        out["report"] = open(os.path.join(d, "report.md"), encoding="utf-8").read()
    except OSError:
        out["report"] = ""
    out["name"] = name
    return out


def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", s).strip("_")[:40] or "run"


def start_job(body):
    name = safe_name(body.get("name") or "run_" + time.strftime("%H%M%S"))
    if body.get("files"):
        docs = os.path.join(UPLOADS, name)
        os.makedirs(docs, exist_ok=True)
        for f in body["files"]:
            fname = os.path.basename(f["name"])
            with open(os.path.join(docs, fname), "wb") as fh:
                fh.write(base64.b64decode(f["data"].split(",")[-1]))
    else:
        docs = os.path.join(ROOT, body["docs_dir"])
    cmd = [sys.executable, "-u", "forge.py", "--brief", body["brief"], "--docs", docs,
           "--out", os.path.join(RUNS, name), "--auto", "--iters", str(body.get("iters", 3))]
    if body.get("model"):
        cmd += ["--model", body["model"]]
    if body.get("tournament"):
        cmd.append("--tournament")
    job = {"id": uuid.uuid4().hex[:8], "run": name, "lines": [], "stage": 0, "status": "running", "started": time.time()}
    JOBS[job["id"]] = job

    def work():
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, text=True, bufsize=1)
        buf = ""
        while True:
            ch = p.stdout.read(1)
            if not ch:
                break
            if ch in "\r\n":
                line = buf.strip()
                buf = ""
                if not line:
                    continue
                m = re.match(r"\[(\d)/5\]", line)
                if m:
                    job["stage"] = int(m.group(1))
                # progress lines overwrite the previous progress line
                if line.startswith("[") and "] case " in line and job["lines"] and "] case " in job["lines"][-1]:
                    job["lines"][-1] = line
                else:
                    job["lines"].append(line)
            else:
                buf += ch
        p.wait()
        job["status"] = "done" if p.returncode == 0 else "failed"
        if p.returncode == 0:
            job["stage"] = 6
    threading.Thread(target=work, daemon=True).start()
    return job


def chat(body):
    run = safe_name(body["run"])
    path = os.path.join(RUNS, run, "agent.json")
    with LOCK:
        if run not in AGENTS:
            AGENTS[run] = load_agent(path, make_llm(model=body.get("model") or None))
        agent = AGENTS[run]
    out = agent.answer(body["question"])
    return out


def health():
    if os.getenv("FORGE_BACKEND") == "fake":
        return {"ok": True, "backend": "fake (test model; scores mean nothing)", "models": ["fake"]}
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        tags = requests.get(f"{url}/api/tags", timeout=2).json()
        return {"ok": True, "backend": "ollama", "models": [m["name"] for m in tags.get("models", [])],
                "default": os.getenv("FORGE_MODEL", "qwen2.5:3b")}
    except Exception:
        return {"ok": False, "backend": "ollama", "models": [], "error": f"Ollama is not reachable at {url}. Start it with: ollama serve"}


def demos():
    out = []
    base = os.path.join(ROOT, "demos")
    for n in sorted(os.listdir(base)):
        b = os.path.join(base, n, "brief.txt")
        if os.path.isfile(b):
            out.append({"name": n, "brief": open(b, encoding="utf-8").read().strip(), "docs_dir": f"demos/{n}/docs",
                        "files": sorted(os.listdir(os.path.join(base, n, "docs")))})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        try:
            if p == "/":
                return self.send(open(UI, "rb").read(), ctype="text/html; charset=utf-8")
            if p == "/api/health":
                return self.send(health())
            if p == "/api/demos":
                return self.send(demos())
            if p == "/api/runs":
                os.makedirs(RUNS, exist_ok=True)
                names = [n for n in os.listdir(RUNS) if os.path.isdir(os.path.join(RUNS, n))]
                return self.send(sorted((run_summary(n) for n in names), key=lambda r: -r["mtime"]))
            if p.startswith("/api/runs/"):
                name = safe_name(p.split("/")[3])
                if not os.path.isdir(os.path.join(RUNS, name)):
                    return self.send({"error": "no such run"}, 404)
                return self.send(run_detail(name))
            if p.startswith("/api/jobs/"):
                job = JOBS.get(p.split("/")[3])
                return self.send(job or {"error": "no such job"}, 200 if job else 404)
            self.send({"error": "not found"}, 404)
        except Exception as e:
            self.send({"error": str(e)}, 500)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/forge":
                if not body.get("brief", "").strip():
                    return self.send({"error": "Write a brief first."}, 400)
                if not body.get("files") and not body.get("docs_dir"):
                    return self.send({"error": "Pick a demo folder or upload documents."}, 400)
                return self.send(start_job(body))
            if self.path == "/api/chat":
                return self.send(chat(body))
            self.send({"error": "not found"}, 404)
        except requests.exceptions.ConnectionError:
            self.send({"error": "Can't reach the model. Is Ollama running? (ollama serve)"}, 503)
        except Exception as e:
            self.send({"error": str(e)}, 500)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8501"))
    print(f"ForgeAI dashboard on http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
