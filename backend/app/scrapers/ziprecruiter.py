"""ZipRecruiter Playwright scraper."""
from urllib.parse import quote_plus
from .playwright_base import PlaywrightRunner


def scrape_ziprecruiter_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape job listings from ZipRecruiter.

    Returns list of dicts: {title, company, location, description, url}
    """
    q = quote_plus(query)
    url = f"https://www.ziprecruiter.com/jobs-search?search={q}"
    if location:
        url += f"&location={quote_plus(location)}"

    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)

        try:
            page.wait_for_selector("article.job_result, .job_content, a.job_link", timeout=12000)
            cards = page.query_selector_all("article.job_result") or page.query_selector_all(".job_content")
        except Exception:
            cards = []

        for card in cards[:limit]:
            try:
                title_el = card.query_selector("h2.job_title a") or card.query_selector("a.job_link") or card.query_selector("span.title")
                company_el = card.query_selector("a.company_name") or card.query_selector("span.company")
                loc_el = card.query_selector("span.location") or card.query_selector("p.location")
                snippet_el = card.query_selector("p.job_snippet") or card.query_selector("span.snippet")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location_text = loc_el.inner_text().strip() if loc_el else ""
                snippet = snippet_el.inner_text().strip() if snippet_el else ""
                link = title_el.get_attribute("href") if title_el else None

                if title:
                    results.append({
                        "title": title,
                        "company": company,
                        "location": location_text,
                        "description": snippet,
                        "url": link,
                    })
            except Exception:
                continue

    return results
