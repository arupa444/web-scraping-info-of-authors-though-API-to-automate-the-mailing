"""The email scraper has been removed; guard against it creeping back."""

import importlib

from icereach.main import app


def test_no_scrape_routes():
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert not any("scrape" in p.lower() for p in paths)


def test_pubmed_scraper_not_importable():
    # No module in the platform package should expose the old PubMed scraper.
    for mod in ("icereach.main", "icereach.services.sender", "icereach.routers.campaigns"):
        m = importlib.import_module(mod)
        assert not hasattr(m, "search_pubmed_authors_with_emails_scrape")
        assert not hasattr(m, "process_batch")
