from urllib.parse import quote_plus
from .playwright_base import PlaywrightRunner


def scrape_linkedin_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape basic job metadata from LinkedIn search results.

    Note: LinkedIn aggressively protects scraping. This is a best-effort scaffold — adapt selectors
    and add login / session handling as needed.
    Returns list of dicts with keys: title, company, location, description, url
    """
    url = f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(query)}&location={quote_plus(location)}"
    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)
        # wait for results list
        try:
            page.wait_for_selector("ul.jobs-search__results-list li", timeout=10000)
            cards = page.query_selector_all("ul.jobs-search__results-list li")
        except Exception:
            cards = []

        for card in cards[:limit]:
            try:
                title_el = card.query_selector("h3")
                company_el = card.query_selector("h4")
                loc_el = card.query_selector(".job-search-card__location") or card.query_selector("span.job-result-card__location")
                link_el = card.query_selector("a")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location_text = loc_el.inner_text().strip() if loc_el else ""
                url_link = link_el.get_attribute("href") if link_el else None

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
