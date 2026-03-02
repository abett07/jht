from urllib.parse import quote_plus
from .playwright_base import PlaywrightRunner


def scrape_indeed_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape basic job metadata from Indeed search results.

    Returns list of dicts with keys: title, company, location, description, url
    """
    q = quote_plus(query)
    l = quote_plus(location)
    url = f"https://www.indeed.com/jobs?q={q}&l={l}"
    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)
        try:
            page.wait_for_selector("a.tapItem", timeout=10000)
            cards = page.query_selector_all("a.tapItem")
        except Exception:
            cards = []

        for card in cards[:limit]:
            try:
                title_el = card.query_selector("h2") or card.query_selector("h1")
                company_el = card.query_selector("span.companyName")
                loc_el = card.query_selector("div.companyLocation")
                link = card.get_attribute("href")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location_text = loc_el.inner_text().strip() if loc_el else ""
                url_link = f"https://www.indeed.com{link}" if link and link.startswith("/") else link

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
