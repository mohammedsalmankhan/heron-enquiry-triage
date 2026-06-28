# Customer Enquiry Triage & Cost Estimation Prototype

A proof-of-concept tool built for the Heron Joinery AI & Digital Transformation
Internship application, demonstrating one of the internship's named "key
activities": **customer-enquiry triage, requirements summarisation, and cost
and price estimation.**

## What it does

Given a free-text customer enquiry email, the pipeline:

1. **Extracts structured fields** — product type, quantity, dimensions,
   material, urgency, commercial vs. residential signal, and any timeframe
   mentions — using rule-based pattern matching (regex + keyword lookup).
2. **Flags extraction confidence** (High / Medium / Low) based on which
   fields were successfully found, so a human estimator knows at a glance
   which enquiries need a closer read.
3. **Generates a rough price range** from the extracted fields using a
   configurable rate table, applying urgency surcharges, commercial/trade
   discounts, and volume discounts where applicable.
4. **Surfaces everything it's unsure about** as explicit flags rather than
   silently guessing — e.g. "no specific rate for this product/material
   combination, used default rate, verify manually."

Ten realistic, fully invented joinery customer enquiries are included as
sample data (`data/sample_enquiries.json`) to demonstrate the pipeline end
to end.

## Why rule-based extraction, not an LLM API call

This was a deliberate choice, not a fallback because I lacked API access.
For a fixed, well-defined vocabulary (window/door types, materials,
dimensions), a rule-based system is:

- **Fully explainable** — an estimator can see exactly why a field was or
  wasn't extracted, which matters a great deal when the output feeds into
  a price quote a real customer will see.
- **Testable with hard guarantees** — every extraction rule has a unit
  test with a known right answer. An LLM-based extractor's behaviour is
  harder to pin down this precisely without a large labelled evaluation set.
- **Free to run at scale, with zero per-enquiry API cost or latency.**

The honest tradeoff: it only handles phrasing it was built to expect. See
"Known limitations" below, and "Path to production" for where an LLM
genuinely earns its place in a v2.

## Known limitations (found and documented during testing)

- **Natural phrasing without an "x" separator is missed.** "1.2m wide by
  1.5m tall" is not currently parsed, only the "1.2m x 1.5m" / "900mm x
  1200mm" format is. This is a real gap, not a hidden one — it's covered
  by `test_dimension_extraction_known_limitation_natural_phrasing` and the
  pipeline correctly falls back to "manual quote required" rather than
  guessing.
- **A unit must be present on both numbers in a dimension pair.** "1.4 x
  1.8m" (unit omitted on the first number) is not parsed. Same honest
  fallback behaviour applies.
- **Quantity words like "a single" or "a pair" aren't converted to
  numbers.** Only digit quantities ("3 sash windows") are picked up.
- **Pricing is built on illustrative placeholder rates**, not Heron's
  actual costs. The logic (area-based calculation, urgency/discount
  adjustments) is real and tested; the £/sqm figures in
  `pricing.py` are not. Swapping in real rates is a one-line table edit.

## A real bug found and fixed while building this

The first version of the dimension regex used the pattern `(m|mm)` for the
unit, which is a greedy alternation: it matched `mm` as `m` followed by a
literal `m`, so "1200mm" was read as "1200 metres." This produced
six-figure price estimates for ordinary residential windows. Fixed by
reordering the alternation to `(mm|m)` so the longer match is tried first.
There's a regression test (`test_mm_not_misread_as_metres`) specifically
guarding against this recurring.

I'm including this in the README deliberately — it's a more useful signal
of how I work than a project with no visible mistakes would be.

## Path to production

If Heron wanted to take this further:

1. **Replace/augment the rule-based extractor with an LLM-based one**,
   prompt-engineered and evaluated against a labelled set of real (anonymised)
   Heron enquiries — this is where an LLM genuinely adds value, handling the
   long tail of phrasing a rule-based system can't anticipate.
2. **Replace placeholder pricing with real Heron cost data** — material
   costs, labour rates, current lead times by product line.
3. **Add a feedback loop** — when an estimator corrects an extraction or
   price, log it, so the gaps become a prioritised backlog rather than
   guesswork.
4. **Wrap in a simple internal web form or email-forwarding integration**
   so enquiries land directly in the tool rather than requiring manual copy/paste.

## Running it

```bash
cd enquiry_triage
python3 src/pipeline.py          # runs the full pipeline on sample data
python3 -m pytest tests/ -v      # runs the 20-test suite
```

## Project structure

```
enquiry_triage/
├── data/
│   ├── sample_enquiries.json     # 10 synthetic joinery customer enquiries
│   └── pipeline_output.json      # generated output (created on run)
├── src/
│   ├── extractor.py               # rule-based field extraction
│   ├── pricing.py                  # cost estimation engine
│   └── pipeline.py                 # ties extraction + pricing together
├── tests/
│   └── test_pipeline.py            # 20 pytest unit tests
└── README.md
```
## About

Built by Mohammed Salman Khan, MSc Artificial Intelligence at Ulster University.

Email: mohammedsalmankhans636@gmail.com
LinkedIn: https://www.linkedin.com/in/mohammedsalmankhans/
GitHub: https://github.com/mohammedsalmankhan
