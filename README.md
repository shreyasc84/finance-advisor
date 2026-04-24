# AI-Powered Personal Finance Advisor

This project parses Indian bank statements (PDF/CSV), runs ML models for:
- transaction categorization
- cash flow forecasting
- risk profiling

And provides an interactive advisor chat (LangChain + Groq) with model-aware context.

## Features

- Statement upload (`.pdf`, `.csv`) in a Streamlit UI
- PDF table parsing for bank statement transaction rows
- Transaction classification using `models/transaction_classifier.pkl`
- Monthly forecast using `models/cashflow_forecasters.pkl`
- Risk profile scoring (Low/Medium/High)
- Financial advisor chat grounded in parsed + model output context

## Project Structure

- `app.py` - main Streamlit app
- `data/` - datasets and synthetic templates
- `models/` - trained `.pkl` models
- `transaction_categorization.ipynb` - classification training notebook
- `expense_forecasting.ipynb` - cash flow forecasting notebook
- `scripts/generate_synthetic_transaction_templates.py` - synthetic template generator
- `requirements.txt` - dependencies

## Setup (Linux / macOS / Windows)

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Windows (Command Prompt)

```bat
py -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
```

> `setup.sh` is a Unix shell script, so use it on Linux/macOS.  
> On Windows, use the commands above.

## Environment Variables

Create `.env` from `.env.example`:

### Linux / macOS

```bash
cp .env.example .env
```

### Windows (PowerShell)

```powershell
Copy-Item .env.example .env
```

### Windows (Command Prompt)

```bat
copy .env.example .env
```

Then set:

- `GROQ_API_KEY` - your Groq API key
- `GROQ_MODEL` - optional (default: `llama-3.3-70b-versatile`)

## Run the App

### Linux / macOS

```bash
source .venv/bin/activate
streamlit run app.py
```

### Windows (PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

### Windows (Command Prompt)

```bat
.\.venv\Scripts\activate.bat
streamlit run app.py
```

## Train / Refresh Models

1. Open and run:
   - `transaction_categorization.ipynb`
   - `expense_forecasting.ipynb`
2. Ensure generated model files are present in `models/`:
   - `transaction_classifier.pkl`
   - `cashflow_forecasters.pkl`

## Synthetic Data Augmentation

To generate additional diverse transaction templates:

```bash
python scripts/generate_synthetic_transaction_templates.py
```

This writes:

- `data/financial_transaction_synthetic_templates.csv`

## Notes

- Forecast quality improves with longer monthly history.
- Grouped template-safe evaluation is the realistic metric for unseen transaction wording.
- Chat advice is model-context driven and should be used for guidance, not guaranteed outcomes.
