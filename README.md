# Regulatory Brief

A compact, English-only regulatory intelligence interview PoC. Inspired by the adjacent healthcare-directory-demo: Python standard library, SQLite and a single HTML/CSS/JavaScript page. No pip packages, frontend build or Node service is required.

## Start

```sh
cd /Users/bailefei/luff/projects/aitools/regulatory-intelligence-demo
python3 app.py --port 8767
```

Open http://127.0.0.1:8767. Stop with Ctrl+C. Python 3.9+ is sufficient. The first launch creates `brief.sqlite3`; restarts preserve snapshots and reviews.

## Five-minute demonstration

1. **Live sources**: click **Collect live sources** to capture three fixed European Commission HTML pages. Each displays its actual check outcome and timestamp. This first capture is a **Baseline**, not a newly introduced regulation.
2. Open **Inspect & analyze**. Inspect captured text, source URL, SHA-256 and version comparison.
3. Click **Generate AI draft**. This invokes the locally signed-in Codex CLI. A draft includes summary, conditional impact, suggested action, editorial priority, date information and a supporting quotation. Check all of these against the evidence.
4. Enter your reviewer name and review note, then **Approve for brief** or **Reject**. Reviewer names are self-declared local demo labels, not authenticated identities or legal sign-offs.
5. Click **Export brief**. A standalone English HTML newsletter downloads, containing only approved latest versions in the selected mode. Open it in a browser to read or print. The application does not send email.
6. Collect again: identical text creates no extra snapshot. Changed text creates a pending version and removes the previously approved version from current exports until the new version is analyzed and reviewed.

## Offline demonstration

Choose **Offline demo**, then **Load training examples**. Three synthetic examples include a clearly labeled simulated revision. They use preset summaries and priorities, not AI-generated or real regulatory findings. Reference links are contextual only. Review and export work without the network. Loading examples again preserves reviews. Demo and live snapshots are separated in the database, UI and export.

## Real AI configuration

The default executable matches healthcare-directory-demo:

```text
/Applications/ChatGPT.app/Contents/Resources/codex
```

Optional environment variables:

- `REGULATORY_CODEX_BIN`: compatible Codex CLI path.
- `REGULATORY_CODEX_MODEL`: requested model; default `gpt-6-astra`.

The app uses your existing CLI login and applicable account limits. It sends the captured public title and up to 24,000 characters of captured public text to the model. It does not send local private files or copy credentials. Requests use a temporary working directory, ephemeral invocation, read-only sandbox, ignored user configuration, disabled shell tool, JSON Schema and a 90-second timeout. There is no silent mock fallback. Displayed model is requested configuration, not independently attested routing.

Source text is untrusted input. The prompt prohibits executing its instructions. Python checks output shape, editorial-priority enum, required text and exact quotation support (whitespace normalized). Explicit dates need a supporting quote; unsupported dates are replaced with Not established and a visible validation note. These checks do not establish semantic entailment or legal correctness; a human must check applicability, summary accuracy and dates. Failed analysis leaves the previous saved state intact. Successful regeneration clears the old approval.

## Small architecture

- `app.py`: HTTP routes, SQLite persistence, version comparison, review and newsletter rendering.
- `collector.py`: fixed public-source allowlist, bounded HTML fetching, main/article text extraction.
- `analysis.py`: prompt, JSON Schema, Codex invocation and output validation.
- `index.html`: responsive English workspace, search, evidence viewer and export.
- `test_app.py`: meaningful workflow and HTTP regression tests.
- `brief.sqlite3`: generated source snapshots, checks and local activity log; git-ignored.

Sources are configured in `collector.py`. The data model preserves each captured text version, content hash, parent version, capture time, analysis method and review state. The activity log records capture, analysis and approval/rejection events. Diffing is textual, not a legal interpretation. Deduplication is per-source against its immediately preceding snapshot; a return to older content is a new version.

## HTTP API

- `GET /api/health`
- `GET /api/state?mode=live` (or `demo`)
- `GET /api/snapshot?id=1`
- `GET /newsletter?mode=live`
- `POST /api/collect` with `{}`
- `POST /api/demo` with `{}`
- `POST /api/analyze` with `{"id":1}`
- `POST /api/review` with `{"id":1,"status":"approved","reviewer":"Your name","note":"Reviewed for the demonstration"}`

POST requests require JSON. The app binds localhost, validates Host and Origin, allows one mutation/model operation at a time and caps request size. It is not a public multi-user service.

## Verification

```sh
python3 -m unittest -v
```

Tests use temporary databases and mocked collection/model output; the HTTP test opens a temporary loopback port. Live scraping and real model calls are separate smoke checks. Never present mocked tests as measured model accuracy.

## Deliberate scope limits

- Three manually triggered HTML sources; no scheduler, discovery crawler, browser rendering, PDF extraction or automatic API integration.
- Normalized visible-text snapshots, not byte-for-byte HTML archives. Publication dates are not extracted into a dedicated field; capture dates must not be presented as publication dates.
- Single excerpt analysis; no chunking, embeddings, vector database or autonomous agent loop.
- Exact text deduplication per source, not cross-source semantic deduplication.
- Readable current-content search and browsable version history; no full-text index.
- No automatic legal applicability decision, authenticated expert approval, external notifications, recurring publication or production hosting.
- Newsletter is a point-in-time reviewed digest. It is not guaranteed to cover all changes in a calendar week or month.

For production, source permissions/robots policies and schedules need review; add access control, durable queues, retries and freshness alerts, immutable source/analysis histories, reviewer roles, labeled evaluation sets and legal subject-matter validation. These are future work, not PoC capabilities.
