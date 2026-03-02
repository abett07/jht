import logging
from .scrapers.linkedin import scrape_linkedin_jobs
from .scrapers.indeed import scrape_indeed_jobs
from .scrapers.dice import scrape_dice_jobs
from .scrapers.ziprecruiter import scrape_ziprecruiter_jobs
from .scrapers.builtin import scrape_builtin_jobs
from .scrapers.wellfound import scrape_wellfound_jobs
from .scrapers.career_pages import scrape_career_pages

logger = logging.getLogger(__name__)

# Registry of all scrapers: (name, callable)
_SCRAPERS = [
    ("linkedin", scrape_linkedin_jobs),
    ("indeed", scrape_indeed_jobs),
    ("dice", scrape_dice_jobs),
    ("ziprecruiter", scrape_ziprecruiter_jobs),
    ("builtin", scrape_builtin_jobs),
    ("wellfound", scrape_wellfound_jobs),
]


def scrape_jobs(query: str = "DFIR OKTA", location: str = "", limit: int = 10, proxy: str | None = None):
    """Run all registered scrapers + career pages and aggregate results.

    Returns deduplicated list of job dicts.
    """
    results = []

    for name, fn in _SCRAPERS:
        try:
            logger.info("Running scraper: %s", name)
            items = fn(query, location, limit=limit, proxy=proxy)
            logger.info("  %s returned %d results", name, len(items))
            results.extend(items)
        except Exception as e:
            logger.warning("Scraper %s failed: %s", name, e)

    # career pages (configured via env)
    try:
        career = scrape_career_pages(limit=limit, proxy=proxy)
        logger.info("Career pages returned %d results", len(career))
        results.extend(career)
    except Exception as e:
        logger.warning("Career pages scraper failed: %s", e)

    # dedupe by URL or title+company
    seen = set()
    deduped = []
    for r in results:
        key = (r.get("url") or "") or (r.get("title", "") + "||" + r.get("company", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    logger.info("Total deduplicated results: %d", len(deduped))
    return deduped
