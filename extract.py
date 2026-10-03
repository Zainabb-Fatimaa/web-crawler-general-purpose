import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
MAX_LINES = 40


def _clean(s):
    return re.sub(r"\s+", " ", s).strip(" •-\t•●")


def _lines_from(tag):
    if tag.name == "a":
        return []
    if tag.name in ("ul", "ol"):
        return [_clean(li.get_text(" ", strip=True)) for li in tag.find_all("li")]
    if tag.name == "table":
        rows = []
        for tr in tag.find_all("tr"):
            if tr.find("td") is None:
                continue
            cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(" | ".join(cells))
        return rows
    lines = []
    for ln in tag.get_text("\n", strip=True).split("\n"):
        ln = _clean(ln)
        if ln:
            lines.append(ln)
    return lines


def _is_stop(sib, level):
    stop = {h for h in HEADINGS if int(h[1]) <= level}
    return sib.name in stop or sib.find(list(stop)) is not None


def _collect_after(heading):
    level = int(heading.name[1])
    node = heading
    for _ in range(3):
        items = []
        for sib in node.next_siblings:
            if not isinstance(sib, Tag):
                continue
            if _is_stop(sib, level):
                break
            items.extend(_lines_from(sib))
        if items:
            return items
        if node.parent is None or node.parent.name in ("body", "html", "[document]"):
            break
        node = node.parent
    return []


def _dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def parse(html, base_url, rules):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        t.decompose()

    t = soup.select_one(rules.get("title_selector", "h1"))
    name = _clean(t.get_text(" ", strip=True)) if t else (soup.title.string.strip() if soup.title else base_url)

    sections = {k: [] for k in rules["sections"]}
    headings = {k: [] for k in rules["sections"]}
    for h in soup.find_all(HEADINGS[1:]):
        text = h.get_text(" ", strip=True).lower()
        for key, kws in rules["sections"].items():
            if any(kw in text for kw in kws):
                sections[key] += _collect_after(h)
                headings[key].append(re.sub(r"\s+", " ", h.get_text(" ", strip=True)))
                break
    sections = {k: _dedupe(v)[:MAX_LINES] for k, v in sections.items()}

    body_lines = None
    for key, kws in rules.get("line_fallback", {}).items():
        if sections.get(key):
            continue
        if body_lines is None:
            body_lines = soup.get_text("\n", strip=True).split("\n")
        hits = [_clean(l) for l in body_lines if any(k in l.lower() for k in kws)]
        sections[key] = _dedupe(hits)[:5]

    base_host = urlparse(base_url).netloc
    ignore = rules.get("ignore_link_domains", [])
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        host = urlparse(href).netloc
        if not href.startswith("http") or host == base_host or any(d in host for d in ignore):
            continue
        txt = a.get_text(" ", strip=True)
        if any(k in txt.lower() for k in rules.get("link_keywords", [])) and href not in seen:
            seen.add(href)
            links.append({"text": txt, "href": href})

    return {"source_url": base_url, "name": name, "sections": sections,
            "section_headings": headings, "links": links}
