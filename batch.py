import json, time
from datetime import datetime
from pathlib import Path


def load_urls(path):
    seen, urls = set(), []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split(" #")[0].strip()
        if line and not line.startswith("#") and line not in seen:
            seen.add(line)
            urls.append(line)
    return urls


def _load_state(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else {}


def _save_state(p, state):
    Path(p).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_batch(urls, scrape_fn, add_fn, state_file="out/state.json", delay=5.0,
              force=False, require_content=True, log=print):
    state = _load_state(state_file)
    res = {"added": [], "skipped": [], "failed": []}
    total = len(urls)
    first = True

    for i, url in enumerate(urls, 1):
        tag = f"[{i}/{total}]"
        if not force and url in state and state[url].get("status") == "added":
            log(f"{tag} skip (already added): {state[url]['name']}")
            res["skipped"].append(url)
            continue

        if not first:
            time.sleep(delay)
        first = False

        try:
            log(f"{tag} scraping {url}")
            data = scrape_fn(url)
            found = sum(1 for v in data["sections"].values() if v)
            if require_content and found == 0:
                raise ValueError("no sections found - tune the rules file (use --debug)")
            if add_fn:
                add_fn(data)
                state[url] = {"status": "added", "name": data["name"],
                              "sections_found": found, "at": datetime.now().isoformat(timespec="seconds")}
                log(f"{tag} added: {data['name']} ({found}/{len(data['sections'])} sections found)")
            else:
                log(f"{tag} dry-run: {data['name']} ({found}/{len(data['sections'])} sections found)")
            res["added"].append(url)
        except KeyboardInterrupt:
            log("Interrupted - progress saved. Re-run the same command to resume.")
            _save_state(state_file, state)
            raise
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            log(f"{tag} FAILED: {reason}")
            state[url] = {"status": "failed", "reason": reason,
                          "at": datetime.now().isoformat(timespec="seconds")}
            res["failed"].append((url, reason))
        _save_state(state_file, state)

    return res


def print_report(res, log=print):
    log("\n=== Summary ===")
    log(f"Added/processed: {len(res['added'])}   Skipped: {len(res['skipped'])}   Failed: {len(res['failed'])}")
    for url, reason in res["failed"]:
        log(f"  x {url}\n      {reason}")
    if res["failed"]:
        log("Fix the cause (or the rules file) and re-run the same command: only failed URLs are retried.")
