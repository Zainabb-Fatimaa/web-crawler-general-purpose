import sys, pathlib, json
root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from gdoc import DocWriter, add_entry, u16
import gdoc


class FakeExec:
    def __init__(s, f): s.f = f
    def execute(s): return s.f()


class FakeDocs:
    def __init__(s): s.end = 2; s.log = []
    def documents(s): return s
    def get(s, documentId):
        tbl = {"table": {"tableRows": [{"tableCells": [{"content": [{"startIndex": 10 + r * 10 + c}]} for c in range(3)]} for r in range(8)]}}
        return FakeExec(lambda: {"body": {"content": [tbl, {"endIndex": s.end}]}})
    def batchUpdate(s, documentId, body):
        for r in body["requests"]:
            s.log.append(list(r)[0])
            if "insertText" in r: s.end += u16(r["insertText"]["text"])
        return FakeExec(lambda: {})


class FakeDrive:
    def files(s): return s
    def create(s, **kw): return FakeExec(lambda: {"id": "x", "webViewLink": "https://drive.example/x"})


gdoc.upload_to_drive = lambda drive, path, folder=None: ("FILEID", "https://drive.example/x")
gdoc.embed_image = lambda writer, drive, fid, path: writer.image("https://drive.example/uc?id=" + fid, 468, 300)

rules = json.load(open(root / "rules.example.json"))
data = json.load(open(root / "tests" / "sample_result.json"))
data["section_shots"] = {k: str(root / "tests" / "sample_page.html") for k in data["sections"]}

w = DocWriter(FakeDocs(), "DOC")
add_entry(w, FakeDrive(), data, rules)
add_entry(w, FakeDrive(), data, rules)
kinds = w.docs.log
assert "insertPageBreak" in kinds and "insertTable" in kinds and "createParagraphBullets" in kinds
assert kinds.count("insertInlineImage") == 2 * len(data["sections"]), kinds.count("insertInlineImage")
print("mock gdoc test passed;", len(kinds), "requests issued")
