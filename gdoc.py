import os, struct, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/documents",
          "https://www.googleapis.com/auth/drive.file"]


def get_services():
    cred_file = os.getenv("GOOGLE_CREDENTIALS_FILE") or "credentials.json"
    token_file = os.getenv("GOOGLE_TOKEN_FILE") or "token.json"
    if not os.path.exists(cred_file) and not os.path.exists(token_file):
        raise FileNotFoundError(
            f"Google OAuth file not found: {cred_file}. Download a Desktop-app OAuth client "
            "from Google Cloud Console or set GOOGLE_CREDENTIALS_FILE in .env")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("docs", "v1", credentials=creds), build("drive", "v3", credentials=creds)


def u16(s):
    return len(s.encode("utf-16-le")) // 2


class DocWriter:
    def __init__(self, docs, doc_id):
        self.docs, self.id = docs, doc_id

    def _get(self):
        return self.docs.documents().get(documentId=self.id).execute()

    def _end(self):
        return self._get()["body"]["content"][-1]["endIndex"] - 1

    def _do(self, reqs):
        if not reqs:
            return
        for attempt in range(4):
            try:
                self.docs.documents().batchUpdate(documentId=self.id, body={"requests": reqs}).execute()
                return
            except HttpError as e:
                if e.resp.status in (429, 500, 503) and attempt < 3:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise

    def is_empty(self):
        return self._end() <= 1

    def page_break(self):
        self._do([{"insertPageBreak": {"endOfSegmentLocation": {}}}])
        self._do([{"insertText": {"endOfSegmentLocation": {}, "text": "\n"}}])

    def para(self, text, style="NORMAL_TEXT", link=None):
        start = self._end()
        end = start + u16(text) + 1
        reqs = [
            {"insertText": {"location": {"index": start}, "text": text + "\n"}},
            {"updateParagraphStyle": {"range": {"startIndex": start, "endIndex": end},
                                      "paragraphStyle": {"namedStyleType": style},
                                      "fields": "namedStyleType"}},
            {"deleteParagraphBullets": {"range": {"startIndex": start, "endIndex": end}}},
        ]
        if link:
            reqs.append({"updateTextStyle": {"range": {"startIndex": start, "endIndex": end - 1},
                                             "textStyle": {"link": {"url": link}}, "fields": "link"}})
        self._do(reqs)

    def checklist(self, items):
        items = [i for i in items if i and i.strip()] or ["(nothing found - add manually)"]
        text = "\n".join(items) + "\n"
        start = self._end()
        end = start + u16(text)
        self._do([
            {"insertText": {"location": {"index": start}, "text": text}},
            {"updateParagraphStyle": {"range": {"startIndex": start, "endIndex": end},
                                      "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                      "fields": "namedStyleType"}},
            {"createParagraphBullets": {"range": {"startIndex": start, "endIndex": end},
                                        "bulletPreset": "BULLET_CHECKBOX"}},
        ])

    def table(self, header, rows):
        data = [header] + rows
        self._do([{"insertTable": {"rows": len(data), "columns": len(header),
                                   "location": {"index": self._end()}}}])
        tbl = [c for c in self._get()["body"]["content"] if "table" in c][-1]["table"]
        reqs = []
        for r in reversed(range(len(data))):
            for c in reversed(range(len(header))):
                txt = data[r][c]
                if txt:
                    idx = tbl["tableRows"][r]["tableCells"][c]["content"][0]["startIndex"]
                    reqs.append({"insertText": {"location": {"index": idx}, "text": txt}})
        self._do(reqs)

    def image(self, uri, width_pt, height_pt):
        start = self._end()
        self._do([
            {"insertInlineImage": {"location": {"index": start}, "uri": uri,
                                   "objectSize": {"width": {"magnitude": width_pt, "unit": "PT"},
                                                  "height": {"magnitude": height_pt, "unit": "PT"}}}},
            {"insertText": {"location": {"index": start + 1}, "text": "\n"}},
        ])


def upload_to_drive(drive, path, folder_id=None):
    body = {"name": os.path.basename(path)}
    if folder_id:
        body["parents"] = [folder_id]
    f = drive.files().create(body=body, media_body=MediaFileUpload(path),
                             fields="id,webViewLink").execute()
    return f["id"], f["webViewLink"]


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[1:4] != b"PNG":
        return None
    return struct.unpack(">II", head[16:24])


def fit_size(px, max_w=468, max_h=648):
    w, h = px or (4, 3)
    scale = min(max_w / w, max_h / h)
    return round(w * scale, 1), round(h * scale, 1)


def embed_image(writer, drive, file_id, path):
    perm = drive.permissions().create(fileId=file_id, body={"type": "anyone", "role": "reader"},
                                      fields="id").execute()
    try:
        w, h = fit_size(png_size(path))
        writer.image(f"https://drive.google.com/uc?export=view&id={file_id}", w, h)
    finally:
        drive.permissions().delete(fileId=file_id, permissionId=perm["id"]).execute()


def attach_shot(writer, drive, data, key, folder_id=None):
    shot = (data.get("section_shots") or {}).get(key)
    if not shot or not os.path.exists(shot):
        return
    file_id, link = upload_to_drive(drive, shot, folder_id)
    try:
        embed_image(writer, drive, file_id, shot)
    except Exception as e:
        print(f"  ! could not embed {os.path.basename(shot)} ({type(e).__name__}: {e}); link kept")
        writer.para(f"Screenshot: {os.path.basename(shot)}", link=link)


def add_entry(writer, drive, data, rules, folder_id=None):
    if not writer.is_empty():
        writer.page_break()

    titles = rules.get("section_titles", {})
    layouts = rules.get("layouts", {})
    order = [k for k in rules.get("display_order", []) if k in data["sections"]]
    order += [k for k in data["sections"] if k not in order]

    writer.para(data["name"], "HEADING_1")

    n = 1
    writer.para(f"{n}. Links", "HEADING_2")
    writer.para("Source page", link=data["source_url"])
    for l in data["links"][:3]:
        writer.para(l["text"] or l["href"], link=l["href"])
    for shot in data.get("screenshots", []):
        _, link = upload_to_drive(drive, shot, folder_id)
        writer.para(f"Screenshot: {os.path.basename(shot)}", link=link)

    for key in order:
        n += 1
        lines = data["sections"][key]
        title = titles.get(key) or key.replace("_", " ").capitalize()
        writer.para(f"{n}. {title}", "HEADING_2")
        layout = layouts.get(key, "checklist")
        if layout == "table":
            rows = [[d, "", "☐"] for d in lines or ["(add manually)"]]
            writer.table(["Item", "Notes", "Done"], rows)
        elif layout == "text":
            writer.para(" ".join(lines) or "(not found - verify at the source)")
        else:
            writer.checklist(lines)
        attach_shot(writer, drive, data, key, folder_id)

    notes = rules.get("notes")
    if notes:
        n += 1
        writer.para(f"{n}. {rules.get('notes_title', 'Notes')}", "HEADING_2")
        writer.checklist(notes)
