"""Generic company career-page scraper using Playwright + BeautifulSoup.

Configure target URLs via CAREER_PAGES_URLS env (comma-separated) or pass directly.
"""
import os
import re
from typing import List
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightRunner


# heuristic keywords that commonly appear in job-listing links/text
_JOB_LINK_PATTERNS = re.compile(
    r"(career|job|position|opening|vacancy|apply|hiring)", re.IGNORECASE
)


def scrape_career_page(url: str, limit: int = 20, proxy: str | None = None) -> list:
    """Scrape a single company career page for job links.

    Returns list of dicts: {title, company, location, description, url}
    """
    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        html = page.content()

    soup = BeautifulSoup(html, "html.parser")

    # Strategy: find all <a> tags whose text or href matches job-like patterns
    links = soup.find_all("a", href=True)
    seen = set()
    for a in links:
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or len(text) < 5:
            continue
        # check if link or text looks job-related
        if not _JOB_LINK_PATTERNS.search(href) and not _JOB_LINK_PATTERNS.search(text):
            continue
        if text in seen:
            continue
        seen.add(text)

        # normalize url
        if href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            href = f"{parsed.scheme}://{parsed.netloc}{href}"

        results.append({
            "title": text,
            "company": "",  # could be inferred from domain
            "location": "",
            "description": "",
            "url": href,
        })
        if len(results) >= limit:
            break

    return results


def scrape_career_pages(urls: List[str] | None = None, limit: int = 20, proxy: str | None = None) -> list:
    """Scrape multiple career pages. Falls back to CAREER_PAGES_URLS env."""
    if urls is None:
        raw = os.getenv("CAREER_PAGES_URLS", "")
        urls = [u.strip() for u in raw.split(",") if u.strip()]

    all_results = []
    for u in urls:
        try:
            all_results.extend(scrape_career_page(u, limit=limit, proxy=proxy))
        except Exception:
            continue
    return all_results
