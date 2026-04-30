import re
from pathlib import Path

import joblib
from scipy.sparse import csr_matrix, hstack


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "model"

MODEL_PATH = MODEL_DIR / "model.pkl"
VECTORIZER_PATH = MODEL_DIR / "vectorizer.pkl"
SUSPICIOUS_PHRASES_PATH = MODEL_DIR / "suspicious_phrases.pkl"

FINAL_ALERT_THRESHOLD = 0.75
HIGH_RISK_THRESHOLD = 0.55
MEDIUM_RISK_THRESHOLD = 0.30

model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECTORIZER_PATH)
suspicious_phrases = joblib.load(SUSPICIOUS_PHRASES_PATH)


payment_keywords = [
    "registration fee",
    "pay to apply",
    "application fee",
    "security deposit",
    "deposit amount",
    "training fee",
    "payment required",
    "processing fee",
]

urgency_keywords = [
    "immediate joining",
    "urgent hiring",
    "limited seats",
    "apply fast",
    "quick selection process",
    "instant joining",
    "join immediately",
]

contact_keywords = [
    "whatsapp only",
    "message on whatsapp",
    "dm to apply",
    "telegram",
    "contact directly",
    "call now",
]

promise_keywords = [
    "no experience needed",
    "earn huge incentives",
    "easy money",
    "guaranteed stipend",
    "earn from home",
    "daily payout",
    "refer and earn",
]


def clean_extension_text(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"<.*?>", " ", text)
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b\d{10,}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def count_suspicious_phrases(text: str, phrase_list: list[str]) -> int:
    text = str(text).lower()
    return sum(1 for phrase in phrase_list if phrase in text)


def get_risk_level(fake_risk_score: float) -> str:
    if fake_risk_score >= HIGH_RISK_THRESHOLD:
        return "High Risk"
    if fake_risk_score >= MEDIUM_RISK_THRESHOLD:
        return "Medium Risk"
    return "Low Risk"


def get_warning_message(fake_risk_score: float) -> str:
    if fake_risk_score >= HIGH_RISK_THRESHOLD:
        return "Warning: This internship appears highly suspicious."
    if fake_risk_score >= MEDIUM_RISK_THRESHOLD:
        return "Caution: This internship has some suspicious patterns."
    return "This internship looks relatively safe based on the model."


def extract_matched_reasons(text: str) -> dict:
    text = str(text).lower()

    return {
        "matched_suspicious_phrases": [phrase for phrase in suspicious_phrases if phrase in text],
        "matched_payment_keywords": [word for word in payment_keywords if word in text],
        "matched_urgency_keywords": [word for word in urgency_keywords if word in text],
        "matched_contact_keywords": [word for word in contact_keywords if word in text],
        "matched_promise_keywords": [word for word in promise_keywords if word in text],
    }


def get_top_fraud_terms(cleaned_text: str, top_n: int = 5) -> list[dict]:
    text_vector = vectorizer.transform([cleaned_text])
    feature_names = vectorizer.get_feature_names_out()

    # Last coefficient belongs to suspicious_phrase_count in the hybrid model
    text_coefficients = model.coef_[0][:-1]
    contributions = text_vector.multiply(text_coefficients).toarray().flatten()

    top_indices = contributions.argsort()[::-1]

    top_terms = []
    for idx in top_indices:
        if contributions[idx] > 0:
            top_terms.append(
                {
                    "term": feature_names[idx],
                    "contribution": round(float(contributions[idx]), 4),
                }
            )
        if len(top_terms) == top_n:
            break

    return top_terms


def build_model_text(
    title: str = "",
    location: str = "",
    salary_range: str = "",
    company_profile: str = "",
    description: str = "",
    requirements: str = "",
    benefits: str = "",
    employment_type: str = "",
    required_experience: str = "",
    required_education: str = "",
    industry: str = "",
    function: str = "",
) -> str:
    parts = [
        f"TITLE {title}",
        f"LOCATION {location}",
        f"SALARY {salary_range}",
        f"COMPANY {company_profile}",
        f"DESCRIPTION {description}",
        f"REQUIREMENTS {requirements}",
        f"BENEFITS {benefits}",
        f"EMPLOYMENT_TYPE {employment_type}",
        f"EXPERIENCE {required_experience}",
        f"EDUCATION {required_education}",
        f"INDUSTRY {industry}",
        f"FUNCTION {function}",
    ]
    return " ".join(parts)


def predict_extension_input(
    title: str = "",
    location: str = "",
    salary_range: str = "",
    company_profile: str = "",
    description: str = "",
    requirements: str = "",
    benefits: str = "",
    employment_type: str = "",
    required_experience: str = "",
    required_education: str = "",
    industry: str = "",
    function: str = "",
) -> dict:
    combined_text = build_model_text(
        title=title,
        location=location,
        salary_range=salary_range,
        company_profile=company_profile,
        description=description,
        requirements=requirements,
        benefits=benefits,
        employment_type=employment_type,
        required_experience=required_experience,
        required_education=required_education,
        industry=industry,
        function=function,
    )

    cleaned_text = clean_extension_text(combined_text)
    suspicious_count = count_suspicious_phrases(cleaned_text, suspicious_phrases)

    text_vector = vectorizer.transform([cleaned_text])
    phrase_vector = csr_matrix([[suspicious_count]])
    final_vector = hstack([text_vector, phrase_vector])

    fake_risk_score = float(model.predict_proba(final_vector)[0][1])
    predicted_label = int(fake_risk_score >= FINAL_ALERT_THRESHOLD)

    return {
        "predicted_label": predicted_label,
        "fake_risk_score": round(fake_risk_score, 4),
        "risk_level": get_risk_level(fake_risk_score),
        "warning_message": get_warning_message(fake_risk_score),
        "suspicious_phrase_count": int(suspicious_count),
        "threshold_used": FINAL_ALERT_THRESHOLD,
    }


def predict_extension_input_explainable(
    title: str = "",
    location: str = "",
    salary_range: str = "",
    company_profile: str = "",
    description: str = "",
    requirements: str = "",
    benefits: str = "",
    employment_type: str = "",
    required_experience: str = "",
    required_education: str = "",
    industry: str = "",
    function: str = "",
) -> dict:
    combined_text = build_model_text(
        title=title,
        location=location,
        salary_range=salary_range,
        company_profile=company_profile,
        description=description,
        requirements=requirements,
        benefits=benefits,
        employment_type=employment_type,
        required_experience=required_experience,
        required_education=required_education,
        industry=industry,
        function=function,
    )

    cleaned_text = clean_extension_text(combined_text)
    suspicious_count = count_suspicious_phrases(cleaned_text, suspicious_phrases)

    text_vector = vectorizer.transform([cleaned_text])
    phrase_vector = csr_matrix([[suspicious_count]])
    final_vector = hstack([text_vector, phrase_vector])

    fake_risk_score = float(model.predict_proba(final_vector)[0][1])
    predicted_label = int(fake_risk_score >= FINAL_ALERT_THRESHOLD)

    return {
        "predicted_label": predicted_label,
        "fake_risk_score": round(fake_risk_score, 4),
        "risk_level": get_risk_level(fake_risk_score),
        "warning_message": get_warning_message(fake_risk_score),
        "suspicious_phrase_count": int(suspicious_count),
        "threshold_used": FINAL_ALERT_THRESHOLD,
        "matched_reasons": extract_matched_reasons(cleaned_text),
        "top_fraud_terms": get_top_fraud_terms(cleaned_text, top_n=5),
    }
