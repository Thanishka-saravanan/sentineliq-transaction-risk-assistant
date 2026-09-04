TRACK_ID=PS06

# SentinelIQ — Transaction Risk Investigation Assistant

SentinelIQ is a specialized investigation assistant built for a bank's fraud desk. It analyzes multi-month customer transaction histories against deterministic risk rules, establishes per-customer behavioral baselines, and leverages Google Gemini for grounded reasoning and structured investigation reporting.

The system is designed with a strict engineering boundary: **deterministic Python logic performs all numerical anomaly detection, baseline calculations, and rule evaluations, while Gemini performs reasoning, contextual explanation, uncertainty handling, and investigator-oriented reporting.**

SentinelIQ flags activity for review and explains the evidence. It **never claims that fraud has occurred**, preserving the final judgement for human fraud analysts. When routine account activity presents no risk signals, it decisively reports: **NO ATTENTION REQUIRED**.

---

## Architecture Overview

```
                   Transaction History (CSV / JSON)
                                |
                                v
               Customer Baseline Analysis Engine
         (Mean, Median, Usual Hours, Channels, Payees)
                                |
                                v
               Deterministic Risk Analysis Engine
         (R01: Large Transfers | R02: New Payee Burst | 
          R03: Odd-Hours      | R04: Pattern Deviation | 
          R05: Linked Transaction Chains)
                                |
                                v
                   Structured Evidence Findings
         (Txn IDs, Actual vs Baseline stats, Delta %, Rule IDs)
                                |
                                v
            Local Risk Policy & Rules Retrieval (RAG)
                                |
                                v
                Gemini Grounded Reasoning Engine
         (Structured JSON, Priority Assessment, Uncertainty)
                                |
                                v
       FastAPI Backend  <=======>  Professional Fraud Desk UI
```

---

## Core Features

- **Decisive First Finding**: Immediately signals `YES — Attention Required` or `NO — No Attention Required`.
- **Customer-Centric Baselines**: Calculates personalized behavioral baselines per customer rather than imposing naive global static rules.
- **Deterministic Risk Engine**:
  - **R01 (Unusually Large Transfer)**: Flags transactions exceeding personal historical median/average and high-value threshold deviations.
  - **R02 (New Payee Payment Burst)**: Catches multiple rapid payments to a newly encountered payee.
  - **R03 (Odd-Hours Activity)**: Evaluates high-risk time windows (e.g., 00:00–05:00) against the customer's established active hours.
  - **R04 (Customer Behavior Deviation)**: Multi-factor evaluation combining unusual amount, payee, channel, and frequency.
  - **R05 (Linked Transaction Pattern)**: Correlates related suspicious transactions into an investigation chain.
- **Auditable Evidence Chains**: Every finding includes exact transaction IDs, amounts, dates, channels, baseline comparisons, and triggered rule IDs.
- **Grounded AI Synthesis**: Uses Gemini with structured JSON output strictly grounded in deterministic evidence and local risk policy documents.
- **Zero Fraud Accusation Guarantee**: Maintains neutral, investigative language, highlights uncertainties, and designates human investigator next steps.
- **Fraud Desk Investigation UI**: Single-page dashboard with customer selector, interactive transaction explorer, visual baseline stats, evidence timeline, and investigator action recommendations.

---

## Deterministic Logic vs. Gemini Responsibilities

| Responsibility | Deterministic Engine (Python) | Gemini GenAI |
| :--- | :---: | :---: |
| Statistical baselines (mean, median, hours, channels) | **Yes** | No |
| Anomaly detection & threshold checks | **Yes** | No |
| Rule trigger evaluations (R01–R05) | **Yes** | No |
| Transaction linking & timeline grouping | **Yes** | No |
| Evidence compilation & delta calculations | **Yes** | No |
| Evidence synthesis & narrative explanation | No | **Yes** |
| Policy grounding & rule context interpretation | No | **Yes** |
| Prioritizing what to investigate first | Guided | **Yes** |
| Identifying investigative uncertainties | No | **Yes** |
| Formulating recommended investigator next steps | No | **Yes** |

---

## Risk Rules Summary

- **R01 — Unusually Large Transfer**: Flags transfers materially exceeding customer historical median and average.
- **R02 — New Payee Payment Burst**: Flags rapid successive payments to an unfamiliar payee.
- **R03 — Odd-Hours Activity**: Flags transactions during high-risk windows (00:00–05:00) deviating from personal active hours.
- **R04 — Customer Behaviour Deviation**: Detects compound anomalies in channel, amount, frequency, and beneficiary.
- **R05 — Linked Transaction Pattern**: Connects multi-transaction events (e.g., test transaction followed by large outflow).

---

## Dataset Description

SentinelIQ includes synthetic datasets modeled on realistic retail banking customer patterns:

1. **Customer 1 (Routine Activity)**: Regular daytime expenses, utility bills, salary credits. *(Expected: NO ATTENTION REQUIRED)*
2. **Customer 2 (Large Transfer Anomaly)**: Consistent low-value transactions followed by an unprecedented large transfer. *(Expected: R01)*
3. **Customer 3 (New Payee Burst)**: Rapid successive transfers to an unseen beneficiary within a 2-hour window. *(Expected: R02)*
4. **Customer 4 (Odd-Hours Activity)**: Customer with exclusively business-hours activity making late-night transactions at 03:30 AM. *(Expected: R03)*
5. **Customer 5 (Complex Linked Pattern)**: Rapid-fire micro-burst to a new payee followed by an off-hours spike. *(Expected: R02, R03, R05)*
6. **Customer 6 (Ambiguous / Borderline Case)**: Slightly elevated holiday spending, borderline deviation, requiring human investigator nuance without premature alarm.

---

## Quickstart & Running the Application

### Prerequisites
- Python 3.11+
- Google Gemini API Key

### Installation

```bash
# Clone and navigate to project root
cd sentineliq

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Set your Gemini API key in your terminal or create a `.env` file:

```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your-gemini-api-key-here"

# Linux / macOS
export GEMINI_API_KEY="your-gemini-api-key-here"
```

> **Note:** If `GEMINI_API_KEY` is not provided, SentinelIQ will still execute full deterministic risk analysis and baseline calculations, surfacing a clear UI alert indicating that AI narrative synthesis is paused.

### Startup

Start the application with a single command:

```bash
python app.py
```

The application will start automatically and be available at:

**http://localhost:8000**

---

## API Endpoints

- `GET /api/health` — Application health check and status
- `GET /` — SentinelIQ fraud desk investigation web interface
- `GET /api/customers` — List available customer profiles and test scenarios
- `GET /api/customers/{customer_id}` — Customer details and metadata
- `GET /api/customers/{customer_id}/transactions` — Historical transactions for customer
- `POST /api/investigate/{customer_id}` — Run deterministic analysis, retrieval, and grounded AI investigation
- `GET /api/rules` — View local risk policy rules (R01–R05)

---

## Test Scenarios & Automated Testing

Run the test suite to verify all baseline calculations, rule engines, and scenarios:

```bash
pytest tests/
```

---

## Known Limitations

- Real-time streaming webhook ingestion is simulated via preloaded transaction files.
- Embedding indexes for local risk rules are generated locally using Gemini embeddings or local vector cosine similarity.
- Multi-currency conversions assume a unified standard base currency (USD/EUR/GBP/INR) per customer.

---

## Demo Video Placeholder

> **Demo Walkthrough Video**: `[Link to Demo Video Placeholder]`
