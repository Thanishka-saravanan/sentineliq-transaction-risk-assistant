TRACK_ID=PS06

# SentinelIQ — Transaction Risk Investigation Assistant

SentinelIQ is a specialized, production-style investigation assistant built for a bank's fraud desk (Banking Track: **PS06**). It analyzes multi-month customer transaction histories against deterministic risk policies, establishes personalized behavioral baselines, and leverages Google Gemini as an auditable, grounded investigation copilot.

The system is built on a strict, defense-grade engineering boundary: **deterministic Python logic performs all numerical anomaly detection, mathematical baselines, and policy evaluations, while Gemini performs reasoning, plain-language synthesis, uncertainty calibration, and investigator action planning.**

SentinelIQ assists fraud analysts by surfacing actionable evidence. It **never claims that fraud has occurred**, ensuring that final determinations remain strictly human-in-the-loop. When routine account activity exhibits no risk signals, it decisively reports: **NO ATTENTION REQUIRED**.

---

## The Banking Problem (PS06)

Fraud desks face thousands of daily alerts, leading to investigator fatigue, high false-positive rates, and missed multi-stage attacks. Generic static rules (e.g., blanket amount thresholds) flag legitimate customer purchases while missing subtle behavioral shifts. Conversely, ungrounded GenAI solutions hallucinate transaction amounts, invent phantom account numbers, and prematurely declare fraud.

**SentinelIQ solves this through:**
1. **Personalized Behavioral Baselines**: Every transaction is evaluated against the customer's *own* historical spending distributions, active hours, and frequent payees rather than naive population averages.
2. **Deterministic Risk Policies (R01–R05)**: Mathematical detection of large transfers, payment bursts, off-hours anomalies, compounding behavioral shifts, and linked attack chains.
3. **Grounded GenAI Synthesis**: Gemini generates structured investigation briefs strictly from pre-computed deterministic evidence and policy rules, enforcing zero fabrication.
4. **Human-in-the-Loop Workflow**: Clear recommendations, customer interview questions, and mitigating factors empower human analysts to make informed decisions.

---

## Investigation Pipeline Architecture

```
                 Customer Transaction History (CSV / JSON)
                                     |
                                     v
                   Customer Behavioural Baseline Engine
            (Median, IQR Bounds, Active Hours, Channels, Payees)
                                     |
                                     v
                   Deterministic Risk Detection Engine
            ┌──────────────────────────────────────────────────┐
            │  R01: Unusually Large Transfer                   │
            │  R02: New Payee Payment Burst                    │
            │  R03: Odd-Hours Activity Anomaly                 │
            │  R04: Customer Behaviour Deviation               │
            │  R05: Linked Multi-Transaction Chain             │
            └──────────────────────────────────────────────────┘
                                     |
                                     v
                    Deterministic Evidence & Findings
            (Finding IDs, Metrics, Multipliers, Delta %, Txn IDs)
                                     |
                                     v
                   Transparent Grounding Context Builder
            (Customer Profile + Baseline Summary + Triggered Rules)
                                     |
                                     v
                  Grounded Gemini Investigation Copilot
            (Structured JSON, Assessment, Concerns, Mitigating Factors)
                                     |
                                     v
            FastAPI Backend  <═══════════════>  Investigation UI
                         (Port 8000 / Vanilla Web)
```

---

## Deterministic Logic vs. Gemini Copilot Responsibilities

| Responsibility | Deterministic Engine (Python) | Gemini Copilot (GenAI) |
| :--- | :---: | :---: |
| Statistical baseline calculation (IQR, median, active hours) | **Authoritative Source** | Reads only |
| Mathematical anomaly detection & threshold evaluations | **Authoritative Source** | Reads only |
| Risk rule evaluations (R01–R05) & scoring (0–100) | **Authoritative Source** | Reads only |
| Transaction linking & attack sequence grouping | **Authoritative Source** | Reads only |
| Evidence compilation & finding ID generation | **Authoritative Source** | Reads only |
| Plain-language investigation synthesis & narrative | Excluded | **Grounded Synthesis** |
| Policy rule context & rationale interpretation | Excluded | **Grounded Synthesis** |
| Identifying mitigating context (known payees, typical hours) | Feeds context | **Grounded Synthesis** |
| Formulating customer interview questions & next steps | Excluded | **Grounded Synthesis** |
| Overriding scores or inventing transaction data | **Strictly Forbidden** | **Strictly Forbidden** |

---

## Deterministic Risk Policies (R01–R05)

- **R01 — Unusually Large Transfer**: Flags transfers materially exceeding the customer's historical 1.5x IQR upper bound and personal median.
- **R02 — New Payee Payment Burst**: Detects rapid consecutive outbound transfers to an unfamiliar beneficiary within a short time window.
- **R03 — Odd-Hours Activity**: Identifies transactions occurring during nocturnal high-risk windows (00:00–05:00) deviating from the customer's historical active hours.
- **R04 — Customer Behaviour Deviation**: Detects compounding multi-factor shifts combining unusual amount, atypical channel, velocity, and unfamiliar payee.
- **R05 — Linked Transaction Pattern**: Correlates multi-stage attack signatures (e.g., nominal probing transfer followed by rapid drain transfers).

---

## Synthetic Customer Scenarios

SentinelIQ includes 6 realistic retail banking scenarios designed to stress-test every facet of the investigation workflow:

