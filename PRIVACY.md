# Privacy & data handling (FinGuide)

FinGuide is a Streamlit web app. When you use the **hosted deployment** (for example on [Streamlit Community Cloud](https://streamlit.io/cloud)), your browser talks to Streamlit’s servers where the app runs. This policy describes what happens to your data in that setup. If you run the app yourself (`streamlit run app.py` on your own machine or server), the same processing steps apply, but data stays on infrastructure you control.

## Who processes your data

| Party | Role |
|--------|------|
| **Streamlit hosting** | Runs the app, holds your **session** in server memory while you use the page, serves the UI over HTTPS. |
| **FinGuide (this app)** | Parses uploads, runs ML models, builds charts, risk score, and optional PDF export. Does **not** write your statement to the app’s filesystem by default. |
| **Groq (optional)** | Powers **Advisor** chat only if `GROQ_API_KEY` is configured. Receives your questions plus an **anonymized summary** (see below). |

We do not operate a separate FinGuide database or user accounts. There is no sign-up flow inside the app.

## What you upload

- Bank statement **PDF** or **CSV** files, via the sidebar uploader.
- Files are read into **server memory** for the current Streamlit session. The app does not save them to disk, object storage, or a database as part of normal operation.
- Parsing, classification, forecasting, charts, risk scoring, and PDF generation all use that in-memory data on the host where Streamlit runs.

## What we show in the UI

- The **Transactions** tab displays narrations with **masking** (long numbers, refs, emails partially hidden) for safer viewing.
- Full narration text may still exist in session memory for parsing and ML; it is not sent to Groq in bulk.

## What leaves the hosting environment

### Advisor chat (optional)

If the deployer sets `GROQ_API_KEY` (locally in `.env` or in **Streamlit secrets** for Cloud):

- Your **chat messages** and an **anonymized summary** are sent to [Groq](https://groq.com) for replies.
- The summary includes: transaction counts, income/expense/net totals, category totals, risk score, forecast numbers, and high-level risk reasons.
- It does **not** include: raw narration lines, account numbers, uploaded file names, or merchant names from your statement.

Review Groq’s terms and privacy policy for API usage.

### What we do not send to Groq

- Your PDF/CSV files
- Row-by-row transaction narrations
- Account numbers from statements

### Streamlit platform

Streamlit’s own logging, analytics, and infrastructure policies apply to traffic to the hosted app. See [Streamlit’s privacy documentation](https://docs.streamlit.io) and your deployment settings on Community Cloud.

## Session lifecycle

- Data lives in the **active session** while you keep the app open. Refreshing or closing the tab typically ends the session; FinGuide does not keep a statement archive after that.
- **Advisor** chat history is cleared when you upload different files or click **Clear chat**.
- Each visitor gets an isolated session; we do not merge sessions between users.

## Security practices in the app

- **Aggregates-only** context for the LLM (`build_advisor_context` in code).
- **Redaction** helpers for sensitive patterns in displayed narrations.
- **No default persistence** of uploads or chat to disk.
- Deployments should use **HTTPS** (provided on Streamlit Cloud) and store API keys in **Streamlit secrets**, not in public repos.

## Your responsibilities

- Upload only statements you are allowed to use. Do not upload other people’s data without permission.
- Do not commit `.env`, `secrets.toml`, or API keys to git.
- On Streamlit Cloud, set `GROQ_API_KEY` in the app’s **Secrets** in the dashboard, not in source code.
- Treat the hosted URL as **sensitive** if the app is public: anyone with the link can upload data to a session on that deployment.
- For stricter control, run a private deployment (access-controlled Streamlit app or self-hosted instance).

## Data retention

- **FinGuide:** No long-term retention of statements or chat in application code.
- **Groq:** Retention and processing are governed by Groq’s policies when Advisor is used.
- **Streamlit:** May retain logs or metadata per their platform rules; check Streamlit Cloud settings and docs.

## Changes

This policy may be updated as deployment or features change. The in-app **Privacy & data** expander shows a short summary; this file is the full reference.

## Contact

For privacy questions about a specific deployment, contact the person or team who published that Streamlit app URL.
