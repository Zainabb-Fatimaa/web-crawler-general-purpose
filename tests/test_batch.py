import sys, json, pathlib, tempfile
root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from batch import load_urls, run_batch

tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "u.txt").write_text("# comment\nhttps://a/1\n\nhttps://a/2  # inline\nhttps://a/1\nhttps://a/3\nhttps://a/4\n")
urls = load_urls(tmp / "u.txt")
assert urls == ["https://a/1", "https://a/2", "https://a/3", "https://a/4"], urls

full = {"deadline": ["x"], "benefits": []}
def scrape(u):
    if u.endswith("/3"): raise RuntimeError("boom")
    if u.endswith("/4"): return {"name": "Empty", "sections": {"deadline": [], "benefits": []}}
    return {"name": "P" + u[-1], "sections": full}

added = []
st = str(tmp / "s.json")
r = run_batch(urls, scrape, added.append, st, delay=0, log=lambda *_: None)
assert [d["name"] for d in added] == ["P1", "P2"], added
assert len(r["failed"]) == 2 and r["skipped"] == [], r

added.clear()
r2 = run_batch(urls, scrape, added.append, st, delay=0, log=lambda *_: None)
assert r2["skipped"] == ["https://a/1", "https://a/2"] and added == [], r2
assert len(r2["failed"]) == 2

def bad_add(d): raise ValueError("doc error")
r3 = run_batch(["https://a/1"], scrape, bad_add, str(tmp / "s2.json"), delay=0, log=lambda *_: None)
assert len(r3["failed"]) == 1 and json.load(open(tmp / "s2.json"))["https://a/1"]["status"] == "failed"
print("batch tests passed")
