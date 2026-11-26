# ForgeAI

You give ForgeAI a one-paragraph brief and a folder of documents. It builds an agent from them, writes its own test set, grades the agent, fixes what it can in up to 3 rounds, and then writes a report on what still fails.

Everything runs on a small local model through Ollama (default `qwen2.5:3b`). No LangChain or agent framework is used. It's plain Python, so every step can be read and changed.

## Quick start

```bash
# 1. install Ollama (https://ollama.com), then:
ollama pull qwen2.5:3b
ollama pull nomic-embed-text      # optional, only used if the optimizer switches to hybrid retrieval

# 2. python deps
pip install -r requirements.txt

# 3. build an agent (interactive: asks up to 5 questions, then shows the requirements for approval)
python forge.py --brief demos/crew_rest/brief.txt --docs demos/crew_rest/docs --out runs/crew_rest

# unattended (what the review needs): no questions, no checkpoint
python forge.py --brief "I need an assistant that ..." --docs path/to/folder --out runs/new --auto

# 4. chat with any produced agent
python chat.py runs/crew_rest/agent.json

# both demos in one go
bash run_demos.sh
```

Useful flags: `--judge-model llama3.2:3b` uses a different model as the judge, `--budget 400000` caps tokens for the run, `--tournament` makes two candidate prompts and lets the evals pick one, and `--iters 3` sets the number of fix rounds.

The client also speaks the OpenAI API format. Set `FORGE_BACKEND=openai`, `OPENAI_BASE_URL=...` and `FORGE_MODEL=...` to point it at LM Studio, vLLM, or anything else that serves that format.

## Dashboard

```bash
python server.py          # then open http://localhost:8501
```

A web UI on top of the same pipeline, with no extra dependencies (standard-library server, one HTML page):

- **New run.** Pick a demo or upload your own documents, write a brief, and watch the five stages progress with a live log.
- **Results.** Pass rate, the honest holdout score, score per iteration, what each fix changed and whether it was kept, and every remaining failure grouped by cause.
- **Requirements.** The groundability check, with the topics it flagged.
- **Eval set.** Every generated case with its expected facts and result, plus the cases the checks threw out.
- **Agent.** The system prompt (rules added by the fix loop are highlighted), retrieval settings, and the tool decisions with reasons.
- **Try the agent.** Chat with the produced agent, next to the passages and tool calls it used for each answer.
- **Report.** The rendered `report.md`.

`FORGE_BACKEND=fake python server.py` runs everything against the scripted test model, so you can click through the UI without Ollama. Its scores mean nothing.

## What happens in a run

```
brief + docs
   │
   ├─ 1. Intake ─────────── summarise each doc, ask ≤5 questions, write requirements
   │      └─ groundability guard: is every must-answer topic actually in the docs?
   │         unsupported topics → flagged + moved to must-refuse
   │      └─ human checkpoint: approve / edit requirements (skipped with --auto)
   │
   ├─ 2. Eval generation ── 12 answerable, 3 multi-doc, 3 ambiguous, 5 out-of-scope
   │      └─ every case is checked before it's kept; discards are logged
   │      └─ split 70/30 into dev / holdout
   │
   ├─ 3. Agent generation ─ persona + rules, retrieval params, tools, output contract
   │      └─ tool picks must pass a rule check (no weather tool on an HR bot)
   │
   ├─ 4. Loop (max 3) ───── run evals → classify failures → one targeted fix → re-run
   │      └─ fix kept only if the dev score goes up, otherwise reverted
   │
   └─ 5. Report ─────────── scorecard per iteration, change log, what still fails and why
```

## Output of a run

```
runs/<name>/
  requirements.md / .json    scope, audience, tone, must-answer, must-refuse, groundability table, Q&A
  evalset.json               generated cases + generation log (incl. discarded cases and why)
  agent.json                 the final agent definition (this is what chat.py loads)
  iterations/agent_vN.json   the definition at each iteration
  iterations/results_vN.json per-case results at each iteration
  iteration_log.json         what changed, why, which cases it targeted, score before/after
  scorecard.json             scores per iteration
  report.md                  the human-readable report
  run_meta.json              model, tokens, time, tool decisions, judge stats
```

## How each requirement is handled

| # | Requirement | Where | How |
|---|---|---|---|
| 1 | Intake interviewer | `intake.py` | Summarises each doc, asks at most 5 questions (cut to 5 in code even if the model asks more), writes the requirements. With `--auto` the model answers its own questions conservatively, and those answers are marked *assumed*. |
| 2 | Groundability guard | `intake.py: groundability()` | For each must-answer topic, retrieves passages and asks the model whether they support it, with an exact quote as evidence. A "yes" only counts if the quote really is in the passages **and** is about the topic. Unsupported topics are flagged and moved to must-refuse. |
| 3 | Agent generator | `generator.py` | Model writes persona, rules and refusal message. Fixed grounding rules are always added. Retrieval params come from document stats. Output contract is JSON `{answer, sources, refused}`. |
| 4 | Eval generator | `evalgen.py`, `prompts/eval_*.txt` | Cases are generated from document chunks. Key facts must be copied from the source passage; facts that aren't really there get the case thrown out. |
| 5 | Judge | `judge.py` | Deterministic checks first. The LLM judge is used only when string matching is unsure (see below). |
| 6 | Critic–optimizer | `optimizer.py` | Every failure gets one of 4 categories. The most common one in dev gets **one** targeted fix. Everything is logged. |
| 7 | Honest report | `report.py` | Dev and holdout scores shown separately, failures listed with reasons, caveats written out. |
| 8 | Runnable product | `chat.py`, `agent.py` | The same `Agent` class runs in the chat CLI and in the evals, so what's tested is what ships. |
| 9 | Two demos | `demos/`, `runs/` | Crew rest-hours policy bot (3 PDFs, no tools) and port-call cost bot (CSV + 2 PDFs, CSV lookup + calculator). |

