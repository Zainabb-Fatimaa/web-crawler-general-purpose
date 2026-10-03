# web-crawler

A general-purpose, rule-driven web crawler built on Playwright (Chromium). It loads pages in a real
browser, extracts the sections you define in a rules file, takes a cropped screenshot of each section,
and writes everything to a Google Doc through your own Google account, with each screenshot embedded
under its section.

```
URL -> Playwright (render + screenshots) -> extract.py (rules) -> gdoc.py -> Google Doc + Drive
```

## Features
- Rendered pages via headless Chromium, so JavaScript-heavy sites work
- Sections are matched by heading keywords defined in a JSON rules file; no code changes needed
- One cropped screenshot per section, uploaded to Drive and embedded in the Doc
- Batch mode with resume: progress is saved after every URL and failures never stop the run
- Respects `robots.txt` and pauses between requests
- Dry-run mode that needs no Google account

## Install
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Configure the rules
Copy `rules.example.json` to `rules.json` and edit it. If `rules.json` is missing, the example is used.

| Key | Purpose |
|---|---|
| `title_selector` | CSS selector for the page title |
| `sections` | `name -> [heading keywords]`; a heading goes to the first section whose keyword it contains |
| `layouts` | optional per section: `checklist` (default), `table` or `text` |
| `section_titles` | optional display names for sections in the Doc |
| `display_order` | optional order of sections in the Doc |
| `line_fallback` | `section -> [keywords]`; if a section is empty, use body lines containing a keyword |
| `link_keywords` | outbound links whose text contains one of these are listed |
| `ignore_link_domains` | outbound domains to skip |
| `notes`, `notes_title` | optional closing checklist added to every entry |

Try a scrape without Google first and inspect the JSON in `out/`:
```bash
python main.py "https://example.com/some-page/" --dry-run --debug
```
If a section is empty, open the saved HTML in `out/`, look at the real headings and add those words to `sections`.

## Connect your Google account
1. In Google Cloud Console create a project and enable the **Google Docs API** and **Google Drive API**.
2. Configure the OAuth consent screen and add yourself as a test user.
3. Create an **OAuth client ID** of type **Desktop app** and save the JSON as `credentials.json` here.
4. Create a Google Doc and, optionally, a Drive folder for screenshots.
5. Copy `.env.example` to `.env` and fill in the Doc and folder. A bare ID or the full URL both work.

The first run opens a browser to sign in and stores `token.json`. Delete it to switch accounts.

## Run
```bash
python main.py "<url>" --doc <DOC_ID_OR_URL> --folder <FOLDER_ID_OR_URL>
python main.py --urls-file urls.txt
```
Put one URL per line in `urls.txt` (`#` starts a comment).

| Flag | Effect |
|---|---|
| `--dry-run` | scrape only, no Google calls |
| `--force` | reprocess URLs already added |
| `--allow-empty` | add pages even if no section matched |
| `--no-link-shot` | skip the screenshot of the first outbound link |
| `--delay N` | seconds between pages (default 5) |
| `--debug` | save rendered HTML to `out/` |

Re-running the same command resumes: finished URLs are skipped and failed ones retried.

## How screenshots are attached
Google Docs can only insert images from a URL it can fetch. Each section screenshot is uploaded to your
Drive, shared as "anyone with the link" for the instant of the insert, then made private again. The Doc keeps
its own copy. If embedding fails, a link to the Drive file is added instead.

## Tests
```bash
python tests/test_extract.py
python tests/test_batch.py
python tests/test_gdoc_mock.py
```

## Files
| File | Purpose |
|---|---|
| `main.py` | CLI entry point |
| `scrape.py` | Playwright: page loading, section screenshots, robots check |
| `extract.py` | HTML + rules -> structured data |
| `gdoc.py` | Google Docs and Drive writer |
| `batch.py` | URL loop, resume state, error handling |
| `rules.example.json` | Example rules |

## Notes
Check each site's terms of use and keep request rates low. `credentials.json`, `token.json`, `.env`,
`rules.json`, `urls.txt` and `out/` are git-ignored.
