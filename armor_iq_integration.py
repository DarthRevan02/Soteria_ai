"""
armor_iq_integration.py

Wraps the ArmorIQ SDK for the Fake Internship Detector pipeline.

Flow:
  ML model output (fake_risk_score, risk_level, etc.)
       ↓
  capture_plan()   — define intent: "evaluate internship posting"
       ↓
  get_intent_token() — get cryptographic token with scam-detection policy
       ↓
  invoke()         — send ML result through ArmorIQ proxy → get verdict
       ↓
  ArmorVerdict     — allow / warn / block / high_block → sent to ArmorClaw

Set these environment variables before running:
  ARMORIQ_API_KEY   = ak_live_<64 hex chars>
  ARMORIQ_USER_ID   = (any unique string, e.g. "scam-detector-user")
  ARMORIQ_AGENT_ID  = (any unique string, e.g. "scam-detector-agent-v1")
"""

import os
from dataclasses import dataclass, field

from armoriq_sdk import ArmorIQClient


# ══════════════════════════════════════════════════════════════════
# CLIENT — initialised once at import time
# (API key is read from env; user enters it before running)
# ══════════════════════════════════════════════════════════════════
_client: ArmorIQClient | None = None


def get_client() -> ArmorIQClient:
    global _client
    if _client is None:
        _client = ArmorIQClient(
            api_key=os.getenv("ARMORIQ_API_KEY"),
            user_id=os.getenv("ARMORIQ_USER_ID", "scam-detector-user"),
            agent_id=os.getenv("ARMORIQ_AGENT_ID", "scam-detector-agent-v1"),
        )
    return _client


# ══════════════════════════════════════════════════════════════════
# VERDICT MODEL
# Maps ArmorIQ's allow/deny response to our 4-level system
# ══════════════════════════════════════════════════════════════════
@dataclass
class ArmorVerdict:
    verdict: str            # "ALLOW" | "WARN" | "BLOCK" | "HIGH_BLOCK"
    score: float            # ML fake_risk_score (0.0–1.0)
    score_pct: int          # score as integer percentage
    risk_level: str         # "Low Risk" | "Medium Risk" | "High Risk"
    reasons: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    policy_triggers: list[str] = field(default_factory=list)
    armoriq_verified: bool = False   # True if ArmorIQ call succeeded

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "score_pct": self.score_pct,
            "risk_level": self.risk_level,
            "reasons": self.reasons,
            "keywords": self.keywords,
            "policy_triggers": self.policy_triggers,
            "armoriq_verified": self.armoriq_verified,
        }


# ══════════════════════════════════════════════════════════════════
# POLICY
# Defines what ArmorIQ allows/denies for the scam-detector MCP
# ══════════════════════════════════════════════════════════════════
SCAM_DETECTOR_POLICY = {
    # Allow the scam analysis action only
    "allow": ["scam-detector-mcp/analyze_posting"],
    # Block any write/modify actions (detector should be read-only)
    "deny": ["scam-detector-mcp/modify_*", "scam-detector-mcp/delete_*"],
    "allowed_tools": ["analyze_posting"],
    "rate_limit": 200,   # max 200 requests/hour
}


# ══════════════════════════════════════════════════════════════════
# VERDICT MAPPING
# Translate ArmorIQ's response data into our 4-level verdict
# ══════════════════════════════════════════════════════════════════
def _map_to_verdict(ml_result: dict, armoriq_data: dict) -> str:
    """
    ArmorIQ enforces policy on the invoke() call.
    If invoke() succeeds, we still need to map the ML risk score
    into our 4-level verdict so ArmorClaw knows what to do.

    Levels:
      HIGH_BLOCK  — score ≥ 0.85  OR  matched hard block triggers
      BLOCK       — score ≥ 0.75
      WARN        — score ≥ 0.40  OR  suspicious phrase count ≥ 3
      ALLOW       — score < 0.40  AND  no hard triggers
    """
    score = ml_result.get("fake_risk_score", 0.0)
    phrase_count = ml_result.get("suspicious_phrase_count", 0)
    matched = ml_result.get("matched_reasons", {})

    # Flatten all matched items
    all_matched = " ".join(
        " ".join(v) for v in matched.values() if isinstance(v, list)
    ).lower()

    hard_block_phrases = ["pay to apply", "upfront fee", "money transfer", "payment required"]
    has_hard_block = any(p in all_matched for p in hard_block_phrases)

    if score >= 0.85 or has_hard_block:
        return "HIGH_BLOCK"
    elif score >= 0.75:
        return "BLOCK"
    elif score >= 0.40 or phrase_count >= 3:
        return "WARN"
    else:
        return "ALLOW"