Stretch goals done: human checkpoint, prompt tournament (`--tournament`), and budget with early stopping (`--budget` caps tokens; a fix that doesn't raise the dev score is reverted, and the loop stops early when every dev case passes or no untried fix is left).

## Design decisions (and why)

**The pipeline checks itself.** The model that writes the tests, the agent, and the judge can all be the same 3B model, and a 3B model will make things up. So the places where it's most likely to lie each get a plain-code check:

- **Eval facts.** Every expected fact has to actually appear in the source passage. Cases that fail this get dropped and logged. You can see in the report how many the generator got wrong.
- **Questions that give themselves away.** If the answer is already written in the question, the case is thrown out.
- **Out-of-scope questions.** If the documents clearly answer an "out of scope" question (high retrieval score), the case is thrown out, because it isn't really out of scope.
- **Guard evidence.** The model's "yes, the docs cover this" only counts with an exact quote, and the quote has to be on-topic. Small models like quoting a real but unrelated sentence.
- **Tool picks.** Each tool has a rule (CSV lookup only if there is a CSV; weather only if the brief mentions weather/wind). The model's pick has to pass the rule.
- **Optimizer "fixes".** A rule the critic writes is rejected if it contains a number or any expected answer from the tests. Otherwise the loop could "fix" a failure by pasting the answer into the prompt.
- **Overfitting.** Fixes are chosen using dev cases only. Holdout cases are scored every round but never looked at when choosing, so the holdout number is the honest one.

**Judge: deterministic first, LLM as a narrow fallback.** Each answer is checked fact by fact. Numbers must match exactly, and words are matched loosely. Only when that's unsure is the model asked a yes/no question about one fact. Defences against the known judge biases:

- *Position bias.* There are no A-vs-B comparisons. Each LLM verdict is also asked twice with the answer and fact in opposite order, and if the two disagree the fact counts as missing and the case is flagged.
- *Verbosity bias.* The judge answers a per-fact checklist, never "rate this answer", so a longer answer gains nothing.
- *Self-preference.* The judge never compares against a model-written ideal answer, only against facts copied from the documents. `--judge-model` lets you use a different model.

Grounding is checked in code too. The answer must cite a file it actually retrieved, and any number in the answer must appear in the retrieved text, the tool output or the question.

**Failure categories are decided in code, not by the model:**

| Category | Rule |
|---|---|
| `retrieval_miss` | the needed facts were not in the retrieved passages |
| `wrong_refusal` | refused, but the facts were in the retrieved passages |
| `hallucination` | numbers not in the context, cited a file it never retrieved, or answered an out-of-scope question with made-up details |
| `prompt_defect` | facts were retrieved but the answer left them out, or it didn't cite, or it broke the JSON contract |

**Fixes are small and one at a time.**

- *Retrieval miss:* raise `top_k`, then shrink chunks, then switch to hybrid retrieval.
- *The other categories:* add one general rule written by the critic, or a fallback rule if the critic's rule gets rejected.

One change per iteration means the before/after score can be credited to that change.

**TF-IDF by default.** It needs no model download, gives the same result every time, and works well on short policy documents. Hybrid (TF-IDF plus Ollama embeddings) is something the optimizer can switch on when keyword search is missing paraphrased questions.

## Demo data

Both demos use a made-up company, Bluefin Marine. The documents were written with an LLM. The prompts are in `demos/SYNTHESIS_PROMPTS.md`, and `demos/make_demo_docs.py` rebuilds the PDFs.

- **crew_rest.** The brief asks about rest hours, fatigue reporting, shore leave and relief, and also overtime pay. The documents say nothing about overtime pay, on purpose, so the groundability guard should flag it. No tools should be attached.
- **port_costs.** The brief needs tariff lookups and cost arithmetic, so it should get `csv_lookup` and `calculator` and nothing else.

## Tests

```bash
python tests/test_pipeline.py
```

These run the whole pipeline on both demos with a fake, deliberately unreliable LLM (`tests/fake_llm.py`). It invents facts, quotes irrelevant evidence, tries to attach a weather tool and writes a leaky critic rule. The tests check that the factory catches each of these. They test the plumbing, not answer quality.

## Known limitations

- With small documents the eval set is small (~23 cases), so one case is worth ~4 points. Treat differences under ~10 points as noise.
- Number matching is strict on purpose. "2 weeks" for "14 days" is marked wrong.
- Eval questions are checked for factual grounding, not for whether a real user would phrase them that way.
- The calculator and CSV lookup are basic. There are no joins across CSVs and no unit conversion.
- Each run's scores depend on the model. Expect different numbers on a 3B model than on a 7B one.
