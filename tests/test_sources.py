"""Synthetic inputs only; every URL request is injected and all sockets are blocked."""
import builtins
from io import BytesIO
import socket
import sys

import pytest

from rag_research_agent.ingest.sources import (
    SourceError, fetch_url, github_raw_url, google_doc_export_url, is_x_url,
    load_docx, load_pdf, load_source, load_text_file,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("test attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def test_text_utf8_bom_and_markdown(tmp_path):
    path = tmp_path / "가상.md"
    path.write_text("# 합성 문서\n핵심은 비용이다.", encoding="utf-8-sig")
    doc = load_source(path)
    assert doc.text == "# 합성 문서\n핵심은 비용이다."
    assert doc.title == path.name and doc.fetched_at.endswith("+00:00")
    assert load_text_file(path).source_id == doc.source_id


def test_html_excludes_chrome_and_keeps_inline_words():
    html = b"<html><head><title>hidden title</title></head><body><nav>menu</nav><article><h1>Synthetic</h1><p>Hello <b>world</b>.</p><script>bad()</script><style>css</style><aside>ad</aside><footer>footer</footer></article></body></html>"
    doc = fetch_url("https://example.invalid/article", lambda _: (200, "text/html; charset=utf-8", html))
    assert doc.text == "Synthetic\nHello world."


def test_google_export_and_text():
    url = "https://docs.google.com/document/d/fake_123/edit?usp=sharing"
    exported = "https://docs.google.com/document/d/fake_123/export?format=txt"
    assert google_doc_export_url(url) == exported
    calls = []
    def fetcher(target):
        calls.append(target)
        return 200, "text/plain", "합성 공유 문서입니다.".encode()
    assert fetch_url(url, fetcher).text == "합성 공유 문서입니다."
    assert calls == [exported]


@pytest.mark.parametrize("response", [(401, "text/plain", b""), (403, "text/plain", b""),
                                       (200, "text/html", b'<form action="https://accounts.google.com/ServiceLogin">')])
def test_google_access_denied(response):
    with pytest.raises(SourceError, match="링크 공유.*--file"):
        fetch_url("https://docs.google.com/document/d/fake/edit", lambda _: response)


def test_github_blob_and_readme_fallback():
    url = "https://github.com/synthetic/project/blob/main/docs/test.md"
    raw = "https://raw.githubusercontent.com/synthetic/project/main/docs/test.md"
    assert github_raw_url(url) == raw
    calls = []
    def fetcher(target):
        calls.append(target)
        return (200, "text/plain", b"# Synthetic markdown") if target.endswith("README.ko.md") else (404, "", b"")
    doc = fetch_url("https://github.com/synthetic/project/", fetcher)
    assert doc.text == "# Synthetic markdown"
    assert calls == ["https://raw.githubusercontent.com/synthetic/project/HEAD/README.md",
                     "https://raw.githubusercontent.com/synthetic/project/HEAD/README.ko.md"]
    calls.clear()
    fetch_url(url, lambda target: (calls.append(target) or 200, "text/plain", b"# body"))
    assert calls == [raw]


def test_github_last_readme_fallback_and_issue_html():
    calls = []
    def fetcher(target):
        calls.append(target)
        return (200, "text/plain", b"# body") if target.endswith("readme.md") else (404, "", b"")
    fetch_url("https://github.com/synthetic/project", fetcher)
    assert len(calls) == 3 and calls[-1].endswith("/HEAD/readme.md")
    url = "https://github.com/synthetic/project/issues/1"
    assert github_raw_url(url) == url
    assert fetch_url(url, lambda _: (200, "text/html", b"<p>Synthetic issue</p>")).text == "Synthetic issue"


@pytest.mark.parametrize("status", [401, 403, 404])
def test_github_private_or_missing(status):
    with pytest.raises(SourceError, match=f"HTTP {status}.*공개"):
        fetch_url("https://github.com/synthetic/private", lambda _: (status, "", b""))


@pytest.mark.parametrize("host", ["x.com", "twitter.com", "mobile.twitter.com", "www.x.com"])
def test_x_never_fetches(host):
    url = f"https://{host}/synthetic/status/1"
    assert is_x_url(url)
    def unexpected(_):
        raise AssertionError("X must never be fetched")
    with pytest.raises(SourceError, match="X는.*--text"):
        fetch_url(url, unexpected)
    assert not is_x_url("https://x.com.example.invalid")


def test_network_permission_and_invalid_scheme():
    def unexpected(_):
        raise AssertionError("network permission missing")
    with pytest.raises(SourceError, match="--allow-network"):
        load_source("https://example.invalid", False, unexpected)
    with pytest.raises(SourceError, match="http/https"):
        load_source("file:///private", True, unexpected)


def _pdf_bytes(text=True):
    # A complete synthetic, single-page PDF with a basic Type1 text layer.
    stream = b"BT /F1 12 Tf 20 100 Td (Synthetic document text layer.) Tj ET" if text else b""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    raw, offsets = b"%PDF-1.4\n", [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(raw)
    raw += b"xref\n0 6\n0000000000 65535 f \n"
    raw += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets[1:])
    return raw + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


def test_pdf_extraction_or_optional_installation(tmp_path):
    try:
        import pypdf
    except ImportError:
        with pytest.raises(SourceError, match=r"\[pdf\]"):
            load_pdf(_pdf_bytes())
        return
    doc = load_pdf(_pdf_bytes())
    assert "Synthetic document text layer." in doc.text
    assert doc.pages[0]["page"] == 1
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(_pdf_bytes())
    assert load_source(path).text == doc.text
    with pytest.raises(SourceError, match="스캔 PDF.*OCR 미지원"):
        load_pdf(_pdf_bytes(False))
    for url, kind in [("https://example.invalid/a", "application/pdf"), ("https://example.invalid/a.pdf", "application/octet-stream")]:
        fetched = fetch_url(url, lambda _: (200, kind, _pdf_bytes()))
        assert fetched.text == doc.text and fetched.origin == url and fetched.pages == doc.pages


@pytest.mark.parametrize("module,loader,extra", [("pypdf", load_pdf, "pdf"), ("docx", load_docx, "docx")])
def test_missing_optional_readers_are_actionable(monkeypatch, module, loader, extra):
    original = builtins.__import__
    def unavailable(name, *a, **kw):
        if name == module:
            raise ImportError("synthetic missing extra")
        return original(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(SourceError, match=rf"\[{extra}\]"):
        loader("synthetic." + extra)


def test_docx_text_or_optional_installation(tmp_path):
    try:
        from docx import Document
    except ImportError:
        with pytest.raises(SourceError, match=r"\[docx\]"):
            load_docx(tmp_path / "synthetic.docx")
        return
    path = tmp_path / "synthetic.docx"
    doc = Document()
    doc.add_paragraph("합성 문단")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "합성 표"
    doc.save(path)
    assert load_source(path).text == "합성 문단\n합성 표"
