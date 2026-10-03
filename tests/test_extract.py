import json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from extract import parse

rules = json.loads((root / "rules.example.json").read_text())
html = (root / "tests" / "sample_page.html").read_text()
d = parse(html, "https://example.com/items/sample-1/", rules)
s = d["sections"]

assert d["name"] == "Sample Item A", d["name"]
assert s["summary"] == ["A short description of the item."], s
assert s["requirements"] == ["Python 3.10 or newer", "Internet access"], s
assert s["resources"] == ["User guide", "Changelog"], s
assert s["steps"] == ["Install the package.", "Run the example script."], s
assert s["dates"] == ["15 January 2027"], s
assert s["pricing"] == ["Free tier", "Pro plan"], s
assert d["section_headings"]["requirements"] == ["Requirements"], d["section_headings"]
assert [l["href"] for l in d["links"]] == ["https://docs.example.org/start"], d["links"]
print("all extraction tests passed")
