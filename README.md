# jht — Job Hunting Toolkit

Automated job scraping → resume matching → recruiter email discovery → LLM email drafting → Gmail send pipeline with a Next.js dashboard.

## Architecture

```
4:30 AM  →  Scrape jobs (LinkedIn, Indeed, Dice, ZipRecruiter, BuiltIn, Wellfound, career pages)
4:40 AM  →  Filter & score (embeddings + skill overlap + rejection rules)
4:45 AM  →  Find recruiter emails (Apollo, Hunter, Clearbit, SMTP verify, pattern guess)
4:50 AM  →  Draft emails (OpenAI LLM / fallback template)
5:00 AM  →  Send emails + follow-ups (Gmail API, resume attached)
```

## Quick Start

### 1. Backend

```bash
cd /workspaces/jht
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install

# Copy and fill env
cp backend/.env.example backend/.env
# Edit backend/.env with your keys

# Run API server
uvicorn backend.app.main:app --reload
```

### 2. Frontend (Next.js Dashboard)

```bash
cd frontend
npm install
npm run dev    # http://localhost:3001
```

### 3. Gmail OAuth Setup (one-time)

```bash
# Download client_secret.json from Google Cloud Console
export GMAIL_CLIENT_SECRETS_PATH=./client_secret.json
python -m backend.app.gmail_oauth_setup
# Sets GMAIL_CREDENTIALS_PATH to the generated token
```

### 4. Daily Pipeline (cron)

```bash
# Manual run:
python -m backend.app.pipeline

# Cron (edit with crontab -e):
30 4 * * * cd /workspaces/jht && ./scripts/run_daily.sh >> logs/pipeline.log 2>&1
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/jobs` | List all jobs |
| GET | `/stats` | Dashboard stats |
| POST | `/scrape` | Run scraper pipeline |
| POST | `/jobs/{id}/send` | Draft & send email for a job |
| POST | `/jobs/{id}/followup` | Send follow-up email |

## Environment Variables

See `backend/.env.example` for the full list. Key ones:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL or SQLite connection string |
| `RESUME_PATH` | Path to your resume (PDF or TXT) |
| `OPENAI_API_KEY` | OpenAI key for embeddings + LLM drafts |
| `GMAIL_CREDENTIALS_PATH` | Path to Gmail OAuth token |
| `APOLLO_API_KEY` | Apollo.io key for recruiter discovery |
| `HUNTER_API_KEY` | Hunter.io key for email verification |
| `CLEARBIT_KEY` | Clearbit key for enrichment |
| `PORTFOLIO_URL` | Portfolio link appended to emails |
| `SEND_MATCH_THRESHOLD` | Min match score to auto-send (default: 50) |
| `MAX_EMAILS_PER_DAY` | Rate limit (default: 20) |
| `PLAYWRIGHT_PROXIES` | Comma-separated proxy URLs |
| `CAREER_PAGES_URLS` | Comma-separated company career page URLs |

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app + endpoints
    models.py            # SQLAlchemy models (Job, Resume)
    scraper.py           # Aggregator for all scrapers
    matcher.py           # Embeddings + rule-based matching
    email_finder.py      # Multi-source recruiter email finder
    email_draft.py       # LLM-powered email drafting
    emailer.py           # Send via Gmail
    gmail_sender.py      # Gmail API integration
    gmail_oauth_setup.py # Interactive OAuth flow
    resume_parser.py     # PDF + TXT resume parser
    pipeline.py          # Full daily pipeline runner
    followup.py          # Follow-up email logic
    apollo_client.py     # Apollo.io integration
    clearbit_client.py   # Clearbit integration
    smtp_verify.py       # SMTP ping verification
    scrapers/
      playwright_base.py # Playwright runner with retries + proxy rotation
      proxy_pool.py      # Proxy rotation pool
      linkedin.py        # LinkedIn scraper
      indeed.py          # Indeed scraper
      dice.py            # Dice scraper
      ziprecruiter.py    # ZipRecruiter scraper
      builtin.py         # BuiltIn.com scraper
      wellfound.py       # Wellfound scraper
      career_pages.py    # Generic career page scraper
    matching/
      embeddings.py      # OpenAI / fallback embeddings + cosine similarity
      cache.py           # Text-hash embedding cache
frontend/
  pages/index.js         # Next.js dashboard
scripts/
  run_daily.sh           # Cron wrapper
  cron.example           # Crontab reference
```
# jht