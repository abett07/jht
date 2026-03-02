"""BuiltIn.com Playwright + BeautifulSoup scraper."""
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .playwright_base import PlaywrightRunner


def scrape_builtin_jobs(query: str, location: str = "", limit: int = 10, proxy: str | None = None):
    """Scrape job listings from BuiltIn.com.

    Uses Playwright to render JS then BeautifulSoup for parsing.
    Returns list of dicts: {title, company, location, description, url}
    """
    q = quote_plus(query)
    url = f"https://builtin.com/jobs?search={q}"
    if location:
        url += f"&location={quote_plus(location)}"

    results = []
    with PlaywrightRunner(proxy=proxy, headless=True) as runner:
        page = runner.new_page()
        page.goto(url, timeout=60000)

        # let JS render
        try:
            page.wait_for_selector("[data-id='job-card'], .job-card, .job-result", timeout=12000)
        except Exception:
            pass

        html = page.content()

    soup = BeautifulSoup(html, "html.parser")

    # BuiltIn uses various card selectors; try common patterns
    cards = soup.select("[data-id='job-card']") or soup.select(".job-card") or soup.select("div.job-result")

    for card in cards[:limit]:
        try:
            title_el = card.select_one("h2 a") or card.select_one("a.job-title") or card.select_one("h3 a")
            company_el = card.select_one("span.company-name") or card.select_one("div.company-title")
            loc_el = card.select_one("span.job-location") or card.select_one("div.location")

            title = title_el.get_text(strip=True) if title_el else ""
            company = company_el.get_text(strip=True) if company_el else ""
            location_text = loc_el.get_text(strip=True) if loc_el else ""
            link = title_el.get("href") if title_el else None
            url_link = f"https://builtin.com{link}" if link and link.startswith("/") else link

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
