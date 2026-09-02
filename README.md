# Retail-Pulse

A fixed-price monthly sales & inventory dashboard for small Indian
retailers. This is the actual product being sold - separate from
`ai_business_platform`, which is the business-management/guardrail
tooling used to research, spec, and draft outreach for it.

## What this MVP does

- Retailer signs up, logs in (own account, own data - basic multi-tenant)
- Uploads a weekly CSV export (see `sample_data/sample_upload.csv` for
  the expected format)
- CSV is validated before anything is written (row count, required
  columns, date parsing) - a rejected file shows why, not a silent failure
- Dashboard shows: top sellers (7 days), reorder alerts, stale stock
  (30+ days unsold), and a suggested next-order quantity (a simple,
  explainable heuristic - not AI forecasting)

## Deliberately NOT in this MVP (fast-follows, not missing-by-accident)

- POS-specific parsers for Shopify/Square/Lightspeed/Retail Pro - one
  generic CSV format for now. Build a real parser once an actual
  customer's actual export format is in hand, not before.
- SLA commitments, support ticketing, quarterly review calls - these
  are service/business promises, not software, and are premature before
  there's one paying customer.
- Multiple viewer accounts per shop (spec allowed 3) - single account
  per shop for now.

## Running locally

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Visit http://127.0.0.1:8000

## Known limitation before relying on this for a real paying customer

SQLite on most free hosting tiers (including Render's free web service)
is **not persistent across redeploys** unless a paid persistent disk is
attached. Fine for demoing and early validation; before onboarding a
real paying customer whose data must survive a redeploy, either attach
a persistent disk or move to a managed Postgres (Render has a free
Postgres tier with its own limits - check current terms before relying
on it).

## Deploying (Render, free tier)

1. Push this repo to GitHub.
2. On render.com, "New +" → "Blueprint" → connect the repo (uses `render.yaml`).
3. Render builds the Dockerfile and assigns a public URL automatically.
