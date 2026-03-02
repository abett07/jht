"""Dice.com Playwright scraper."""
from urllib.parse import quote_plus
from .playwright_base import PlaywrightRunner


def scrape_dice_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape job listings from Dice.com.

    Returns list of dicts: {title, company, location, description, url}
    """
    q = quote_plus(query)
    url = f"https://www.dice.com/jobs?q={q}"
    if location:
        url += f"&location={quote_plus(location)}"

    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)

        # Dice uses a custom web-component based card list
        try:
            page.wait_for_selector("dhi-search-card", timeout=12000)
            cards = page.query_selector_all("dhi-search-card")
        except Exception:
            # fallback selectors
            try:
                page.wait_for_selector("a[data-cy='card-title-link']", timeout=8000)
                cards = page.query_selector_all(".card-body, .search-card")
            except Exception:
                cards = []

        for card in cards[:limit]:
            try:
                title_el = card.query_selector("a[data-cy='card-title-link']") or card.query_selector("h5 a") or card.query_selector("a.card-title-link")
                company_el = card.query_selector("a[data-cy='search-result-company-name']") or card.query_selector("span.company")
                loc_el = card.query_selector("span[data-cy='search-result-location']") or card.query_selector("span.location")

                title = title_el.inner_text().strip() if title_el else ""
                company = company_el.inner_text().strip() if company_el else ""
                location_text = loc_el.inner_text().strip() if loc_el else ""
                link = title_el.get_attribute("href") if title_el else None
                url_link = f"https://www.dice.com{link}" if link and link.startswith("/") else link

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
