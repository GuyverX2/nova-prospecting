"""The analyzer is the only component that fetches an operator-supplied URL.

Everything here is about not letting that become a server-side request forgery
primitive, and about the analysis output staying evidence-backed.
"""
from __future__ import annotations

import pytest

from app.prospecting.analyzer import (
    WebsiteAuditError,
    analyze_html,
    normalize_public_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://evil.example/",
        "javascript:alert(1)",
        "ftp://files.example/pub",
        "data:text/html,<script>alert(1)</script>",
    ],
)
def test_non_web_schemes_are_blocked(url):
    with pytest.raises(WebsiteAuditError) as exc:
        normalize_public_url(url)
    assert exc.value.code == "URL_SCHEME_BLOCKED"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:80/",
        "http://169.254.169.254/latest/meta-data/",  # cloud instance metadata
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://0.0.0.0/",
        "http://database.internal/",
        "http://printer.local/",
    ],
)
def test_private_and_metadata_targets_are_blocked(url):
    with pytest.raises(WebsiteAuditError) as exc:
        normalize_public_url(url)
    assert exc.value.code in {"URL_HOST_BLOCKED", "URL_PORT_BLOCKED"}


def test_embedded_credentials_are_blocked():
    with pytest.raises(WebsiteAuditError) as exc:
        normalize_public_url("https://user:secret@acme.example/")
    assert exc.value.code == "URL_CREDENTIALS_BLOCKED"


@pytest.mark.parametrize("port", [22, 3306, 5432, 6379, 8080, 9200])
def test_non_web_ports_are_blocked(port):
    with pytest.raises(WebsiteAuditError) as exc:
        normalize_public_url(f"https://acme.example:{port}/")
    assert exc.value.code == "URL_PORT_BLOCKED"


def test_public_urls_are_normalized_without_fragments():
    assert normalize_public_url("  HTTPS://Acme.Example/start?a=1#top  ") == (
        "https://Acme.Example/start?a=1"
    )
    assert normalize_public_url("https://acme.example") == "https://acme.example/"


def test_analysis_is_deterministic_and_evidence_backed():
    html = """<!doctype html><html lang="sv"><head><title>Acme Bygg AB</title>
    <meta name="description" content="Vi bygger hus i Uppsala och hjalper dig hela vagen hem.">
    <meta name="viewport" content="width=device-width"></head>
    <body><h1>Acme Bygg</h1><img src="a.png" alt="Hus"><a href="/kontakt">Kontakt</a></body></html>"""
    first = analyze_html(html, "https://acme.example")
    second = analyze_html(html, "https://acme.example")
    assert first["metrics"] == second["metrics"]
    assert first["improvement_score"] == second["improvement_score"]
    assert 0 <= first["improvement_score"] <= 100
    for finding in first["findings"]:
        assert finding["title"]
        assert 0 <= float(finding["confidence"]) <= 1
    assert first["evidence"], "findings must be traceable to observed evidence"


def test_analysis_of_a_poor_page_scores_worse_than_a_good_one():
    poor = analyze_html("<html><body><p>Ring oss</p></body></html>", "https://acme.example")
    good = analyze_html(
        """<!doctype html><html lang="sv"><head><title>Acme Bygg AB - snickare i Uppsala</title>
        <meta name="description" content="Vi bygger och renoverar hus i Uppsala sedan 1994.">
        <meta name="viewport" content="width=device-width,initial-scale=1"></head>
        <body><h1>Acme Bygg</h1><img src="a.png" alt="Hus"><a href="mailto:hej@acme.example">Kontakt</a>
        </body></html>""",
        "https://acme.example",
    )
    assert poor["improvement_score"] > good["improvement_score"]


def test_analysis_never_executes_or_echoes_scripts():
    result = analyze_html(
        "<html><head><title>X</title></head><body><script>alert('xss')</script></body></html>",
        "https://acme.example",
    )
    rendered = repr(result)
    assert "alert('xss')" not in rendered
