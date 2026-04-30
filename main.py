from pprint import pprint
from inference import predict_extension_input_explainable
from armor_iq_integration import evaluate_with_armoriq

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import re


app = FastAPI(title="Fake Internship Detector", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Input model
# ──────────────────────────────────────────────
class RawJobInput(BaseModel):
    raw_text: str
    domain: str
    url: HttpUrl


# ──────────────────────────────────────────────
# Text utilities
# ──────────────────────────────────────────────
def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def get_section(text: str, start: str, end_list: list[str]) -> str:
    try:
        part = text.split(start, 1)[1]
        for end in end_list:
            if end in part:
                return clean(part.split(end, 1)[0])
        return clean(part)
    except Exception:
        return ""


# ──────────────────────────────────────────────
# Internshala parser
# ──────────────────────────────────────────────
def parse_internshala(raw_text: str, url: str) -> dict:
    data = {}
    text = raw_text.replace("\r", "")
    text = text.rsplit("\n\n\n", 1)[-1]

    title_match = re.search(r"([^\n]+?)\s*-\s*Internship", text)
    data["title"] = clean(title_match.group(1)) if title_match else "Unknown"

    company_match = re.search(r"\n([A-Za-z0-9 &.,]+)\nWork from home", text)
    company_name = clean(company_match.group(1)) if company_match else "Unknown"

    about_company_key = f"About {company_name}"
    company_profile = get_section(
        text,
        about_company_key,
        ["Activity on Internshala", "Apply now", "Internship by Places"],
    )
    if company_profile.startswith("Website"):
        company_profile = company_profile.split(" ", 1)[-1]
    if not company_profile:
        company_profile = company_name
    data["company_profile"] = company_profile

    data["location"] = "Remote" if "Work from home" in text else "Unknown"

    salary_match = re.search(r"₹\s?[\d,]+\s*/month", text)
    data["salary_range"] = salary_match.group(0) if salary_match else "Unknown"

    data["description"] = get_section(
        text,
        "About the work from home job/internship",
        ["Skill(s) required"],
    )
    data["requirements"] = get_section(text, "Other requirements", ["Perks"])
    data["benefits"] = get_section(text, "Perks", ["Number of openings"])

    data["employment_type"]     = "Internship" if "Internship" in text else "Unknown"
    data["required_experience"] = "Unknown"
    data["required_education"]  = "Unknown"
    data["industry"]            = "Unknown"
    data["function"]            = "Unknown"
    data["source_platform"]     = "Internshala"
    data["source_url"]          = url

    return data


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.get("/")
def home():
    return {"message": "Fake Internship Detector v2 — ArmorIQ + ArmorClaw enabled 🛡️"}


@app.post("/analyze")
def analyze(data: RawJobInput):
    if "internshala" not in data.domain:
        return {"error": "Only Internshala supported for now"}

    # 1. Parse raw page text into structured fields
    structured = parse_internshala(data.raw_text, str(data.url))

    # 2. Run ML model (explainable variant)
    ml_result = predict_extension_input_explainable(
        title=structured.get("title", ""),
        location=structured.get("location", ""),
        salary_range=structured.get("salary_range", ""),
        company_profile=structured.get("company_profile", ""),
        description=structured.get("description", ""),
        requirements=structured.get("requirements", ""),
        benefits=structured.get("benefits", ""),
        employment_type=structured.get("employment_type", ""),
        required_experience=structured.get("required_experience", ""),
        required_education=structured.get("required_education", ""),
        industry=structured.get("industry", ""),
        function=structured.get("function", ""),
    )

    # 3. ArmorIQ SDK — policy-enforced evaluation
    verdict = evaluate_with_armoriq(ml_result, structured)

    print("=== ArmorIQ Verdict ===")
    pprint(verdict.to_dict())

    # 4. Return verdict for ArmorClaw (browser extension) to enforce
    return {
        "structured_data": structured,
        "ml_analysis": {
            "fake_risk_score": ml_result.get("fake_risk_score"),
            "risk_level": ml_result.get("risk_level"),
            "suspicious_phrase_count": ml_result.get("suspicious_phrase_count"),
            "warning_message": ml_result.get("warning_message"),
            "top_fraud_terms": ml_result.get("top_fraud_terms", []),
        },
        "armor_verdict": verdict.to_dict(),   # ← ArmorClaw reads this
    }
