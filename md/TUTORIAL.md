# TUTORIAL — Using the CV–Job Fit Analyzer

One user, one machine, one SQLite file. This document takes you from a fresh
clone to a finished application packet, then shows how to get your data back out
and how to run the tests.

Everything here was executed against this repository before it was written down.
Where a command needs a Windows shell detail, it is stated rather than implied.

---

## 0. What this tool does, and the three things it will not do

It reads a job post you paste and your CV, then produces an application packet:

1. a **fit summary** with the strongest matches and the biggest gaps,
2. each **job requirement** marked `strong`, `partial` or `gap`, with the
   sentence from your CV that proves it,
3. **CV suggestions** that reword or reorder what you already wrote,
4. a short **cover note draft**.

Three refusals are built into the code, not into a setting:

- **It never touches LinkedIn.** No scraping, no browser automation, no
  extension, no headless Chrome. Job text arrives one way: you select the text
  on the page, copy it, and paste it in. The single HTTP client in the backend
  refuses `linkedin.com` by hostname from a blocklist.
- **It never applies for you.** No autofill, no submit, no screening answers.
  There is no "apply" or "skip" button anywhere, and no recommendation of that
  kind is ever generated.
- **It never invents experience.** A suggestion may reword, reorder or
  emphasise a line that is already in your CV. It may not add a tool, a metric,
  a date or a job you did not have. A genuine gap is reported as a gap. The
  cover note may only assert requirements whose verdict is `strong`, and every
  note is labelled a draft.

---

## 1. What you need first

