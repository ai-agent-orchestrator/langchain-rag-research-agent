"""Local documents and explicitly enabled public URLs; optional readers are lazy imports."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SourceError(ValueError):
    """An input cannot be read without user intervention."""


@dataclass(frozen=True)
class Document:
    source_id: str
    title: str
    text: str
    origin: str
    fetched_at: str
    pages: list[dict] | None = None


def _document(text, origin, title, pages=None):
    return Document(sha256((origin + "\0" + text).encode()).hexdigest()[:16], title,
                    text, origin, datetime.now(timezone.utc).isoformat(), pages)


def load_text_file(path):
    path = Path(path)
    if path.suffix.lower() not in (".txt", ".md"):
        raise SourceError("텍스트 파일은 .txt 또는 .md를 사용해 주세요")
    return _document(path.read_text(encoding="utf-8-sig"), str(path.resolve()), path.name)


def load_docx(path):
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise SourceError('DOCX 지원 설치: pip install -e ".[docx]"') from exc
    path = Path(path)
    try:
        doc = DocxDocument(path)
        # iter_inner_content preserves paragraph/table order (including table cells).
        pieces = []
        for block in doc.iter_inner_content():
            if hasattr(block, "text"):
                pieces.append(block.text)
            else:
                pieces.extend("\t".join(cell.text for cell in row.cells) for row in block.rows)
        return _document("\n".join(pieces), str(path.resolve()), path.name)
    except Exception as exc:
        raise SourceError(f"DOCX를 읽을 수 없습니다: {path.name}") from exc


def load_pdf(path_or_bytes):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SourceError('PDF 지원 설치: pip install -e ".[pdf]"') from exc
    is_bytes = isinstance(path_or_bytes, bytes)
    origin = "pdf:bytes" if is_bytes else str(Path(path_or_bytes).resolve())
    try:
        reader = PdfReader(BytesIO(path_or_bytes) if is_bytes else path_or_bytes)
        pages = [{"page": n, "text": page.extract_text() or ""}
                 for n, page in enumerate(reader.pages, 1)]
    except Exception as exc:
        raise SourceError("PDF를 읽을 수 없습니다. 암호화 또는 손상 여부를 확인해 주세요") from exc
    text = "\n\n".join(p["text"] for p in pages)
    if sum(c.isalnum() for c in text) < 10:
        raise SourceError("스캔 PDF로 보임, OCR 미지원. 텍스트 파일로 넣어 주세요")
    return _document(text, origin, "document.pdf" if is_bytes else Path(path_or_bytes).name, pages)


def is_x_url(url):
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ("x.com", "twitter.com"))


def _validate_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise SourceError("인증 정보 없는 http/https 공개 주소를 사용해 주세요")
    if is_x_url(url):
        raise SourceError("X는 로그인·약관 때문에 자동 수집하지 않습니다. 본문을 복사해 --text 또는 파일로 넣어 주세요")


def google_doc_export_url(url):
    p = urlsplit(url)
    match = re.match(r"/document/d/([A-Za-z0-9_-]+)(?:/|$)", p.path)
    if p.hostname == "docs.google.com" and match:
        return f"https://docs.google.com/document/d/{match[1]}/export?format=txt"
    return url


def github_raw_url(url):
    p = urlsplit(url)
    parts = p.path.strip("/").split("/")
    if p.hostname == "github.com" and len(parts) >= 5 and parts[2] == "blob":
        return "https://raw.githubusercontent.com/" + "/".join(parts[:2] + parts[3:])
    if p.hostname == "github.com" and len(parts) == 2:
        return "https://raw.githubusercontent.com/" + "/".join(parts) + "/HEAD/README.md"
    return url


class _HTMLText(HTMLParser):
    ignored = {"script", "style", "nav", "footer", "aside", "head"}
    blocks = {"p", "div", "br", "li", "section", "article", "h1", "h2", "h3", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.pieces = []

    def handle_starttag(self, tag, attrs):
        if tag in self.ignored:
            self.hidden.append(tag)
        if not self.hidden and tag in self.blocks:
            self.pieces.append("\n")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in self.blocks:
            self.pieces.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.pieces.append(data)

    def text(self):
        return "\n".join(line.strip() for line in "".join(self.pieces).splitlines() if line.strip())


class _PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)  # X redirects must never be fetched either.
        if urlsplit(newurl).hostname == "accounts.google.com":
            raise SourceError(_GOOGLE_HELP)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url):
    try:
        req = Request(url, headers={"User-Agent": "RRA-Prototype/1.0"})
        with build_opener(_PublicRedirect()).open(req, timeout=20) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), b""
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"주소에 접속할 수 없습니다: {exc}") from exc


_GOOGLE_HELP = "링크 공유를 켜거나 txt/docx로 내려받아 --file로 넣어 주세요"


def fetch_url(url, fetcher=None):
    _validate_url(url)
    google = google_doc_export_url(url)
    target = github_raw_url(google)
    candidates = [target]
    if target.endswith("/HEAD/README.md"):
        candidates += [target.removesuffix("README.md") + name for name in ("README.ko.md", "readme.md")]
    fetcher = fetcher or _fetch
    for candidate in candidates:
        status, content_type, raw = fetcher(candidate)
        if status != 404:
            break
    if google != url and status in (401, 403):
        raise SourceError(_GOOGLE_HELP)
    if not 200 <= status < 300:
        raise SourceError(f"HTTP {status}: 공개 주소와 접근 권한을 확인해 주세요 (비공개 GitHub 인증 미지원)")
    kind = content_type.split(";", 1)[0].strip().lower()
    if kind == "application/pdf" or urlsplit(candidate).path.lower().endswith(".pdf"):
        doc = load_pdf(raw)
        return replace(doc, source_id=sha256((url + doc.text).encode()).hexdigest()[:16], origin=url,
                       title=Path(urlsplit(url).path).name or "document.pdf")
    text = raw.decode("utf-8-sig")
    if google != url and ("accounts.google.com" in text.lower() or "servicelogin" in text.lower()
                          or kind in ("text/html", "application/xhtml+xml")):
        raise SourceError(_GOOGLE_HELP)
    if kind in ("text/html", "application/xhtml+xml") or (not kind and text.lstrip().lower().startswith(("<!doctype html", "<html"))):
        parser = _HTMLText()
        parser.feed(text)
        text = parser.text()
    return _document(text, url, Path(urlsplit(url).path).name or urlsplit(url).hostname)


def load_source(arg, allow_network=False, fetcher=None):
    value = str(arg)
    if "://" in value:
        _validate_url(value)
        if not allow_network:
            raise SourceError("URL 입력은 --allow-network를 명시해야 가져옵니다")
        return fetch_url(value, fetcher)
    path = Path(value)
    loader = {".txt": load_text_file, ".md": load_text_file, ".docx": load_docx, ".pdf": load_pdf}.get(path.suffix.lower())
    if loader is None:
        raise SourceError("지원 파일: .txt, .md, .docx, .pdf")
    return loader(path)
