import os
from typing import List
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.baseline import (
    build_customer_baseline,
    build_baseline_summary,
)
from src.data_loader import (
    load_all_customers,
    load_customer_by_id,
    load_transactions_for_customer,
    load_risk_rules,
)
from src.models import (
    Customer,
    CustomerBaseline,
    CustomerBaselineSummary,
    CustomerRiskAnalysis,
    RiskFinding,
    RiskRuleDefinition,
    Transaction,
)
from src.risk_engine import analyze_customer_risk

app = FastAPI(
    title="SentinelIQ — Transaction Risk Investigation Assistant",
    description="Fraud desk investigation assistant (Banking Track: PS06)",
    version="1.0.0",
)

# Mount static directory if it exists
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_homepage():
    """Serves the SentinelIQ dashboard homepage."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "project": "SentinelIQ",
        "track_id": "PS06",
        "status": "online",
        "message": "SentinelIQ API is running."
    }


@app.get("/api/health")
async def health_check():
    """Application health and readiness check."""
    return {
        "status": "healthy",
        "project": "SentinelIQ",
        "track_id": "PS06",
        "version": "1.0.0",
        "gemini_api_key_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.get("/api/customers", response_model=List[Customer])
async def get_customers():
    """Returns all available customer investigation profiles."""
    try:
        return load_all_customers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load customers: {str(e)}")


@app.get("/api/customers/{customer_id}", response_model=Customer)
async def get_customer(customer_id: str):
    """Returns profile details for a specific customer."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    return customer


@app.get("/api/customers/{customer_id}/transactions", response_model=List[Transaction])
async def get_customer_transactions(customer_id: str):
    """Returns all historical transactions for a customer, sorted chronologically."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    return load_transactions_for_customer(customer_id)


@app.get("/api/rules", response_model=List[RiskRuleDefinition])
async def get_risk_rules():
    """Returns the operational fraud desk risk rules (R01 through R05)."""
    try:
        return load_risk_rules()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load risk rules: {str(e)}")


@app.get("/api/customers/{customer_id}/baseline", response_model=CustomerBaseline)
async def get_customer_baseline(customer_id: str):
    """Returns the complete statistical behavioral baseline for a specific customer."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    transactions = load_transactions_for_customer(customer_id)
    return build_customer_baseline(transactions, customer_id=customer.customer_id)


@app.get("/api/customers/{customer_id}/baseline/summary", response_model=CustomerBaselineSummary)
async def get_customer_baseline_summary(customer_id: str):
    """Returns a concise human-readable behavioral baseline summary for a customer."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    transactions = load_transactions_for_customer(customer_id)
    baseline = build_customer_baseline(transactions, customer_id=customer.customer_id)
    return build_baseline_summary(baseline)


@app.get("/api/customers/{customer_id}/risk-analysis", response_model=CustomerRiskAnalysis)
async def get_customer_risk_analysis(customer_id: str):
    """Runs deterministic risk evaluation against customer history and returns structured findings."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    transactions = load_transactions_for_customer(customer_id)
    return analyze_customer_risk(
        customer_id=customer.customer_id,
        transactions=transactions,
        customer_name=customer.name,
    )


@app.get("/api/customers/{customer_id}/findings", response_model=List[RiskFinding])
async def get_customer_findings(customer_id: str):
    """Returns the list of triggered risk findings for a specific customer."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    transactions = load_transactions_for_customer(customer_id)
    analysis = analyze_customer_risk(
        customer_id=customer.customer_id,
        transactions=transactions,
        customer_name=customer.name,
    )
    return analysis.findings


@app.get("/api/customers/{customer_id}/findings/{finding_id}", response_model=RiskFinding)
async def get_customer_finding_by_id(customer_id: str, finding_id: str):
    """Returns a specific risk finding for a customer."""
    customer = load_customer_by_id(customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer '{customer_id}' not found. Available IDs: CUST001 to CUST006."
        )
    transactions = load_transactions_for_customer(customer_id)
    analysis = analyze_customer_risk(
        customer_id=customer.customer_id,
        transactions=transactions,
        customer_name=customer.name,
    )
    for finding in analysis.findings:
        if finding.finding_id == finding_id:
            return finding
    raise HTTPException(
        status_code=404,
        detail=f"Finding '{finding_id}' not found for customer '{customer_id}'."
    )


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
