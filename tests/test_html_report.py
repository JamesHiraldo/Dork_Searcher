from html.parser import HTMLParser

from src.discovery import DiscoveryResult
from src.html_report import render_html
from src.inventory import Inventory


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.links = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)
        if tag == "a":
            self.links.append(dict(attrs).get("href"))


def test_html_export_is_self_contained_and_escapes_research_data(tmp_path):
    hostile = '</pre><script>alert("x")</script><img src="https://evil.invalid/x" onerror="x">'
    with Inventory(tmp_path / "inventory.sqlite3") as store:
        store.merge(
            "example.com",
            DiscoveryResult(
                "crtsh",
                [
                    {
                        "hostname": "api.example.com",
                        "note": hostile,
                        "url": "https://api.example.com/?q=" + hostile,
                    }
                ],
                error=hostile,
            ),
        )
        store.save_check(
            "example.com",
            {
                "hostname": "api.example.com",
                "checked_at": "2026-10-27",
                "state": hostile,
                "addresses": [hostile],
            },
        )
        report = store.export("example.com", tmp_path)
        content = report.with_suffix(".html").read_text(encoding="utf-8")
    document = Document()
    document.feed(content)
    assert not {"script", "img", "iframe", "object", "embed", "link", "base", "form"} & set(
        document.tags
    )
    assert not any(name.startswith("on") for name, _ in document.attributes)
    assert "&lt;script&gt;" in content and hostile not in content
    assert set(document.links) == {
        "report.json",
        "inventory.csv",
        "hosts.txt",
        "alive.txt",
        "down_observed.txt",
        "intermittent.txt",
    }
    assert all((report.parent / link).is_file() for link in document.links)
    assert "Content-Security-Policy" in content
    assert "default-src 'none'" in content
    assert 'class="state unknown"' in content


def test_empty_html_and_missing_observations_are_explicit(tmp_path):
    with Inventory(tmp_path / "i.db") as store:
        content = render_html(store.report("example.com"))
    assert "No hosts stored" in content and "No provider audit entries" in content
    assert "None observed" in content and "not proof" in content


def test_html_preserves_every_host_and_labels_evidence_preview(tmp_path):
    with Inventory(tmp_path / "i.db") as store:
        store.merge(
            "example.com",
            DiscoveryResult(
                "wayback",
                [
                    {"hostname": "a.example.com", "url": f"https://a.example.com/entry-{i:04}-end"}
                    for i in range(25)
                ]
                + [{"hostname": "b.example.com"}],
            ),
        )
        report = store.report("example.com")
        content = render_html(report)
        evidence = report["assets"][0]["evidence"]
    assert "a.example.com" in content and "b.example.com" in content
    assert "Evidence (25 records)" in content and "first 20 evidence records" in content
    assert evidence[0]["url"] in content and evidence[24]["url"] not in content


def test_html_failure_does_not_mark_bundle_complete(monkeypatch, tmp_path):
    import pytest

    def fail(*args):
        raise OSError("synthetic write failure")

    monkeypatch.setattr("src.inventory.render_html", fail)
    with Inventory(tmp_path / "i.db") as store, pytest.raises(OSError):
        store.export("example.com", tmp_path)
    assert not list(tmp_path.rglob("report.json"))
