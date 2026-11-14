# Eval set

Ten to fifteen CV+JD pairs I scored by hand. Every prompt or model change is run
against this set and the delta is reported before merging (AGENTS.md).

## Layout

```
eval/
  cases/            one YAML per pair
    local/          the real pairs (git-ignored: a JD is not mine to publish)
  gold/             the hand labels, same relative path as the case
    local/
  reports/          generated, git-ignored
  baseline.json     last accepted run, git-ignored
```

A case and its gold file share a name: `cases/local/01-fintech.yaml` is labelled
by `gold/local/01-fintech.yaml`. A case without gold stops the run; it is never
silently skipped.

## Case file

```yaml
id: 01-fintech
title: Senior Backend Engineer
company: Example Payments # optional
expect: analysis # optional, defaults to analysis
cv: |
  <the CV text, verbatim>
jd: |
  <the job post, verbatim>
```

## Gold file

```yaml
requirements:
  - text: Strong Go
    verdict: strong # strong | partial | gap
    note: quoted the order service line # optional, for me only
```

`text` may be paraphrased; it is matched to the extracted requirement by token
containment (shared tokens over the smaller side, >= 0.5), best match first, each
item used once. Containment rather than Jaccard because a short label such as
"strong Go" lives inside a full extracted sentence, and Jaccard would call that a
miss.

The verdicts follow the same rubric the pipeline is judged by:

- **strong**: the CV states the requirement and a quote proves it.
- **partial**: the CV shows part of it, or an adjacent thing.
- **gap**: the CV says nothing about it.

## Refusal cases

Not every page is a job post. A LinkedIn Jobs menu page, a company profile, or
anything else pasted by mistake must be refused, not analysed. Such a case sets
`expect` to the error code it must produce instead of a verdict:

```yaml
id: page-hard-1
title: pasted page page-hard-1
expect: JD_NOT_FOUND
cv: |
  <the CV text, verbatim>
jd: |
  <the page, verbatim>
```

`expect` is `analysis` (the default) or one of `JD_NOT_FOUND` and
`JD_MULTIPLE_JOBS`. A refusal case needs no labels, so its gold file may be
`requirements: []`; an `analysis` case still refuses to load without labels.

A refusal is judged on the code, not on anything else: the expected code scores
a pass, any other outcome scores a miss, and a case expected to refuse that
instead produces an analysis is reported as an error rather than a low score.
Refusals have no requirements, so they are excluded from agreement, stability,
structuring and latency: an empty case would otherwise flatter or dilute them.

## What the report measures

| Metric               | Target | Meaning                                                         |
| -------------------- | ------ | --------------------------------------------------------------- |
| Agreement            | >= 75% | my verdict vs the pipeline's, per requirement                   |
| Stability            | >= 75% | requirements where all 3 runs voted the same way                |
| Structuring accuracy | >= 75% | my requirements that the extractor actually found               |
| Ungrounded quotes    | 0      | a strong/partial verdict whose quote is not in the CV           |
| Unsupported facts    | 0      | a number in a suggestion or cover note that is not in the CV    |
| Refusals correct     | all    | pages that must be refused and were refused with the right code |

Agreement is also compared with `baseline.json`: a drop of more than 2 points is
blocking. The first run has no baseline, and that is not a failure.

Stability reuses the votes the pipeline already stores rather than paying for a
second full pass; an unanimous vote across `match_runs` is the same evidence.

**That sentence only holds when `match_runs` is at least 2.** At one run every
requirement is trivially unanimous, so stability reads 1.0 no matter what the
model does. `.env` ships `MATCH_RUNS=1`, so a gate run must set it explicitly:

```
$env:MATCH_RUNS = "3"   # PowerShell; the gate is measured at three votes
python -m app.cli eval --dir eval
```

A report whose `match_runs` is 1 did not measure M2, and its stability figure
must not be quoted or used as a baseline.

## Commands

```
python -m app.cli eval --dir eval
python -m app.cli eval --dir eval --limit 3          # smoke the setup
python -m app.cli eval --dir eval --update-baseline  # accept this run
```

The run needs a working provider credential, because it calls the real model. It
writes to a throwaway `data/eval.db`; the real database is never opened.

## The shipped examples

`example-*` pairs use the synthetic CV from `backend/tests/fixtures/`. They exist
to show the format and to prove the harness works, not to prove quality: nobody
should read a score off three invented cases.
