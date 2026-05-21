# Privacy & data handling (FinGuide)

## What stays on your machine

- Uploaded PDF/CSV files (processed in memory only; not written to disk by the app)
- Parsing, classification, forecasting, charts, and risk scoring (local `.pkl` models)
- Full transaction table in the UI session (with masked narrations in the Transactions tab)

## What may leave your machine

- **Advisor chat (optional):** If you set `GROQ_API_KEY`, questions and an **anonymized summary** are sent to [Groq](https://groq.com) for replies.
- The summary includes: transaction counts, income/expense/net totals, category totals, risk score, and forecast numbers.
- It does **not** include: raw narration lines, account numbers, file names, or merchant names from your statement.

## Session hygiene

- Chat history is cleared when you upload different files or click **Clear chat**.
- Closing the browser ends the Streamlit session; no statement archive is kept by default.

## Your responsibilities

- Keep `.env` and API keys private; do not commit them to git.
- Run `streamlit run app.py` locally for personal use, or protect any shared deployment with HTTPS and login.
- Review Groq’s terms and data policy for API usage.