| Requirement                                   | Why                                                                     |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| Python 3.13 (the project pins `>=3.13,<3.14`) | Backend runtime                                                         |
| [uv](https://docs.astral.sh/uv/)              | Installs Python deps and runs the commands below                        |
| Node.js LTS + npm                             | Builds the React UI once                                                |
| An OpenAI-compatible LLM endpoint and a key   | The only thing this app sends text to                                   |
| A CV as PDF or DOCX                           | 5 MB upload cap                                                         |
| Gmail account with LinkedIn job-alert emails  | Optional. Only if you want the alert inbox instead of pasting every job |

No Docker. No Redis. No cloud account for this app itself.

---

## 2. Install (one time)

From the repository root:

```powershell
uv sync
npm --prefix frontend ci
npm --prefix frontend run build
```

- `uv sync` creates `.venv` and installs the pinned backend dependencies.
- `npm --prefix frontend ci` installs the UI dependencies from `package-lock.json`.
- `npm --prefix frontend run build` type-checks with `tsc --noEmit` and writes
  `frontend/dist`. The backend serves that folder, so after this step the UI and
  the API come from one process.

Create the database tables:

```powershell
$env:PYTHONPATH = "backend"
uv run alembic upgrade head
```

`$env:PYTHONPATH = "backend"` matters. The Python package is `backend/app`, so
`app` is not importable from the repository root without it. Set it once per
shell session; every command in this tutorial assumes it. `uvicorn` has its own
switch (`--app-dir backend`) and does not need the variable; `pytest` does not
need it because `pyproject.toml` already lists `pythonpath = ["backend"]`.

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

`.env` is listed in `.gitignore`. It holds defaults, not secrets — the API key
never goes in there (see §3).

---

## 3. Configure: the key, the model, the redaction terms

Start the app:

```powershell
uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Two other entry points exist while developing:
<http://127.0.0.1:8000/docs> for the Swagger page and
`npm --prefix frontend run dev` on <http://127.0.0.1:5173> for hot reload.

Check the health line first: **Home → System status**, **Settings → Gmail**, or
`GET /api/health`. It reports four fields. On a fresh install it looks like this:

```json
{
  "status": "ok",
  "database": "ok",
  "gmail": "not_connected",
  "llm": "not_configured"
}
```

`llm: not_configured` is expected until you store a key. Nothing else works
before that, and the app says so instead of failing somewhere deeper. Once a key
is stored the value is a probe, not a guess:

| `llm`            | What it means                                          |
| ---------------- | ------------------------------------------------------ |
| `ok`             | The provider answered with the stored key              |
| `not_configured` | No key in the keychain                                 |
| `auth_failed`    | A key is stored but the provider rejected it           |
| `unreachable`    | A key is stored but the provider did not answer        |
| `unknown`        | The probe itself failed; retry with `?refresh=true`    |

The probe asks the provider's cheapest endpoint (`GET /models`), never a
completion, so it costs no tokens and is cached for five minutes. Saving
settings clears that cache, so a new key shows up immediately.

### 3.1 Store the API key

**Settings → Model**:

- **Base URL** — the OpenAI-compatible root, for example
  `https://api.deepseek.com`.
- **Model** — the model string, for example `deepseek-v4-flash`. It is stored on
  every analysis so two results are only ever compared when their model string
  matches.
- **API key** — paste it, press **Save**.

The key goes to the OS keychain through `keyring`, under service `cv-fit`. It is
not written to the database, not written to `.env`, and never appears in a log
line. After saving, the field's placeholder becomes "A key is stored; leave
empty to keep it", and the health report switches to `llm: ok`.

If the keychain is locked you get `SECRET_STORE_UNAVAILABLE` rather than a
silent fallback to plaintext.

### 3.2 Decide what the model may see

**Settings → Privacy and data** states, in one sentence, which host receives
text: the host in the Base URL above. Under it:

- **Custom redaction terms** — your full name, your current employer, anything
  else you would rather the model never reads. Matching is literal and
  case-insensitive.

Every hit is replaced by a numbered token, not blanked out: `[EMAIL_1]`,
`[PHONE_1]`, `[URL_1]`, `[ID_1]`, `[ADDRESS_1]` for the rules that always run, and
`[CUSTOM_1]` for your own terms. The numbering restarts per kind, and the Parser
View's **Redacted before sending** panel gives the friendly name and a count for
each kind.

- **Your data** — row counts, the export button, the backup button and the purge
  button. Covered in §10 and §11.

### 3.3 Optional: the pre-filter

**Settings → Criteria** holds keywords, locations and seniority used to mark
alert emails as irrelevant before they reach your job list. A filtered job is
kept and labelled, not deleted. Empty lists mean nothing is filtered.

### 3.4 Optional: non-negotiables

**Settings → Criteria** also takes your non-negotiables: languages, locations,
work modes, a salary floor and a work-authorisation note. These turn into
**constraint flags** in the packet summary. Each flag is one of four statuses —
`ok`, `conflict`, `review`, `not_stated` — read from the job text and the CV. A
conflict is reported and never changes a verdict or hides a row, and the app does
not decide whether a `review` flag is acceptable.

---

## 4. Add your CV

**CVs** in the top navigation.

1. **Label** — a short name you will recognise, for example `Backend CV`
   (required, 60 characters max).
2. **Target role (optional)** — for example `Backend engineer`.
3. Drop a PDF or DOCX on the dropzone, or click it to pick a file. The file is
   optional here; you can add it after creating the CV.
4. Press **Add CV**.

What happens on upload, in order: the extension and the magic bytes are checked;
the file is capped at 5 MB; a file whose contents you already uploaded is
rejected as a duplicate rather than silently becoming version 2; text is
extracted in a short-lived subprocess with a timeout, so a malformed PDF cannot
hang the server; PII is redacted; the result is stored.

You then have a version to look at:

- **Open latest version** (`/cv-versions/<id>`) is the Parser View. It shows any
  parser warnings, the file's SHA-256 and section count, and how many characters
  will actually be sent. **Redacted before sending** lists each redaction kind
  with a hit count. The text has two tabs: **Sent to LLM (redacted)**, which is
  byte-for-byte what a model receives, and **Sections**, which is how the parser
  split the document.

  Read this once before your first analysis. If a name or an address survives,
  add it as a custom redaction term in §3.2 and check again.

To replace the file, use the row's **Add a version** dropzone. Each upload is a
new version; analyses record the version they used, so editing your CV never
rewrites an old result.

---

## 5. Get a job into the inbox

**Jobs** in the top navigation. The page says it plainly: open the post, expand
the description, select all, copy — then use **Add JD**. Nothing is fetched from
the site for you.

### 5.1 The paste route (works for any site, always)

1. **New job** — title is required; company, location and URL are optional. The
   URL is stored for your reference only. It is never fetched.
2. Open the job, select the whole page, copy it.
3. On the job page, press **Add JD** and paste into **Paste the whole job page**.

Paste the whole page, noise included. Navigation, cookie banners and "similar
jobs" sidebars are expected; the structuring step drops what it cannot quote.
The box refuses fewer than 200 characters (that is a link, not a post) and more
than 60,000 (that is more than one job).

The stored text is shown back to you on the job page with its character count.
Two annotations may appear, both advisory and never blocking:

- **"This looks cut off."** — the paste ends mid-sentence or lacks a section a
  post usually has. Usually a collapsed "show more".
- **A note that the text contains instructions** — job posts sometimes contain
  text addressed at an AI. It is treated as data. It is never followed.

### 5.2 The alert route (optional)

**Settings → Gmail** shows the state. Consent happens in the helper process, so
this app never holds an OAuth code:

```powershell
$env:PYTHONPATH = "backend"
uv run python -m app.mcp_gmail auth
```

That opens Google's consent screen for the scope `gmail.readonly`. The refresh
token is written to the OS keychain. Then **Settings → Gmail → Check
connection** should say _connected_. **Disconnect** deletes the local token only.

On **Jobs**, **Sync alerts** reads your alert emails and turns them into rows.
The result line reads like `12 emails read · 4 new jobs · 8 duplicates · 0
alerts could not be read`. An alert layout that cannot be parsed is counted and
skipped, never guessed at. Running it twice is safe: the second run adds nothing.

The helper exposes exactly two read-only tools. Nothing is sent, labelled,
archived or deleted.

---

## 6. Run the analysis

On the job page, with stored text present:

1. Press **Run analysis**.
2. Pick the CV version. If you only have one, it is preselected.
3. Press **Run**.

Two outcomes, and the difference matters:

- **A cached result exists** — you land on the packet immediately. The key is
  `hash(cv_version, jd_id, prompt_version, model, runs, cover-note params)`, so
  an identical run costs nothing and the POST response carries `cache_hit: true`.
  The flag is in the API response and in the CLI output; the packet screen does
  not display it.
- **No cached result** — you are taken to `/tasks/<id>`, which polls every second
  or two and shows the current step. Steps run in a fixed order in code: preflight,
  structure and extract, match, ground, vote, suggest, fabrication guard, cover
  note, cover-note guard, persist. You can cancel between steps; a finished step
  is never half-written.

A first run on a fresh job takes tens of seconds and is the only step that spends
tokens. If you set a monthly token budget in **Settings → Model**, a spent budget
raises `BUDGET_EXCEEDED` and stops new work until you raise it or run with the
explicit override.

---

## 7. Read the packet

Five sections, reachable from the sticky nav: **Summary**, **Matches**,
**Suggestions**, **Cover note**, **Job as read**.

### Summary

The fit label and the counts are computed in code from the verified matches. The
model is never asked to write verdict prose. You get the number of strong,
partial and gap requirements, up to three strongest must-have matches, up to
three biggest must-have gaps and partials, and any constraint flag whose status
is `conflict` or `review`.

### Matches

One row per requirement, each with:

- the verdict — `strong`, `partial` or `gap`;
- the requirement text and its importance (`knockout` rows sort first among gaps);
- the vote tally, for example `3/3`;
- **Evidence in your CV** — a verbatim quote from the stored version of your CV.

The rule that makes this usable: no quote means the verdict is `gap`. A
`strong` or `partial` row without a quotable sentence cannot be produced.

### Suggestions

Each card shows **In your CV now** and **Proposed wording**, side by side. Some
cards are hidden behind **Show N rejected by the guard**; those failed the
fabrication check because they introduced a fact, a number, a tool or a date that
is not in your CV.

**Accept** or **Reject** each one. The decision is stored with the analysis, so
the packet is a record of what you actually decided, not a fresh opinion on every
visit. Accepting a suggestion records your judgement — it does not edit your CV
file.

### Cover note

A draft of `COVER_NOTE_MIN_WORDS`–`COVER_NOTE_MAX_WORDS` words (60–150 by
default). It is labelled a draft on purpose, it may only assert requirements
whose verdict is `strong`, and it passed the cover-note guard before being
stored.

- Edit it in place and save. Your edit is kept with the analysis.
- **Try again** regenerates it. If regeneration fails the guard, the old note
  stays and the reason is shown; it is not replaced with something unguarded.
- Paste it into the real application yourself.

### Job as read

The stored text with its character count, so you can always check what the model
was working from.

Every packet also shows its provenance: model string, prompt bundle version,
runs per requirement and the timestamp. Two packets are only comparable when the
model and the bundle match; the UI says so rather than letting you compare apples
and oranges.

---

## 8. Move the job through your own process

On a job page you get two buttons: **Shortlist** and **Dismiss**. The states are
`new`, `shortlisted`, `analyzed`, `applied`, `dismissed`, and the API accepts
only the transitions in the table below. The other rows of this table are
available through `PATCH /api/jobs/{id}`; the UI exposes just the two above.

| From          | To                                     |
| ------------- | -------------------------------------- |
| `new`         | `shortlisted`, `dismissed`, `analyzed` |
| `shortlisted` | `analyzed`, `dismissed`                |
| `analyzed`    | `applied`                              |
| `dismissed`   | `new`                                  |
| `applied`     | —                                      |

The app never moves a job to `applied` for you. That transition is yours, and it
is the only place the tool admits you applied.

---

## 9. Come back later

- **History** on a job page lists every analysis of that job with its fit label,
  model and date, so you can see whether a CV revision moved the needle.

The API also has `GET /api/cvs/{cv_id}/impact`, which aggregates what your
analysed jobs asked for across CV versions. It is not surfaced in the UI yet;
call it from `/docs` or with `curl` if you want the numbers.

Comparisons between CV versions are only meaningful when the model string and
prompt bundle match. The UI flags a mismatch instead of presenting a delta.

---

## 10. Get the packet out

Three exits:

1. **Export JSON** (**Settings → Privacy and data**) — every row you own, as one
   JSON file. This is your data, so treat the file like the CV itself.
2. **Markdown** — `GET /api/analyses/<id>/export.md`, or from the CLI:
   `uv run python -m app.cli packet --analysis-id <id> --md packet.md`. Fixed
   section order, no banned phrasing.
3. **Copy** from the packet screen — the cover note has its own copy control.

---

## 11. Backup and purge

- **Back up database** writes a timestamped copy of `data/app.db` into the
  directory named under the button (`data/backups`). It is a file copy you can
  move anywhere.
- **Delete all data** asks you to type `DELETE` before it runs, then names every
  table it will empty and how many rows are in each. Uploaded files go too.
  Settings survive a purge, and the dialog says so instead of claiming otherwise.
  This cannot be undone, so take the backup or the export first.

There is no live "purge" button hidden anywhere else, and no schedule. Deleting
is always an explicit act with a typed confirmation.

---

## 12. Doing it without a browser

The CLI is the Stage A interface. Every command prints JSON, so it pipes.

```powershell
$env:PYTHONPATH = "backend"

uv run python -m app.cli health
uv run python -m app.cli cv add --label "Backend CV" --file .\cv.pdf --target-role "Backend engineer"
uv run python -m app.cli cv show
uv run python -m app.cli cv preview <cv_version_id>
uv run python -m app.cli job add --title "Backend Engineer" --company "Example" --location "Remote"
uv run python -m app.cli job paste <job_id> --file .\jd.txt --source-kind page_paste
uv run python -m app.cli job structure <snapshot_id>
uv run python -m app.cli analyze --cv-version <cv_version_id> --snapshot <snapshot_id>
uv run python -m app.cli packet --analysis-id <analysis_id> --summary
uv run python -m app.cli packet --analysis-id <analysis_id> --suggestions
uv run python -m app.cli packet --analysis-id <analysis_id> --md packet.md
uv run python -m app.cli task list --limit 10
uv run python -m app.cli task watch <task_id> --interval 2
uv run python -m app.cli job sync-alerts --limit 25
uv run python -m app.cli eval --dir eval
```

`job paste --file -` reads the text from stdin, which is handy when you have just
copied a page. `--source-kind` records how the text arrived; it never triggers a
fetch.

`analyze` drains the queue inside its own process, so no server needs to be
running. A second identical call reports `cache_hit: true` and issues no model
call.

---

## 13. Running the tests

Backend:

```powershell
uv run pytest -q
uv run ruff check backend
```

Expected at the time of writing: `456 passed`, and `All checks passed!`.

Frontend, from the repository root:

```powershell
npm --prefix frontend run build     # tsc --noEmit && vite build
npm --prefix frontend run test      # 71 tests
npm --prefix frontend run e2e       # 17 Playwright tests + axe checks
```

The end-to-end suite starts its own server and stubs the API, so it does not
need your key, your CV or your Gmail.

Contract checks, needed only if you changed a request or response model:

```powershell
uv run python -m app.cli openapi --out frontend/openapi.json
npm --prefix frontend run gen:api
uv run python -m app.cli export-schemas
```

The eval set lives in `eval/`. Any prompt or model change is supposed to be run
against it before merging:

```powershell
uv run python -m app.cli eval --dir eval
```

The report and baseline comparison are printed as JSON, and a delta beyond the
threshold exits non-zero.

---

## 14. When something goes wrong

Errors come back as `{"error": {"code": ..., "message": ..., "details": ...}}`
and the UI shows the message, not the code alone.

| Code                                     | What it means                                        | What to do                                     |
| ---------------------------------------- | ---------------------------------------------------- | ---------------------------------------------- |
| `llm: not_configured` in health          | No API key in the keychain                           | Settings → Model → API key → Save              |
| `llm: auth_failed` in health             | The provider rejected the stored key                 | Paste a new key and Save                       |
| `llm: unreachable` in health             | Right key, but the provider did not answer           | Check the network, the Base URL, then retry    |
| `SECRET_STORE_UNAVAILABLE`               | The OS keychain is locked                            | Unlock the keychain, then retry                |
| `GMAIL_NOT_CONNECTED`                    | No Gmail token, or it was deleted                    | Run the `app.mcp_gmail auth` command from §5.2 |
| `VALIDATION_ERROR` / `reason: too_short` | Paste is under 200 characters                        | Expand the post first, copy again              |
| `VALIDATION_ERROR` / `reason: too_long`  | Paste is over 60,000 characters                      | Paste one job, not a search results page       |
| `UPLOAD_INVALID`                         | Not a PDF/DOCX by magic bytes, or the file is empty  | Re-export the file and retry                   |
| `UPLOAD_TOO_LARGE`                       | The file is over the 5 MB cap                        | Compress or trim the CV, then retry            |
| `JD_NOT_FOUND`                           | The text is not a job post                           | Paste the actual posting                       |
| `JD_MULTIPLE_JOBS`                       | Several postings in one paste                        | Paste one job at a time                        |
| `BUDGET_EXCEEDED`                        | Monthly token cap reached                            | Raise it in Settings, or override deliberately |
| `FETCH_HOST_BLOCKED`                     | The URL host is on the blocklist (LinkedIn included) | Paste the text instead                         |
| `NOT_FOUND`                              | The row was purged or never existed                  | Re-create it                                   |

Two habits that prevent most confusion:

- Read the **Parser view** of your CV before the first analysis. If something
  private is visible, add it as a redaction term.
- Run **health** after changing a key, a base URL or a model. It is the cheapest
  check and it names the broken part.

---

## 15. What I deliberately did not build

Recorded here so nobody goes looking for it:

- **No LinkedIn access of any kind.** No scraper, no extension, no headless
  browser, no URL fetch for a job post in the Add JD dialog.
- **No auto-apply, autofill or screening answers.** The tool stops at advice.
- **No "apply" or "skip" recommendation.** Not in the UI, not in the prompt, not
  in the packet.
- **No multi-user auth, no cloud deployment, no Docker.** It binds to
  `127.0.0.1` and stays there.
- **No Word export, no benchmarks, no CV-version comparison view.** The last two
  were Could items and are still deferred.
- **No Redis, Celery, message broker, SSE or extra cache layer.** Progress is a
  poll, the worker runs in the same process, and the cache is the database.
