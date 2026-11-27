# ForgeAI report: BluefinAssistant

Generated 2026-11-27 08:24 · model `qwen2.5:3b` · judge `qwen2.5:3b` · 373 LLM calls · ~180150 tokens · 34872s

## Result

**12/23 cases pass (52%).** Dev 47%, holdout 62%. Correct 39%, grounded 100%, refusal accuracy 100%.

Holdout cases were never used to pick fixes, so the holdout number is the fairer estimate of how this agent does on new questions.

## Requirements flags

The brief asks for things the documents cannot support. The agent refuses these instead of guessing:
- **Overtime pay calculation**

Only weakly covered (expect thinner answers): Fatigue reporting procedure, Shore leave entitlements, Returning on board requirements, Sign-off process, Repatriation procedures, Medical sign-off procedures

5 intake answers were assumed, not given by a person (see requirements.md).

## Tool selection

| Tool | Model said | Decision | Why |
|---|---|---|---|
| calculator | attach | attached | requirement check passed |
| csv_lookup | attach | rejected | rule: only when the folder contains a CSV file |
| current_date | attach | rejected | rule: only when answers depend on today's date (deadlines, expiry, days remaining) |
| weather | skip | not attached | model did not pick it |

## Eval set

23 cases kept out of 24 generated (0 discarded by the checks). By type: answerable 12, multi_doc 3, ambiguous 3, out_of_scope 5. Split: 15 dev / 8 holdout.

## Scorecard per iteration

| Iter | Change | Dev | Holdout | Overall | Correct | Grounded | Refusal | Kept? |
|---|---|---|---|---|---|---|---|---|
| 0 | baseline | 40% | 62% | 48% | 39% | 100% | 80% | yes |
| 1 | added rule: "When answering, include all critical information and context provided in the question or context, ensuring no essential details are omitted." | 33% | 62% | 44% | 33% | 100% | 80% | no, reverted |
| 2 | retrieval.top_k 4 -> 6 | 47% | 62% | 52% | 39% | 100% | 100% | yes |
| 3 | retrieval.chunk_size 140 -> 91 (overlap 30) | 40% | 62% | 48% | 33% | 100% | 100% | no, reverted |

## Change log

- **Iteration 1:** targeted `prompt_defect` (dev failures by category: {'prompt_defect': 8, 'retrieval_miss': 1})
  - Change: added rule: "When answering, include all critical information and context provided in the question or context, ensuring no essential details are omitted."
  - Why: the right passage was retrieved but the answer left facts out or skipped citations
  - Targeted cases: case_02, case_03, case_05, case_07, case_10, case_11, case_15, case_20
  - Dev 40% → 33%, holdout 62% → 62%. Fixed: case_20. Newly broken: case_06, case_21.
  - Decision: reverted (dev score did not improve)
- **Iteration 2:** targeted `retrieval_miss` (dev failures by category: {'prompt_defect': 8, 'retrieval_miss': 1})
  - Change: retrieval.top_k 4 -> 6
  - Why: needed passages were not in the top results; widen the net
  - Targeted cases: case_18
  - Dev 40% → 47%, holdout 62% → 62%. Fixed: case_20. Newly broken: none.
  - Decision: kept (dev score improved)
- **Iteration 3:** targeted `retrieval_miss` (dev failures by category: {'prompt_defect': 6, 'wrong_refusal': 1, 'retrieval_miss': 1})
  - Change: retrieval.chunk_size 140 -> 91 (overlap 30)
  - Why: facts were buried in long chunks that scored low; smaller chunks match questions more tightly
  - Targeted cases: case_18
  - Dev 47% → 40%, holdout 62% → 62%. Fixed: none. Newly broken: case_06.
  - Decision: reverted (dev score did not improve)

## What still fails, and why

### prompt_defect (9): the right passage was retrieved but the answer dropped facts, skipped citations or broke format

| Case | Type | Split | Question | Detail |
|---|---|---|---|---|
| case_02 | answerable | dev | What is the maximum time frame within which the head of department must report a | facts were retrieved but left out of the answer: ['Master records', 'breaches to the office'] |
| case_03 | answerable | dev | What is the minimum time required for a seafarer to rest before the ship's depar | facts were retrieved but left out of the answer: ['Anyone who expects to be late must call', 'normal contract length is 4 months for officers'] |
| case_05 | answerable | dev | What is the minimum number of hours of rest required in a 7-day period? | facts were retrieved but left out of the answer: ['77 hours of rest', '7-day period'] |
| case_07 | answerable | dev | What is the policy of Bluefin Marine regarding the reporting of fatigue? | facts were retrieved but left out of the answer: ['no-blame policy', 'safety action', 'no discipline'] |
| case_08 | answerable | holdout | What is the primary responsibility of the Master when a situation at sea is reso | facts were retrieved but left out of the answer: ['board or cargo'] |
| case_09 | answerable | holdout | What is the maximum notice period required for a seafarer to request sign-off at | facts were retrieved but left out of the answer: ['Extensions beyond 30 days are not allowed'] |
| case_11 | answerable | dev | How often are seafarer's hours of rest records checked? | facts were retrieved but left out of the answer: ['Records Each seafarer records their own hours of rest daily', 'The Master signs the records at the end of eac |
| case_15 | multi_doc | dev | According to the shore leave and crew relief policy, when a seafarer is entitled | facts were retrieved but left out of the answer: ['Seafarers are entitled to shore leave when the ship is in port, subject to operational needs, port security r |
| case_17 | ambiguous | holdout | What's the min rating a seafarer need 2 report 2 anon for fatigue probs? | facts were retrieved but left out of the answer: ['A seafarer who does not want to report through the ship can report anonymously'] |

### wrong_refusal (1): the agent refused even though the answer was in front of it

| Case | Type | Split | Question | Detail |
|---|---|---|---|---|
| case_10 | answerable | dev | What is the minimum rating a seafarer must have to report anonymously for fatigu | refused although the facts were in the retrieved context |

### retrieval_miss (1): the retriever never brought back the passage with the answer

| Case | Type | Split | Question | Detail |
|---|---|---|---|---|
| case_18 | ambiguous | dev | If I'm tired or see a buddy is tired at sea, what do I do?? | needed facts were not in the retrieved passages: ['tell head of department', 'complete fatigue report form'] |

## Caveats

- The LLM judge was consulted 154 times (only when string matching was unsure); its two orderings disagreed 16 times. Disagreements count as a miss.
- 1 final cases had an unsure judge verdict; a human should look at those first.
- Eval questions are generated by a small model. Checks guarantee each expected fact really is in its source document, not that the question is one a real user would ask.
- Key-fact matching is strict about numbers on purpose (a small judge model is too lenient on them). An answer that converts units (e.g. '2 weeks' for '14 days') is marked wrong.
