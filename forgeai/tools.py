"""Tool registry. The factory picks from these; the runner executes them.

Each tool has a `needs` rule: a plain check on the requirements + folder that must
be true before the tool may be attached. This is the backstop against the model
attaching a weather tool to an HR bot.
"""
import ast
import csv
import datetime as dt
import operator
import re

import requests


def calculator(expression: str):
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
           ast.Mod: operator.mod}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError("only + - * / ** % and numbers are allowed")

    expr = expression.replace(",", "").replace("x", "*")
    return round(ev(ast.parse(expr, mode="eval").body), 4)


def csv_lookup(file: str, column: str, value: str, data_dir: str = "."):
    import os
    path = os.path.join(data_dir, os.path.basename(file))
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    col = next((c for c in rows[0] if c.lower() == column.lower()), None) if rows else None
    if not col:
        return {"error": f"no column '{column}'. columns: {list(rows[0]) if rows else []}"}
    v = value.lower().strip()
    hits = [r for r in rows if v in str(r[col]).lower()]
    return hits[:10] if hits else {"error": f"no rows where {col} contains '{value}'"}


def current_date():
    d = dt.date.today()
    return {"date": d.isoformat(), "weekday": d.strftime("%A")}


def weather(city: str):
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1}, timeout=15).json()
    if not g.get("results"):
        return {"error": f"city '{city}' not found"}
    loc = g["results"][0]
    w = requests.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
        "latitude": loc["latitude"], "longitude": loc["longitude"],
        "current": "temperature_2m,wind_speed_10m,precipitation"}).json()
    return {"place": loc["name"], "country": loc.get("country"), **w.get("current", {})}


def _words(req):
    # only what the agent must DO. must_refuse is left out on purpose: an HR bot that
    # must refuse weather questions should not get a weather tool.
    import json
    keep = {k: req.get(k) for k in ("brief", "scope", "must_answer", "answers")}
    return json.dumps(keep).lower()


REGISTRY = {
    "csv_lookup": {
        "fn": csv_lookup,
        "description": "Look up rows in a CSV file in the document folder where a column contains a value.",
        "args": {"file": "csv file name", "column": "column name", "value": "text to match"},
        "needs": lambda req, docs: any(d.kind == "csv" for d in docs),
        "needs_reason": "only when the folder contains a CSV file",
    },
    "calculator": {
        "fn": calculator,
        "description": "Evaluate an arithmetic expression, e.g. '1200 * 0.15 + 300'.",
        "args": {"expression": "arithmetic expression"},
        "needs": lambda req, docs: bool(re.search(
            r"\b(calculat|cost|price|total|estimat|quantit|amount|sum|budget|fee|rate|percent|how much)", _words(req))),
        "needs_reason": "only when the requirements involve numbers to compute (cost, total, quantity...)",
    },
    "current_date": {
        "fn": current_date,
        "description": "Get today's date and weekday.",
        "args": {},
        "needs": lambda req, docs: bool(re.search(
            r"\b(today|current date|deadline|days (left|until|remaining)|expir|due date|this week|how long until)", _words(req))),
        "needs_reason": "only when answers depend on today's date (deadlines, expiry, days remaining)",
    },
    "weather": {
        "fn": weather,
        "description": "Current weather (temperature, wind, rain) for a city, from open-meteo.",
        "args": {"city": "city name"},
        "needs": lambda req, docs: bool(re.search(r"\b(weather|forecast|wind|temperature|rain|storm|sea state)", _words(req))),
        "needs_reason": "only when the brief asks about weather or sea/wind conditions",
    },
}


def run_tool(name, args, data_dir="."):
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    fn = REGISTRY[name]["fn"]
    try:
        if name == "csv_lookup":
            return fn(data_dir=data_dir, **args)
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}


def describe(names=None):
    names = names or list(REGISTRY)
    return "\n".join(f"- {n}: {REGISTRY[n]['description']} args={REGISTRY[n]['args']}" for n in names)
