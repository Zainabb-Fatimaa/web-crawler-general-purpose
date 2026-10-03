import json, re
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from extract import parse

UA = "WebCrawler/0.1 (personal learning project)"
MAX_SHOT_HEIGHT = 1800
PAD = 12
_robots_cache = {}

SECTION_BOX_JS = r"""
(text) => {
  const norm = s => s.replace(/\s+/g, '').toLowerCase();
  const want = norm(text);
  const h = [...document.querySelectorAll('h2,h3,h4,h5,h6')].find(e => norm(e.textContent) === want);
  if (!h) return null;
  const level = +h.tagName[1];
  const sel = [2, 3, 4, 5, 6].filter(n => n <= level).map(n => 'h' + n).join(',');
  const isStop = n => n.matches(sel) || n.querySelector(sel) !== null;
  const union = els => {
    let x1 = 1e9, y1 = 1e9, x2 = 0, y2 = 0;
    for (const e of els) {
      const r = e.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top);
      x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    }
    return x2 > x1 ? {x: x1 + scrollX, y: y1 + scrollY, width: x2 - x1, height: y2 - y1} : null;
  };
  let node = h;
  for (let i = 0; i < 3; i++) {
    const els = [node];
    for (let sib = node.nextElementSibling; sib && !isStop(sib); sib = sib.nextElementSibling) els.push(sib);
    if (els.length > 1) return union(els);
    const par = node.parentElement;
    if (!par || ['BODY', 'HTML'].includes(par.tagName)) break;
    node = par;
  }
  return union([h]);
}
"""


def robots_ok(url):
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    if root not in _robots_cache:
        rp = RobotFileParser(root + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots_cache[root] = rp
    rp = _robots_cache[root]
    return True if rp is None else rp.can_fetch(UA, url)


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40] or "page"


class Scraper:
    def __init__(self, rules, out_dir="out", link_shot=True, debug=False):
        self.rules, self.out_dir = rules, out_dir
        self.link_shot, self.debug = link_shot, debug
        Path(out_dir).mkdir(exist_ok=True)

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._ctx = self._browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def _section_shots(self, page, data, slug):
        shots = {}
        for key, heads in data["section_headings"].items():
            if not data["sections"].get(key):
                continue
            for text in heads:
                try:
                    box = page.evaluate(SECTION_BOX_JS, text)
                    if not box:
                        continue
                    x, y = max(box["x"] - PAD, 0), max(box["y"] - PAD, 0)
                    clip = {"x": x, "y": y, "width": box["width"] + 2 * PAD,
                            "height": min(box["height"] + 2 * PAD, MAX_SHOT_HEIGHT)}
                    path = f"{self.out_dir}/{slug}-{key}.png"
                    page.screenshot(path=path, clip=clip, full_page=True)
                    shots[key] = path
                    break
                except Exception as e:
                    data.setdefault("shot_errors", {})[key] = f"{type(e).__name__}: {e}"
        return shots

    def scrape(self, url):
        if not robots_ok(url):
            raise RuntimeError("robots.txt disallows this URL")
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PWTimeout:
                pass

            html = page.content()
            data = parse(html, url, self.rules)
            slug = _slug(data["name"])
            data["screenshots"] = []
            data["section_shots"] = self._section_shots(page, data, slug)
            if self.debug:
                Path(f"{self.out_dir}/{slug}.html").write_text(html, encoding="utf-8")
        finally:
            page.close()

        if self.link_shot and data["links"]:
            other = self._ctx.new_page()
            try:
                other.goto(data["links"][0]["href"], wait_until="domcontentloaded", timeout=25000)
                path = f"{self.out_dir}/{slug}-linked.png"
                other.screenshot(path=path, full_page=True)
                data["screenshots"].append(path)
            except Exception as e:
                data["link_error"] = str(e)
            finally:
                other.close()

        Path(f"{self.out_dir}/{slug}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data
