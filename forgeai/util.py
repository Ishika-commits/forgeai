import json
import os
import re


def save_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm(text):
    t = str(text).lower()
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)      # 1,200 -> 1200
    t = re.sub(r"[^a-z0-9.%$ ]+", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)       # drop full stops, keep 2.5
    return re.sub(r"\s+", " ", t).strip()


STOP = set("a an the of to in on for and or is are be by with at as from that this it its per any "
           "how what when who which does do can i my".split())


def numbers_in(text):
    return set(re.findall(r"\d+(?:\.\d+)?", norm(text)))


def fact_in_text(fact, text):
    """Deterministic fact match.
    - every number in the fact must appear in the text
    - and most of the fact's content words must appear
    Returns 1.0 (clear yes), 0.0 (clear no) or a value in between (unsure)."""
    f, t = norm(fact), norm(text)
    if not f:
        return 0.0
    if f in t:
        return 1.0
    nums = numbers_in(f)
    if nums and not nums <= numbers_in(t):
        return 0.0
    words = [w for w in f.split() if w not in STOP and not re.fullmatch(r"[\d.]+", w)]
    if not words:
        return 1.0 if nums else 0.0
    tw = set(t.split())
    hit = sum(1 for w in words if w in tw or (len(w) > 4 and any(x.startswith(w[:5]) for x in tw)))
    return round(hit / len(words), 2)


REFUSAL_PATTERNS = re.compile(
    r"(i can(?:no|')t help|i(?: am|'m) (?:not able|unable)|outside (?:of )?(?:my|the) scope|"
    r"not covered|don't have information|do not have information|cannot answer|can't answer|"
    r"no information (?:about|on)|not able to answer|i can only help)", re.I)


def looks_like_refusal(text):
    return bool(REFUSAL_PATTERNS.search(str(text)))


def topic_overlap(topic, text):
    """Share of the topic's content words that show up in text (prefix match, so
    'reporting' matches 'report')."""
    tw = [w for w in norm(topic).split() if w not in STOP and len(w) > 2]
    xs = set(norm(text).split())
    if not tw:
        return 0.0
    hit = sum(1 for w in tw if any(x[:5] == w[:5] for x in xs))
    return hit / len(tw)
