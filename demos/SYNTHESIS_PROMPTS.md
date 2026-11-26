# How the demo documents were made

All demo documents are synthetic. Bluefin Marine is a made-up company. The text was
drafted with an LLM (Claude) using the prompts below, then lightly edited by hand so the
numbers are consistent across files. `make_demo_docs.py` turns the text into PDFs.

## Demo 1: crew rest (3 PDFs)

> Write the hours of rest policy for a fictional ship manager, Bluefin Marine. Base the
> structure on how real ISM-style company policies read (purpose, scope, numbered sections),
> loosely following MLC 2006 / STCW rest-hour limits. Include: minimum rest per 24 hours and
> per 7 days, how rest can be split, maximum gap between rest periods, drills, compensatory
> rest, record keeping and who signs, exceptions for emergencies. About 600 words. Use exact
> numbers.

> Write a fatigue reporting procedure for the same company: who to report to, which form,
> deadlines for the Master and the shore office, no-blame policy, a sleepiness scale threshold
> for standing someone down from watch, anonymous reporting, review cycle. About 500 words.

> Write a shore leave and crew relief policy for the same company: shore leave conditions and
> return time, contract lengths for officers and ratings, extensions, sign-off notice,
> repatriation costs, medical sign-off. About 500 words. Do NOT mention wages or overtime pay.

(The last line is deliberate: the brief asks about overtime pay, and the documents don't cover it,
so the groundability guard has something real to catch.)

## Demo 2: port costs (CSV + 2 PDFs)

> Make a CSV tariff sheet for 6 world ports with 3 gross tonnage bands each. Columns: port,
> country, gt_band, port_dues_usd_per_gt, pilotage_usd, towage_usd_per_tug, min_tugs,
> berth_usd_per_hour. Realistic-looking but invented numbers; bigger bands cost more.

> Write the standard agency terms for a fictional port agent working for Bluefin Marine:
> agency fee per call, overtime and weekend surcharges (which service they apply to, what
> percentage, which hours), advance payment and balance terms, dispute window, cancellation
> fee, currency. About 500 words, numbered clauses.

> Write short port notes for the same 6 ports: one or two operational restrictions each
> (pilotage rules, night navigation, draft limits, documents needed before arrival). About 400 words.