def _collect_reasons_and_keywords(ml_result: dict) -> tuple[list[str], list[str], list[str]]:
    """Extract human-readable reasons, keywords, triggers from ML matched_reasons."""
    matched = ml_result.get("matched_reasons", {})
    top_terms = ml_result.get("top_fraud_terms", [])

    reasons, keywords, triggers = [], [], []

    category_map = {
        "matched_payment_keywords": ("Requires payment or fees to apply", "payment"),
        "matched_urgency_keywords": ("Uses urgency tactics (e.g. 'apply fast', 'instant joining')", "urgency"),
        "matched_contact_keywords": ("Uses unofficial channels (WhatsApp, Telegram, DM)", "unofficial_contact"),
        "matched_promise_keywords": ("Makes unrealistic promises (easy money, guaranteed income)", "false_promises"),
        "matched_suspicious_phrases": ("Contains known scam phrases", "scam_phrases"),
    }

    for key, (reason_text, trigger_tag) in category_map.items():
        items = matched.get(key, [])
        if items:
            reasons.append(reason_text)
            triggers.append(trigger_tag)
            keywords.extend(items[:3])

    # Add top ML fraud terms as extra keywords
    for t in top_terms:
        kw = t.get("term", "")
        if kw and kw not in keywords:
            keywords.append(kw)

    return reasons, keywords, triggers


# ══════════════════════════════════════════════════════════════════
# MAIN FUNCTION — called from main.py /analyze endpoint
# ══════════════════════════════════════════════════════════════════
def evaluate_with_armoriq(ml_result: dict, structured_job: dict) -> ArmorVerdict:
    """
    Sends the ML result through ArmorIQ for policy-enforced evaluation.
    Returns an ArmorVerdict for ArmorClaw to enforce.

    Falls back gracefully if ArmorIQ is unreachable (fail-open with WARN).
    """
    score = ml_result.get("fake_risk_score", 0.0)
    risk_level = ml_result.get("risk_level", "Low Risk")

    reasons, keywords, triggers = _collect_reasons_and_keywords(ml_result)

    try:
        client = get_client()

        # ── Step 1: Capture the plan ─────────────────────────────
        # Tells ArmorIQ: "I intend to analyze this posting"
        plan = {
            "goal": "Evaluate internship/job posting for scam indicators",
            "steps": [
                {
                    "action": "analyze_posting",
                    "mcp": "scam-detector-mcp",
                    "description": "Run scam analysis on structured job data",
                    "params": {
                        "title": structured_job.get("title", ""),
                        "fake_risk_score": score,
                        "risk_level": risk_level,
                        "suspicious_phrase_count": ml_result.get("suspicious_phrase_count", 0),
                    },
                }
            ],
        }

        captured = client.capture_plan(
            llm="ml-model-xgboost",
            prompt=f"Analyze job posting: {structured_job.get('title', 'Unknown')}",
            plan=plan,
            metadata={
                "source_platform": structured_job.get("source_platform", "unknown"),
                "fake_risk_score": score,
            },
        )

        # ── Step 2: Get intent token with scam-detector policy ────
        token_response = client.get_intent_token(
            plan_capture=captured,
            policy=SCAM_DETECTOR_POLICY,
            validity_seconds=60,
        )

        # ── Step 3: Invoke through ArmorIQ proxy ─────────────────
        # ArmorIQ verifies the action is within policy before allowing
        result = client.invoke(
            mcp="scam-detector-mcp",
            action="analyze_posting",
            intent_token=token_response,
            params={
                "fake_risk_score": score,
                "risk_level": risk_level,
                "suspicious_phrase_count": ml_result.get("suspicious_phrase_count", 0),
                "matched_reasons": ml_result.get("matched_reasons", {}),
            },
        )

        # ── Step 4: Map result to ArmorVerdict ───────────────────
        verdict_level = _map_to_verdict(ml_result, result.get("data", {}))

        return ArmorVerdict(
            verdict=verdict_level,
            score=score,
            score_pct=int(score * 100),
            risk_level=risk_level,
            reasons=reasons,
            keywords=keywords,
            policy_triggers=triggers,
            armoriq_verified=True,
        )

    except Exception as e:
        # ArmorIQ unreachable or policy rejected — fail-open with WARN
        print(f"[ArmorIQ] Error: {e} — falling back to local verdict")

        verdict_level = _map_to_verdict(ml_result, {})

        return ArmorVerdict(
            verdict=verdict_level,
            score=score,
            score_pct=int(score * 100),
            risk_level=risk_level,
            reasons=reasons or ["Could not verify via ArmorIQ — treat with caution"],
            keywords=keywords,
            policy_triggers=triggers,
            armoriq_verified=False,
        )
