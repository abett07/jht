"""Wellfound (formerly AngelList Talent) Playwright scraper."""
from urllib.parse import quote_plus
from .playwright_base import PlaywrightRunner


def scrape_wellfound_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape job listings from Wellfound.

    Returns list of dicts: {title, company, location, description, url}
    """
    q = quote_plus(query)
    url = f"https://wellfound.com/jobs?query={q}"

    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)

        try:
            page.wait_for_selector("div[class*='jobListing'], div[class*='styles_result'], a[class*='job']", timeout=12000)
            cards = page.query_selector_all("div[class*='jobListing']") or page.query_selector_all("div[class*='styles_result']")
        except Exception:
            cards = []

        for card in cards[:limit]:
            try:
                title_el = card.query_selector("a[class*='jobTitle']") or card.query_selector("h4") or card.query_selector("a")
                company_el = card.query_selector("a[class*='company']") or card.query_selector("h5") or card.query_selector("span[class*='company']")
                loc_el = card.query_selector("span[class*='location']") or card.query_selector("span[class*='Location']")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location_text = loc_el.inner_text().strip() if loc_el else ""
                link = title_el.get_attribute("href") if title_el else None
                url_link = f"https://wellfound.com{link}" if link and link.startswith("/") else link

                if title:
                    results.append({
                        "title": title,
                        "company": company,
                        "location": location_text,
                        "description": "",
                        "url": url_link,
                    })
            except Exception:
                continue

    return results
