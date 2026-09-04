import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.investigation_context import build_grounding_context
from src.models import (
    FindingExplanation,
    GroundingContext,
    InvestigationAssessment,
    InvestigationResult,
)

logger = logging.getLogger("sentineliq.genai")

# Default model (can be overridden via GEMINI_MODEL env var)
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class GeminiNotConfiguredError(Exception):
    """Raised when GEMINI_API_KEY is not set or empty."""
    pass


class GeminiServiceError(Exception):
    """Raised when the Gemini API encounters an error or returns invalid output."""
    pass


SYSTEM_INSTRUCTION = """
You are an expert fraud desk investigation assistant for SentinelIQ (Banking Track: PS06).
Your role is to synthesize already-provided deterministic risk findings and customer baselines into a clear, professional investigation report for human fraud analysts.

CRITICAL OPERATING RULES:
1. STRICT GROUNDING: You must ONLY reason from the supplied evidence in the grounding context.
2. ZERO FABRICATION: Do NOT invent transaction IDs, monetary amounts, payees, dates, rules, or findings.
3. NEVER CLAIM FRAUD: You must NEVER state or conclude that fraud has occurred. A risk finding indicates activity requiring human review. Use objective, neutral language (e.g., "requires human review", "matches policy criteria", "deviates from customer baseline").
4. ZERO FINDINGS PROTOCOL: If the customer has zero deterministic findings (such as CUST001), state clearly: "NO ATTENTION REQUIRED". Do not manufacture or hallucinate suspicious activity.
5. AMBIGUOUS CASES: If an anomaly exists but mitigating context is present (such as CUST006 with an elevated amount to a known payee during normal daytime hours), explicitly highlight the mitigating factors and express appropriate investigative uncertainty.
6. PRESERVE IDENTIFIERS: You must reference exact finding IDs and rule IDs as provided in the context.

Produce your response as valid JSON matching the required schema.
"""


def get_gemini_client(client_override: Optional[Any] = None) -> Any:
    """
    Constructs and returns the official Google GenAI client.
    
    Raises GeminiNotConfiguredError if GEMINI_API_KEY is not set.
    """
    if client_override is not None:
        return client_override

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        raise GeminiNotConfiguredError(
            "Gemini investigation service is not configured. Set GEMINI_API_KEY to enable GenAI investigation synthesis."
        )

    try:
        import httpx
        from google import genai
        from google.genai import types

        # On Windows, configure client_args to prevent local root CA validation failures and set resilient connect/read timeouts
        http_options = types.HttpOptions(
            client_args={
                "verify": False,
                "timeout": httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0),
            }
        )
        client = genai.Client(api_key=api_key.strip(), http_options=http_options)
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Gemini Client: {e}")
        raise GeminiServiceError(f"Failed to initialize Gemini Client: {str(e)}")


