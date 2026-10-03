import argparse, json, os, re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from scrape import Scraper
from batch import load_urls, run_batch, print_report


def google_id(value):
    if not value:
        return value
    m = re.search(r"/(?:d|folders)/([A-Za-z0-9_-]+)", value)
    return m.group(1) if m else value.strip()


def default_rules_file():
    env = os.getenv("RULES_FILE")
    if env:
        return env
    return "rules.json" if Path("rules.json").exists() else "rules.example.json"


def main():
    ap = argparse.ArgumentParser(description="Rule-driven web crawler: Playwright (Chromium) -> Google Docs")
    ap.add_argument("url", nargs="?", help="single page URL")
    ap.add_argument("--urls-file", help="text file with one URL per line")
    ap.add_argument("--doc", default=os.getenv("GOOGLE_DOC_ID") or None, help="Google Doc ID or URL (env: GOOGLE_DOC_ID)")
    ap.add_argument("--folder", default=os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None,
                    help="Drive folder ID or URL for screenshots (env: GOOGLE_DRIVE_FOLDER_ID)")
    ap.add_argument("--rules", default=default_rules_file())
    ap.add_argument("--delay", type=float, default=float(os.getenv("CRAWL_DELAY_SECONDS") or 5),
                    help="seconds between pages (env: CRAWL_DELAY_SECONDS, default 5)")
    ap.add_argument("--force", action="store_true", help="re-process URLs already added")
    ap.add_argument("--allow-empty", action="store_true", help="add pages even if no sections were found")
    ap.add_argument("--dry-run", action="store_true", help="scrape only; do not touch Google")
    ap.add_argument("--no-link-shot", action="store_true", help="skip the screenshot of the first outbound link")
    ap.add_argument("--debug", action="store_true", help="save rendered HTML to out/")
    a = ap.parse_args()
    a.doc, a.folder = google_id(a.doc), google_id(a.folder)

    urls_file = a.urls_file or (None if a.url else (os.getenv("URLS_FILE") or None))
    urls = ([a.url] if a.url else []) + (load_urls(urls_file) if urls_file else [])
    urls = list(dict.fromkeys(urls))
    if not urls:
        ap.error("give a URL, --urls-file, or set URLS_FILE in .env")
    if not a.doc and not a.dry_run:
        ap.error("give --doc, set GOOGLE_DOC_ID in .env, or use --dry-run")

    rules = json.loads(Path(a.rules).read_text(encoding="utf-8"))
    add_fn = None
    if not a.dry_run:
        from gdoc import get_services, DocWriter, add_entry
        docs, drive = get_services()
        writer = DocWriter(docs, a.doc)
        add_fn = lambda data: add_entry(writer, drive, data, rules, a.folder)

    state_file = "out/state.json" if not a.dry_run else "out/state_dryrun.json"
    with Scraper(rules, link_shot=not a.no_link_shot, debug=a.debug) as sc:
        res = run_batch(urls, sc.scrape, add_fn, state_file=state_file, delay=a.delay,
                        force=a.force or a.dry_run, require_content=not a.allow_empty)
    print_report(res)


if __name__ == "__main__":
    main()
