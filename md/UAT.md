# UAT — Acceptance script

A manual acceptance pass for the CV–Job Fit Analyzer. Companion to
[`TUTORIAL.md`](./TUTORIAL.md): the tutorial says _how_, this document says
_what must be true_ and gives you a place to record it.

Run it on the machine that holds the real data, in a **copy** of the data
directory if you want to be safe:

```powershell
Copy-Item -Recurse data data-uat
$env:PYTHONPATH = "backend"
$env:DATABASE_URL = "sqlite:///./data-uat/app.db"
```

Every case below has a **Steps**, an **Expected** and blank **Actual / Pass-Fail**
cells. Fill them in as you go. If a case fails, stop and record it rather than
working around it — the point of this pass is to find out, not to get to the end.

**Never type real personal data into this document.** Where a value is needed,
the case tells you to use a placeholder such as `+62 000 0000 000` or
`someone@example.com`. The same rule applies to screenshots: redact the CV text
and the job text before attaching them.

---

## 0. Sign-off summary

| #   | Area                                                  | Verdict | Notes |
| --- | ----------------------------------------------------- | ------- | ----- |
| U1  | Prerequisites, health, key storage                    |         |       |
| U2  | CV upload validation                                  |         |       |
| U3  | CV redaction before any model call                    |         |       |
| U4  | Job text intake and paste validation                  |         |       |
| U5  | Requirement extraction with verbatim quotes           |         |       |
| U6  | Verdict rule: no quote ⇒ gap                          |         |       |
| U7  | Score computed in code                                |         |       |
| U8  | Suggestion fabrication guard                          |         |       |
| U9  | Suggestion Accept / Reject persistence                |         |       |
| U10 | Cover note: draft label and guard                     |         |       |
| U11 | Cover note regenerate keeps the old note on rejection |         |       |
| U12 | Provenance and mismatch warning                       |         |       |
| U13 | Cache behaviour                                       |         |       |
| U14 | Which host receives text                              |         |       |
| U15 | LinkedIn blocklist                                    |         |       |
| U16 | No raw HTML rendering                                 |         |       |
| U17 | Job state machine                                     |         |       |
| U18 | Purge gate (do not execute a real purge)              |         |       |
| U19 | Backup                                                |         |       |
| U20 | Markdown export                                       |         |       |
| U21 | CLI parity                                            |         |       |
| U22 | Accessibility: keyboard, focus, contrast, themes      |         |       |
| U23 | Alert intake and sync idempotence                     |         |       |
| U24 | No "apply / skip" language anywhere                   |         |       |

Tester: ............................ Date: ................
Build / commit: ............................ Model: ........................

---

## U1 — Prerequisites, health, key storage

**Steps**

1. `uv sync`, `npm --prefix frontend ci`, `npm --prefix frontend run build`,
   `uv run alembic upgrade head`.
2. Start the server: `uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8000`.
3. Open `http://127.0.0.1:8000` and look at **Home → System status**.
4. With no key stored, open **Settings → Model** and confirm the app tells you a
   key is missing rather than failing silently.
5. Store the key, save, then re-check the status.

**Expected**

- `uv run alembic upgrade head` succeeds and `uv run alembic current` prints
  `4f2c9d5a1b73 (head)`.
- `GET /api/health` returns `status: ok`, `database: ok`.
- Before the key: `llm` is `not_configured`. After saving: `llm` is `ok`.
- That flip happens without a reload: saving settings clears the cached probe and
  the page refetches health. `auth_failed` means the provider rejected the key;
  `unreachable` means it did not answer at all.
- After saving, the API-key field's placeholder says a key is stored and asks you
  to leave it empty to keep it.
- No file in the repository or in `data/` contains the key. Confirm with a text
  search for the first 8 characters of the key across `data/` and `.env`.
- Nothing binds anywhere but `127.0.0.1` (`Get-NetTCPConnection -LocalPort 8000`
  shows `127.0.0.1`, not `0.0.0.0`).

**Actual / Pass-Fail**

```text
U1:
```

---

## U2 — CV upload validation

**Steps** (for each sub-case, use the same **Add CV** form)

1. Upload a `.txt` renamed to `.pdf`.
2. Upload a real `.png` renamed to `.pdf`.
3. Upload a zero-byte file.
4. Upload a genuine PDF larger than 5 MB.
5. Upload the same good PDF twice.
6. Upload a good PDF with a label of 61 characters.

