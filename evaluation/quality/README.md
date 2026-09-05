# Quality evaluation

Measures retrieval and answer quality by replaying a fixed dataset through the
real agent workflow and scoring the results. It runs entirely in-process
against the retrieval service's in-memory keyword corpus and the deterministic
inference backend, so one command produces the same report from a clean
checkout with no GPU, model download, database, or running service.

## Run it

```bash
python -m evaluation.quality.run                     # writes evaluation/reports/quality-latest.{json,md}
python -m evaluation.quality.run --check-thresholds  # also fails (exit 1) on a regression
make eval-quality
make eval-quality-check
```

Useful flags: `--dataset PATH`, `--json-out PATH`, `--markdown-out PATH`,
`--top-k N`, `--judge keyword`, `--thresholds PATH`, `--quiet`.

The JSON report is the machine-readable artifact; the Markdown one is for
people. `evaluation/reports/` is git-ignored — move a report you want to keep
into `docs/`.

## What it measures

| Metric | Definition | Scope |
| --- | --- | --- |
| Retrieval recall | share of a case's expected evidence ids that appear in the top-k | retrieval + rewrite cases |
| Retrieval MRR | mean reciprocal rank of the first expected id | retrieval + rewrite |
| Retrieval precision@1 | top result is expected evidence | retrieval + rewrite |
| Citation presence | the answer carries a `[n]` marker and at least one citation is attached | retrieval + rewrite |
| Citation accuracy | share of attached citations that are expected evidence (1.0 when a direct / insufficient case cites nothing) | all cases |
| Answer correctness | the judge passed the answer | all cases |
| Hallucination rate | share of answers asserting more than the retrieved evidence supports — a fabricated citation, a `[n]` marker with nothing attached, a direct answer that cites, or an insufficient-evidence question answered anyway | all cases |

Retrieval metrics come from a clean single-pass retrieval on the question;
citation, correctness, and hallucination come from the end-to-end workflow
result (so the bounded rewrite is included).

## The dataset

`evaluation/datasets/quality-core-v1.json` is a versioned record file
(`schema` = `quality-eval-record/v1`). Every case has an `id`, a `question`, a
`kind`, a `reference_answer`, and case-insensitive `answer_must_include` /
`answer_must_not_include` substrings. Retrieving cases also name
`expected_evidence` document ids. The four kinds must all be present:

- **direct** — answered without retrieval (greetings, "what can you do"); must
  cite nothing.
- **retrieval** — answerable from a single retrieval pass.
- **rewrite** — the first retrieval is weak; the workflow's one bounded query
  rewrite recovers it.
- **insufficient** — no corpus evidence exists; the answer must say so and cite
  nothing.

### Adding a case

1. Add an object to `cases` with a unique `id` and the right `kind`.
2. Put load-bearing facts (a number, a name) in `answer_must_include` so the
   check survives rewording; keep `expected_evidence` to the document ids that
   genuinely support the answer.
3. Run `python -m evaluation.quality.run` and read the per-case table. The
   deterministic backend answers with the first sentence of the top-ranked
   document, so a case only "passes" when that sentence contains your keys.
4. If the aggregate shifts, re-measure and update
   `evaluation/quality/thresholds.json`.

## CI gate

`thresholds.json` holds floors (`min`) and ceilings (`max`), set just beneath
the current baseline. `test_quality_regression.py` runs the full evaluation
inside the normal `pytest` suite and fails when a bound is breached, so CI
catches a quality regression with no extra infrastructure.

## Judges

`KeywordJudge` (the default) is deterministic: it checks the case's substring
keys. `ModelJudge` is a tested seam — give it a `client(prompt) -> str` and it
parses a `SCORE` / `VERDICT` verdict — but it is never wired into the default
run or CI because its output is not reproducible.

## Limitations

- **Small corpus, deterministic backend.** Four documents and a first-sentence
  answer synthesiser. The numbers describe *this* offline stack; they are a
  regression signal, not a claim about a production model.
- **Citation accuracy counts every attached citation.** The workflow attaches
  all evidence above the relevance floor even though the deterministic answer
  only references `[1]`, so a case with one on-target and one incidental
  citation scores 0.5 there.
- **Keyword correctness is shallow.** It confirms the load-bearing facts are
  present, not that the prose is good. Plugging a real model backend and the
  `ModelJudge` would deepen this.