def _sanitize_json_text(raw_text: str) -> str:
    """Extracts raw JSON text if enclosed in markdown code blocks."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def validate_and_sanitize_investigation_result(
    raw_dict: Dict[str, Any],
    context: GroundingContext,
) -> InvestigationResult:
    """
    Validates Gemini output against the deterministic source of truth.
    
    1. Ensures valid finding IDs and rule IDs exist in deterministic findings.
    2. Drops or sanitizes any hallucinated finding IDs or rule IDs.
    3. Preserves the mandatory regulatory disclaimer.
    """
    valid_findings_by_id = {f.finding_id: f for f in context.deterministic_findings}
    valid_rule_ids = {r.rule_id for r in context.relevant_policy_rules}

    # Process finding explanations
    validated_explanations: List[FindingExplanation] = []
    raw_explanations = raw_dict.get("finding_explanations", [])

    for expl in raw_explanations:
        f_id = expl.get("finding_id", "")
        r_id = expl.get("rule_id", "")

        # If model hallucinated a finding_id not present in deterministic findings, skip it
        if f_id not in valid_findings_by_id:
            logger.warning(f"Discarding hallucinated finding_id: {f_id}")
            continue

        true_finding = valid_findings_by_id[f_id]
        # Force rule_id to match true deterministic rule_id
        if r_id != true_finding.rule_id:
            logger.warning(f"Correcting mismatched rule_id for {f_id}: {r_id} -> {true_finding.rule_id}")
            r_id = true_finding.rule_id

        validated_explanations.append(
            FindingExplanation(
                finding_id=f_id,
                rule_id=r_id,
                plain_language_explanation=expl.get("plain_language_explanation", true_finding.description),
                why_it_deviates_from_baseline=expl.get("why_it_deviates_from_baseline", "Deviates from personal baseline metrics."),
                evidence_considered=expl.get("evidence_considered", [str(k) for k in true_finding.evidence.keys()]),
                mitigating_context=expl.get("mitigating_context", []),
            )
        )

    # For any deterministic findings the model omitted, inject a baseline explanation
    explained_ids = {e.finding_id for e in validated_explanations}
    for f_id, finding in valid_findings_by_id.items():
        if f_id not in explained_ids:
            validated_explanations.append(
                FindingExplanation(
                    finding_id=finding.finding_id,
                    rule_id=finding.rule_id,
                    plain_language_explanation=finding.description,
                    why_it_deviates_from_baseline="Activity breached established mathematical policy thresholds.",
                    evidence_considered=list(finding.evidence.keys()),
                    mitigating_context=[],
                )
            )

    # Validate assessment
    raw_assessment = raw_dict.get("investigation_assessment", {})
    assessment = InvestigationAssessment(
        overall_assessment=raw_assessment.get("overall_assessment", "Investigation required."),
        key_concerns=raw_assessment.get("key_concerns", []),
        mitigating_factors=raw_assessment.get("mitigating_factors", []),
        confidence=raw_assessment.get("confidence", "medium"),
        requires_human_review=bool(context.deterministic_findings),
    )

    # Mandatory disclaimer from regulatory policy
    disclaimer = "The system identifies activity requiring human review. A risk finding does not establish that fraud has occurred."

    return InvestigationResult(
        customer_id=context.customer.customer_id,
        executive_summary=raw_dict.get("executive_summary", "Review of customer transaction history."),
        investigation_assessment=assessment,
        finding_explanations=validated_explanations,
        investigation_questions=raw_dict.get("investigation_questions", [
            "What is the commercial or personal purpose of the flagged transfers?",
            "Has the customer confirmed initiating these transactions via an out-of-band channel?"
        ]),
        recommended_next_steps=raw_dict.get("recommended_next_steps", [
            "Contact customer via registered primary phone number to verify intent.",
            "Verify beneficiary account details against watchlists."
        ]),
        limitations=raw_dict.get("limitations", [
            "Automated system evaluates historical transaction data only.",
            "Requires human investigator verification of customer identity and intent."
        ]),
        disclaimer=disclaimer,
    )


def generate_investigation_report(
    customer_id: str,
    client_override: Optional[Any] = None,
    mock_response_text: Optional[str] = None,
) -> InvestigationResult:
    """
    Executes grounded Gemini synthesis for a customer.
    
    1. Builds verified grounding context.
    2. Calls Gemini using google-genai SDK.
    3. Validates and sanitizes structured output against deterministic source findings.
    """
    context = build_grounding_context(customer_id)

    # Format the prompt payload containing only verified grounding data
    prompt_payload = {
        "customer": context.customer.model_dump(),
        "baseline_summary": context.baseline_summary.model_dump(),
        # Focus on top 5 most critical findings to keep prompt concise and fast
        "deterministic_findings": [f.model_dump() for f in context.deterministic_findings[:5]],
        "relevant_policy_rules": [r.model_dump() for r in context.relevant_policy_rules],
        "relevant_transactions": [t.model_dump() for t in context.relevant_transactions],
        "regulatory_disclaimer": context.disclaimer,
        "operational_notes": context.notes,
    }

    prompt_str = (
        "You are generating a SentinelIQ Fraud Desk Investigation Report.\n"
        "Analyze the following verified grounding data and deterministic findings.\n"
        "Synthesize a clear, investigator-oriented report strictly in JSON matching this exact structure:\n"
        "{\n"
        '  "customer_id": "<customer_id>",\n'
        '  "executive_summary": "<summary of findings or state NO ATTENTION REQUIRED if 0 findings>",\n'
        '  "investigation_assessment": {\n'
        '    "overall_assessment": "<synthesized overview of the account state>",\n'
        '    "key_concerns": ["<specific concern 1>", "..."],\n'
        '    "mitigating_factors": ["<mitigating factor 1>", "..."],\n'
        '    "confidence": "high|medium|low",\n'
        '    "requires_human_review": true/false\n'
        "  },\n"
        '  "finding_explanations": [\n'
        "    {\n"
        '      "finding_id": "<exact finding_id from input>",\n'
        '      "rule_id": "<exact rule_id from input>",\n'
        '      "plain_language_explanation": "<clear explanation for fraud analyst>",\n'
        '      "why_it_deviates_from_baseline": "<explicit comparison against historical baseline>",\n'
        '      "evidence_considered": ["<specific evidence item>", "..."],\n'
        '      "mitigating_context": ["<context factor or ambiguity>", "..."]\n'
        "    }\n"
        "  ],\n"
        '  "investigation_questions": ["<question for analyst to ask customer>", "..."],\n'
        '  "recommended_next_steps": ["<concrete investigation step 1>", "..."],\n'
        '  "limitations": ["<inherent limitation of automated data analysis>", "..."]\n'
        "}\n\n"
        "GROUNDING DATA:\n"
        f"{json.dumps(prompt_payload, indent=2)}"
    )

    # Handle mock response for unit testing without live API
    if mock_response_text is not None:
        raw_text = mock_response_text
    else:
        client = get_gemini_client(client_override=client_override)
        model_name = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.1,  # Low temperature for strict determinism
            )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt_str,
                config=config,
            )
            raw_text = response.text
        except Exception as e:
            logger.error(f"Gemini API generation failed for {customer_id}: {e}")
            raise GeminiServiceError(f"Gemini API request failed: {str(e)}")

    # Parse JSON
    try:
        sanitized_text = _sanitize_json_text(raw_text)
        raw_dict = json.loads(sanitized_text)
    except Exception as e:
        logger.error(f"Failed to parse Gemini JSON output: {e}\nRaw text: {raw_text[:200]}")
        raise GeminiServiceError(f"Malformed Gemini JSON output: {str(e)}")

    # Post-generation validation & sanitization
    return validate_and_sanitize_investigation_result(raw_dict, context)