**Expected**

- (1) and (2) are rejected with `UPLOAD_INVALID`, reason `magic_bytes`. A file
  extension alone is never trusted.
- (3) is rejected with `UPLOAD_INVALID`, reason `empty`.
- (4) is rejected with `UPLOAD_TOO_LARGE` (HTTP 413) and the message names the
  limit.
- (5) is rejected with `CONFLICT` ("This file is already uploaded as an earlier
  version") and no second version is created.
- (6) is refused by the form (60 characters max) before any request is sent.
- In every case the job list, the CV list and the database are unchanged, and the
  error is shown to you in the UI rather than only in the server log.

**Actual / Pass-Fail**

```text
U2:
```

---

## U3 — CV redaction before any model call

**Steps**

1. Take a CV that contains a phone number, an email address, a street address and
   an ID number. Use placeholders if you are testing with a synthetic file.
2. Upload it and open **Open latest version**.
3. Read the **Redacted before sending** panel and the **Sent to LLM (redacted)**
   tab.
4. Add your own surname under **Settings → Privacy and data → Custom redaction
   terms**, save, upload the same CV as a new version, and re-check.

**Expected**

- The phone number, email address, street address and ID number each appear as a
  numbered token — `[PHONE_1]`, `[EMAIL_1]`, `[ADDRESS_1]`, `[ID_1]` — in the
  **Sent to LLM (redacted)** tab, and the panel lists each kind with a non-zero
  hit count.
- The **Sections** tab contains no personal identifier either.
- The text in that tab is exactly the text the pipeline uses — there is no
  second, unredacted copy in the request payload.
- After adding the custom term, it is masked too (as `[CUSTOM_1]`, `[CUSTOM_2]`, …),
  case-insensitively, and the hit count for it is non-zero.
- Nothing in the packet later reveals what was removed.

**Actual / Pass-Fail**

```text
U3:
```

---

## U4 — Job text intake and paste validation

**Steps**

1. **Jobs → New job** with a title only. Then with no title.
2. Open the job, press **Add JD**, and paste something under 200 characters.
3. Paste over 60,000 characters (repeat a paragraph until you pass the limit).
4. Paste ordinary prose that is not a job advertisement — a recipe or a news
   paragraph of at least 200 characters.
5. Paste two different job posts one after the other.
6. Paste one real, complete job page.
7. Check the Add JD dialog for any control that would fetch a URL.

**Expected**

- (1) without a title is refused by the form; with a title a job row appears.
- (2) is refused, `VALIDATION_ERROR` with `reason: too_short`, and the saving
  control stays disabled.
- (3) is refused, `VALIDATION_ERROR` with `reason: too_long`.
- (4) fails the extraction with `JD_NOT_FOUND`.
- (5) fails with `JD_MULTIPLE_JOBS`.
- (6) is stored and shown back on the job page with a character count. If the
  paste ends mid-sentence the **"This looks cut off."** note appears, and it
  never blocks you.
- (7) there is no fetch control of any kind. The dialog offers paste only.
- If the pasted text contains phrases addressed at an AI, the job page says the
  text is read as data and the pipeline does not act on it.

**Actual / Pass-Fail**

```text
U4:
```

---

## U5 — Requirement extraction with verbatim quotes

**Steps**

1. Run the analysis on a good paste (§6 of the tutorial).
2. Open **Matches** and take any row with a verdict of `strong` or `partial`.
3. Copy its **Evidence in your CV** quote and search the **Sent to LLM
   (redacted)** CV text for it.
4. Check the requirement text against **Job as read**.

**Expected**

- Each extracted requirement carries a quote that appears character for character
  in the stored job text.
- Each `strong` / `partial` verdict carries an evidence quote that appears
  character for character in the redacted CV text.
- Requirement count is between 5 and 40; a run that extracts fewer than 5 or more
  than 40 is treated as a failure, not as a small packet.
- Duplicate requirements are collapsed, not listed twice.

**Actual / Pass-Fail**

```text
U5:
```

---

## U6 — Verdict rule: no quote ⇒ gap

**Steps**

1. On the same packet, find a requirement you genuinely do not satisfy (a tool
   you have never used, a language you do not speak).
2. Read its row.
3. Inspect the stored rows directly if you want to be certain. Open
   `/docs`, call `GET /api/analyses/{id}`, and read `matches[].verdict` and
   `matches[].evidence_quote`. Or from a shell:

```powershell
$env:PYTHONPATH = "backend"
uv run python -c "import httpx; d = httpx.get('http://127.0.0.1:8000/api/analyses/<id>', timeout=10).json(); [print(m['verdict'], repr(m.get('evidence_quote'))) for m in d['matches']]"
```

**Expected**

- The unsatisfied requirement is `gap`, and its `evidence_quote` is null or an
  empty string.
- No `strong` or `partial` row exists anywhere with a null or empty
  `evidence_quote`. A row that claims a match without a quotable sentence is a
  defect, not a lenient result.
- No requirement has a free-form numeric score attached to it; the verdict is a
  category only.

**Actual / Pass-Fail**

```text
U6:
```

---

## U7 — Score computed in code

**Steps**

1. Read **Summary** and note the counts and the coverage percentage.
2. Count the `strong`, `partial` and `gap` rows in **Matches**.
3. `GET /api/analyses/<id>` and read `summary`.

**Expected**

- The counts in the summary equal the row counts you just made.
- The coverage number is reproducible from the categories by arithmetic — the
  same categories always produce the same number.
- The summary contains no free-form verdict prose: every sentence is a fixed
  phrase selected by a code path, and the fit label is one of a fixed set.
- The summary points back to requirement rows; nothing in it refers to a
  requirement that is not in **Matches**.
- There is no "apply", "skip", "go for it" or "don't bother" recommendation
  anywhere in the packet.

**Actual / Pass-Fail**

```text
U7:
```

---

## U8 — Suggestion fabrication guard

**Steps**

1. Open **Suggestions**.
2. Read every visible card's **In your CV now** and **Proposed wording**.
3. Press **Show N rejected by the guard** if the control is present.
4. For each accepted suggestion, check every concrete token in the proposed
   wording (number, percentage, tool name, employer, date) against the CV text.

**Expected**

- Every visible suggestion only rewords, reorders or emphasises text that already
  exists in the CV. No new number, tool, employer, certification or date.
- Every hidden suggestion is hidden for a stated reason, and that reason fits
  the "introduced something the CV does not contain" family.
- No suggestion contains empty claims such as "results-driven", significance
  inflation, or a generic closer.
- The count in **Show N rejected by the guard** matches the number of hidden
  cards.
- A gap in the CV is reported as a gap. Nothing in this screen tries to paper
  over a missing skill.

**Actual / Pass-Fail**

```text
U8:
```

---

## U9 — Suggestion Accept / Reject persistence

**Steps**

1. Accept one suggestion and reject another.
2. Reload the page.
3. Close the browser, reopen the packet.
4. `GET /api/analyses/<id>` and read the suggestion rows.
5. Reject everything, then re-run the same analysis (it should hit the cache).

**Expected**

- After a reload, the accepted card still reads as accepted and the rejected card
  as rejected. The decision is stored, not held in memory.
- The API shows a `decision` field per suggestion matching what you clicked.
- Accepting does not modify the CV file, the CV version or the CV text: the CV
  and its version count are unchanged.
- A cached re-run does not silently reset your decisions.

**Actual / Pass-Fail**

```text
U9:
```

---

## U10 — Cover note: draft label and guard

**Steps**

1. Open **Cover note**.
2. Read the whole note and look for the draft label.
3. Compare its claims to the `strong` rows only.
4. Check word count.
5. Look for **Copy**.

**Expected**

- The note is presented as a draft, in words, on screen — not only in
  documentation.
- Every requirement it asserts is `strong` in **Matches**. A claim resting on a
  `partial` or `gap` row is a defect.
- Word count sits between the configured minimum and maximum (60–150 by default).
- It contains no fabricated specifics, no significance inflation and no generic
  closer.
- **Copy** puts the note text on the clipboard and confirms the copy happened.

**Actual / Pass-Fail**

```text
U10:
```

---

## U11 — Cover note regenerate keeps the old note on rejection

**Steps**

1. Note the current cover note text.
2. Press **Try again** and wait.
3. If it succeeds, note the new text; if it fails, read the displayed reason.

**Expected**

- On success, the note is replaced and remains guard-passing and still a draft.
- On failure, the previous note is still there, unchanged, and the reason is
  shown. It is never replaced by unguarded text and never silently emptied.
- The attempt is recorded — the packet's provenance does not silently mutate.
- The button shows a busy state while the request is in flight and cannot be
  double-fired.

**Actual / Pass-Fail**

```text
U11:
```

---

## U12 — Provenance and mismatch warning

**Steps**

1. Note the provenance block on the packet: model, prompt bundle, runs,
   timestamp.
2. Change the model string in **Settings → Model** to something visibly different
   (you do not need a working key for the label to change on the next run).
3. Run a fresh analysis of the same job with a different CV version.
4. Compare the two entries in **History**.

**Expected**

- Each stored analysis records `cv_version`, `jd_id`, `prompt_version`, `model`
  and a timestamp, all visible without opening the database.
- When model or prompt bundle differ, the UI says so instead of presenting a
  delta as if the two were comparable.
- When they match and only the CV version changed, the comparison is presented
  without a warning.

**Actual / Pass-Fail**

```text
U12:
```

---

## U13 — Cache behaviour

**Steps**

1. Run an analysis of job A with CV version V. Note the time it took.
2. Run the same job with the same CV version again.
3. Change one things at a time and re-run: the CV version, then the runs-per-
   requirement setting.
4. For the cached case, check the POST response body.

**Expected**

- (2) returns immediately, the POST response carries `cache_hit: true`, and the
  packet is the same analysis id.
- (3) each change produces a new analysis id — a different CV version and a
  different run count are different keys.
- No model call is issued for the cached case. If you can see the model provider's
  usage dashboard, its counter does not move.
- Re-running does not duplicate rows in the packet.

**Actual / Pass-Fail**

```text
U13:
```

---

## U14 — Which host receives text

**Steps**

1. Open **Settings → Privacy and data**.
2. Read the sentence that names where text goes.
3. Change the Base URL host and read it again.
4. With the app running and a job analysed, watch outbound traffic if you can
   (`Get-NetTCPConnection -State Established` while a run is in flight).

**Expected**

- The screen names the host of the configured Base URL in one sentence, and the
  name changes when the Base URL changes.
- The only outbound destination during a run is that host.
- No request goes to LinkedIn, to any social network, or to a telemetry endpoint.
- Gmail traffic only happens inside the helper process, only during a sync.

**Actual / Pass-Fail**

```text
U14:
```

---

## U15 — LinkedIn blocklist

**Steps**

1. From a shell, with the server running:

```powershell
$env:PYTHONPATH = "backend"
uv run python -c "from app.shared.http import assert_host_allowed; assert_host_allowed('https://www.linkedin.com/jobs/view/1', blocked_hosts=['linkedin.com'])"
```

2. Try a job URL variant (`id.linkedin.com`, `linkedin.com`, `lnkd.in`).
3. Inspect the blocklist configuration.

**Expected**

- Each attempt raises `FETCH_HOST_BLOCKED` (HTTP 400) before any connection is
  made.
- The blocklist is host-based and config-driven, and it includes `linkedin.com`.
- There is exactly one HTTP path for user-supplied URLs; no module builds its own
  client or calls `httpx` directly.
- No code path in the API turns a stored job URL into a fetch.

**Actual / Pass-Fail**

```text
U15:
```

---

## U16 — No raw HTML rendering

**Steps**

1. Paste a job page that contains HTML tags and a `<script>` tag.
2. View the packet and the job page.
3. Search the frontend source.

```powershell
Get-ChildItem frontend\src -Recurse -Include *.ts,*.tsx |
  Where-Object { $_.FullName -notmatch '\\test\\' -and $_.Name -notlike '*.test.ts*' } |
  Select-String -Pattern 'dangerouslySetInnerHTML|innerHTML'
```

**Expected**

- No matches from the search — the command prints nothing. The only occurrence in
  the repository is inside `frontend/src/test/no-html-injection.test.ts`, the
  guard test that enforces this rule.
- Tags from the pasted text appear as literal text on screen, or are stripped. A
  script tag never executes and never alters the page.
- LLM output (suggestions, cover note) is rendered as text only.

**Actual / Pass-Fail**

```text
U16:
```

---

## U17 — Job state machine

**Steps**

1. Press **Shortlist** on a `new` job. Press **Dismiss** on another.
2. Try to move an `applied` job anywhere, via the API:

```powershell
$env:PYTHONPATH = "backend"
uv run python -c "import httpx; print(httpx.patch('http://127.0.0.1:8000/api/jobs/<id>', json={'status':'new'}, timeout=10).text)"
```

3. Try an unknown status string.

**Expected**

- `shortlisted` and `dismissed` are accepted from `new` and are reflected after a
  reload.
- Only the documented transitions are accepted; the rest return
  `VALIDATION_ERROR` and change nothing.
- An unknown status is rejected, not coerced.
- Nothing in the UI moves a job to `analyzed` or `applied` on its own initiative —
  `analyzed` is set by the pipeline, and `applied` is only ever set by you.

**Actual / Pass-Fail**

```text
U17:
```

---

## U18 — Purge gate

> **Do not execute a real purge during this test.** Verify the gate and stop. If
> you must see the full flow, do it against `data-uat/` and take a backup first.

**Steps**

1. Open **Settings → Privacy and data → Delete all data**.
2. Type something wrong (`delete`, `DELET`, an empty string) and try to confirm.
3. Read the dialog's row counts and its statement about settings.
4. Press cancel or close the dialog.

**Expected**

- The confirm control is disabled until the exact word `DELETE` is typed; the
  lowercase form is not accepted.
- The dialog names every table it would empty and the row count for each, and
  those counts match `GET /api/data`.
- It states explicitly what survives, and settings do survive.
- Cancel closes without a request. No data was deleted.
- The e2e suite's purge test is stubbed. Nothing in this build sends a real
  purge on its own.

**Actual / Pass-Fail**

```text
U18:
```

---

## U19 — Backup

**Steps**

1. Press **Back up database**.
2. List the target directory.

**Expected**

- A new file appears with a timestamp in its name, non-zero size.
- The file is a readable SQLite database (`sqlite3 <file> ".tables"` lists the
  expected tables) and contains the same row counts as `GET /api/data`.
- The backup does not overwrite the previous one.

**Actual / Pass-Fail**

```text
U19:
```

---

## U20 — Markdown export

**Steps**

1. Request `GET /api/analyses/<id>/export.md` (open it in the browser or use
   `curl`).
2. Compare its sections with the packet screen.

**Expected**

- Sections appear in the fixed order: **Fit summary**, **Must-have
  requirements**, then verdict groups (**Matches (verified)**, **Partial**,
  **Gaps**), then **CV suggestions**, then **Cover note (draft)**.
- The draft note survives into the export as an explicit draft statement.
- No banned phrasing ("results-driven", significance inflation, generic closers).
- No "apply / skip" wording.
- Content matches the packet: same verdicts, same accepted/rejected decisions.

**Actual / Pass-Fail**

```text
U20:
```

---

## U21 — CLI parity

**Steps**

```powershell
$env:PYTHONPATH = "backend"
uv run python -m app.cli health
uv run python -m app.cli cv show
uv run python -m app.cli task list --limit 5
uv run python -m app.cli packet --analysis-id <id> --summary
uv run python -m app.cli packet --analysis-id <id> --suggestions
uv run python -m app.cli packet --analysis-id <id> --md packet.md
uv run python -m app.cli job paste <job_id> --file - --source-kind page_paste
```

**Expected**

- Every command prints JSON (or the markdown file) and exits 0; none needs a
  running server except the ones that read the shared database.
- `--file -` reads stdin, so a pasted page can be piped straight in.
- The CLI packet content matches what the UI shows for the same analysis id.
- `analyze` drains the queue in-process and reports `cache_hit: true` on the
  second identical call.

**Actual / Pass-Fail**

```text
U21:
```

---

## U22 — Accessibility: keyboard, focus, contrast, themes

**Steps**

1. Put the mouse away. Walk the whole flow — Home, Jobs, Job page, Add JD, Run
   analysis, Packet, Settings — using Tab, Shift+Tab, Enter, Space, Escape and
   the arrow keys.
2. Tab through a dialog and confirm focus stays inside it; press Escape.
3. Switch to the dark theme:

```javascript
localStorage.setItem("cv-fit.theme", "dark");
location.reload();
```

4. Re-walk the packet in dark mode.
5. Zoom to 200%.

**Expected**

- Every control is reachable and operable by keyboard alone. No control is a
  bare `div` with a click handler.
- Focus is always visible, and it is visibly distinct from hover.
- Opening a dialog moves focus into it; closing returns focus to the control that
  opened it. Escape closes it.
- Escape and Tab never strand focus behind a modal.
- Text and controls pass contrast in both themes; verdict colours remain
  distinguishable in dark mode and are never the only signal — each verdict is
  also a word.
- Nothing is clipped, overlapped or unreadable at 200% zoom; no horizontal
  scrolling on the packet at 1280 px wide.
- Status messages are announced (`role="status"`) and errors are announced
  (`role="alert"`), not only coloured.

**Actual / Pass-Fail**

```text
U22:
```

---

## U23 — Alert intake and sync idempotence

**Steps**

1. Connect Gmail (`uv run python -m app.mcp_gmail auth`), then **Settings → Gmail
   → Check connection**.
2. Press **Sync alerts** on **Jobs**, note the result line.
3. Press it again immediately.
4. Disconnect and try to sync.

**Expected**

- The result line reports emails read, new jobs, duplicates and alerts that
  could not be read. Skipped alerts are counted, never guessed at.
- The second identical sync adds no rows — duplicates are recognised.
- An unparseable alert layout does not abort the whole sync.
- After **Disconnect**, syncing fails with `GMAIL_NOT_CONNECTED` and the message
  gives the command to reconnect.
- The consent screen asked for `gmail.readonly` only. Nothing in the app sends,
  labels, archives or deletes mail.
- No Gmail token is written to the repository, to `.env` or to a log line.

**Actual / Pass-Fail**

```text
U23:
```

---

## U24 — No "apply / skip" language anywhere

**Steps**

1. Search the UI source and the prompts:

```powershell
Get-ChildItem frontend\src,prompts -Recurse -Include *.ts,*.tsx,*.md,*.txt | Select-String -Pattern 'apply now|you should apply|skip this|worth applying'
```

2. Walk the packet and read every label once more.

**Expected**

- No matches, and no label that recommends applying or skipping.
- The only place "apply" appears is as a neutral past-tense status you set
  yourself ("Applied").
- The packet always leaves the decision with you, and the summary reports facts.

**Actual / Pass-Fail**

```text
U24:
```

---

## Regression checks before signing off

Run these and paste the tail of each output into your record:

```powershell
uv run pytest -q
uv run ruff check backend
npm --prefix frontend run build
npm --prefix frontend run test
npm --prefix frontend run e2e
```

Expected at the time of writing: `456 passed`, `All checks passed!`, a clean
`vite build`, `71 passed`, `17 passed`.

```text
pytest:
ruff:
build:
vitest:
e2e:
```

---

## Known limitations to acknowledge, not to fix during UAT

These are recorded in the implementation plan and are not UAT failures:

1. **The eval gate is 75 / 75 / 75, not the original 80.** Agreed deliberately.
2. **`structuring_accuracy` is measured as precision 78.46 % with recall 98.08 %.**
   Read the two numbers separately; the label in the report is imprecise.
3. **Unanimity across runs (D19) is strict.** A requirement can be flagged
   unstable when a lenient majority would have decided it.
4. **`MATCH_RUNS = 1` in the local `.env`** for cost. Majority voting only means
   something at 3, which is the code default.
5. **Three known-lenient verdicts** in the eval set (jd-02 and jd-03 gap →
   partial, jd-01 partial → strong). They are recorded, not hidden.
6. **Only three of the five analysed pairs are real job pages.** The other two are
   synthetic, so real-page extraction is less proven than the score suggests.
7. **The strong-verdict path is tested but has not been exercised live** against a
   real posting end to end in this environment.
8. **No live purge has ever been executed.** The gate is tested; the destructive
   path itself is not.
9. **The Packet screen has only been rendered live against a gap-only packet.**
   It was loaded in a browser from the stored analysis and showed all five
   sections, the empty "What matches (0)" state, both suggestions with
   Accept/Reject, the "No draft could be verified for this job." cover-note state
   and the Markdown export link. What has never been seen live is a strong-match
   packet carrying a real cover-note draft, and a successful "Try again".
   U5–U12 in this document cover those paths.
10. **The workspace is not a git repository,** so "one concern per commit" was not
    honoured.
11. **An API key was visible in plaintext during development and should be
    rotated.** Rotate it before treating this build as final.

---

## Sign-off

|                                                             |     |
| ----------------------------------------------------------- | --- |
| All cases U1–U24 pass                                       | ☐   |
| Failures recorded above with reproduction steps             | ☐   |
| No real personal data in this document or in any attachment | ☐   |
| Regression commands run, output pasted                      | ☐   |
| Known limitations read and accepted                         | ☐   |
| API key rotated                                             | ☐   |

Tester: ............................ Date: ................