1. **CUST001 — Priya Sharma (Routine Control)**: Consistent daytime expenses, grocery shopping, utility bills. *(Expected: Score 0, 0 findings, NO ATTENTION REQUIRED)*
2. **CUST002 — Rajesh Verma (High-Value Transfer)**: Routine salary earner executing an unprecedented $24,500 NEFT transfer. *(Expected: R01, R04, Score 85)*
3. **CUST003 — Vikram Malhotra (New Payee Velocity Burst)**: Three rapid transfers totaling $4,800 to an unseen beneficiary within 2 hours. *(Expected: R02, Score 75)*
4. **CUST004 — Ananya Desai (Off-Hours Activity)**: Daytime-only account with sudden nocturnal IMPS transfers at 03:30 AM. *(Expected: R03, Score 70)*
5. **CUST005 — Sameer Khan (Linked Probing & Velocity Chain)**: A $1.00 probing transfer at 03:10 AM followed by four high-value IMPS transfers totaling $19,200 within 52 minutes. *(Expected: R05, R02, R03, Score 95)*
6. **CUST006 — Sunita Rao (Ambiguous Anomaly)**: A $3,200 retail purchase at Tanishq Jewellers breaching the numerical upper bound, but conducted during normal daytime hours at a known merchant. *(Expected: R01, Score 55 — Mitigating context identified)*

---

## Investigation Dashboard (Phase 6)

The single-page web dashboard is served directly by FastAPI via vanilla HTML, CSS, and modern JavaScript:
- **Zero Build Tools**: No Node.js, React, or npm required.
- **Real Backend APIs**: All data is dynamically queried; zero hardcoded responses.
- **Interactive Finding-to-Ledger Highlighting**: Clicking any finding card automatically scrolls to and pulses the linked transaction rows in the ledger.
- **On-Demand Copilot Generation**: Gemini synthesis is triggered on-demand via the "Generate Investigation" button with clear loading states and graceful error handling.

---

## API Endpoints Reference

All endpoints are fully implemented, schema-validated, and live:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Investigation Dashboard web application |
| `GET` | `/api/health` | Health, readiness, and API key presence check |
| `GET` | `/api/customers` | List all 6 customer profiles and scenarios |
| `GET` | `/api/customers/{customer_id}` | Get customer metadata by ID |
| `GET` | `/api/customers/{customer_id}/transactions` | Customer transaction ledger |
| `GET` | `/api/rules` | Auditable risk policy rules (R01–R05) |
| `GET` | `/api/customers/{customer_id}/baseline` | Full multi-profile behavioral baseline |
| `GET` | `/api/customers/{customer_id}/baseline/summary` | Condensed behavioral baseline metrics |
| `GET` | `/api/customers/{customer_id}/risk-analysis` | Deterministic risk analysis, scores, and findings |
| `GET` | `/api/customers/{customer_id}/findings` | All deterministic findings for customer |
| `GET` | `/api/customers/{customer_id}/findings/{finding_id}` | Detailed finding view by finding ID |
| `GET` | `/api/customers/{customer_id}/investigation/context` | Transparent grounding context sent to LLM |
| `GET` | `/api/customers/{customer_id}/investigation` | Grounded Gemini Copilot investigation report |

---

## Setup & Quickstart

### Prerequisites
- Python 3.11+
- Google Gemini API Key (optional for deterministic engine; required for GenAI copilot synthesis)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Thanishka-saravanan/sentineliq-transaction-risk-assistant.git
cd sentineliq-transaction-risk-assistant

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy the provided template and configure your environment:

```bash
# Copy template
cp .env.example .env
```

Edit `.env` or set environment variables in your terminal:

```env
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-3.6-flash
SSL_VERIFY=true
PORT=8000
```

> **Graceful Degradation Note:** If `GEMINI_API_KEY` is not provided, SentinelIQ remains 100% operational for baseline calculations, deterministic risk analysis, policy lookup, and transaction ledger exploration. The UI displays an informative alert when the investigation button is clicked.

### 3. Running the Application

```bash
python app.py
```

The application will start at: **http://localhost:8000** (or your configured `PORT`).

---

## Automated Test Suite

Run the complete automated test suite (69 offline unit & integration tests):

```bash
python -m unittest discover -s tests
```

To run the live endpoint verification script against a running server:

```bash
python -u scripts/verify_endpoints.py
```

---

## End-to-End Demo Flow (For Hackathon Judges)

1. **Launch Dashboard**: Open `http://localhost:8000`.
2. **Showcase Attack Chain (`CUST005 — Sameer Khan`)**:
   - Selected by default on load.
   - Observe the 4-step sequence callout: *Probe ($1.00) → Escalation ($4,500) → Rapid Burst ($9,700) → Drain ($5,000)*.
   - Click the **R05 Linked Pattern** finding card to view mathematical evidence and policy basis.
   - Click **"View & Highlight Linked Transactions"** to automatically scroll the ledger to rows `TXN0140`–`TXN0144`.
   - Click **"Generate Investigation"** to observe Gemini synthesizing the chain into an executive summary with concrete investigator questions and actions.
3. **Ambiguity Calibration (`CUST006 — Sunita Rao`)**:
   - Select `CUST006` from the sidebar.
   - Observe the amber alert: *"Policy threshold triggered — mitigating context identified"*.
   - Generate the investigation to see Gemini highlight mitigating factors (*known merchant, daylight hour, primary card channel*) and express appropriate investigative uncertainty rather than declaring fraud.
4. **Routine Account Baseline (`CUST001 — Priya Sharma`)**:
   - Select `CUST001` from the sidebar.
   - Observe the calm green state: *"No Deterministic Policy Findings — Routine Account Activity"*, Score: 0/100, Review: NOT REQUIRED.
   - Generate the investigation to verify the copilot decisively reports: **NO ATTENTION REQUIRED**.

---

## Regulatory Compliance & Safety Statement

> [!IMPORTANT]
> **Regulatory Notice**: The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred. All final account actions, freezes, and SAR filings remain strictly with licensed human fraud analysts.
