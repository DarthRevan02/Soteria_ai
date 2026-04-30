from pprint import pprint
from inference import *

from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl
import re



app = FastAPI()


def detect_fake(job: dict):
    return predict_extension_input_explainable(
        title=job.get("title", ""),
        location=job.get("location", ""),
        salary_range=job.get("salary_range", ""),
        company_profile=job.get("company_profile", ""),
        description=job.get("description", ""),
        requirements=job.get("requirements", ""),
        benefits=job.get("benefits", ""),
        employment_type=job.get("employment_type", ""),
        required_experience=job.get("required_experience", ""),
        required_education=job.get("required_education", ""),
        industry=job.get("industry", ""),
        function=job.get("function", "")
    )



# ===== INPUT MODEL =====
class RawJobInput(BaseModel):
    raw_text: str
    domain: str
    url: HttpUrl


# ===== SIMPLE PARSER (Internshala only) =====
def clean(text: str):
    return re.sub(r"\s+", " ", text).strip()


def get_section(text, start, end_list):
    try:
        part = text.split(start, 1)[1]
        for end in end_list:
            if end in part:
                return clean(part.split(end, 1)[0])
        return clean(part)
    except:
        return ""


def parse_internshala(raw_text: str, url: str):
    data = {}

    text = raw_text.replace("\r", "")
    text = text.rsplit("\n\n\n", 1)[-1]  # Get the main content after the last big break
    # print(text)

    # ===== TITLE (before - Internship) =====
    title_match = re.search(r"([^\n]+?)\s*-\s*Internship", text)
    data["title"] = clean(title_match.group(1)) if title_match else "Unknown"

    # ===== COMPANY NAME =====
    company_match = re.search(r"\n([A-Za-z0-9 &.,]+)\nWork from home", text)
    company_name = clean(company_match.group(1)) if company_match else "Unknown"

    # ===== COMPANY PROFILE (About <company>) =====
    about_company_key = f"About {company_name}"
    company_profile = get_section(
        text,
        about_company_key,
        ["Activity on Internshala", "Apply now", "Internship by Places"]
    )
    if company_profile.startswith("Website"):
        company_profile = company_profile.split(" ", 1)[-1]  # Remove "Website" prefix

    # fallback if not found
    if not company_profile:
        company_profile = company_name

    data["company_profile"] = company_profile

    # ===== LOCATION =====
    data["location"] = "Remote" if "Work from home" in text else "Unknown"

    # ===== SALARY =====
    salary_match = re.search(r"₹\s?[\d,]+\s*/month", text)
    data["salary_range"] = salary_match.group(0) if salary_match else "Unknown"

    # ===== DESCRIPTION (job work, NOT company) =====
    data["description"] = get_section(
        text,
        "About the work from home job/internship",
        ["Skill(s) required"]
    )

    # ===== REQUIREMENTS =====
    data["requirements"] = get_section(
        text,
        "Other requirements",
        ["Perks"]
    )

    # ===== BENEFITS =====
    data["benefits"] = get_section(
        text,
        "Perks",
        ["Number of openings"]
    )

    # ===== STATIC =====
    data["employment_type"] = "Internship" if "Internship" in text else "Unknown"
    # data["required_experience"] = "0-1 years"
    # data["required_education"] = "Any Graduate"
    data["required_experience"] = "Unknown"
    data["required_education"] = "Unknown"
    data["industry"] = "Unknown"
    data["function"] = "Unknown"
    data["source_platform"] = "Internshala"
    data["source_url"] = url

    # pprint(data)

    return data


# ===== DUMMY DETECTOR =====
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


def build_model_text(job: dict) -> str:
    parts = [
        f"TITLE {job.get('title', '')}",
        f"LOCATION {job.get('location', '')}",
        f"SALARY {job.get('salary_range', '')}",
        f"COMPANY {job.get('company_profile', '')}",
        f"DESCRIPTION {job.get('description', '')}",
        f"REQUIREMENTS {job.get('requirements', '')}",
        f"BENEFITS {job.get('benefits', '')}",
        f"EMPLOYMENT_TYPE {job.get('employment_type', '')}",
        f"EXPERIENCE {job.get('required_experience', '')}",
        f"EDUCATION {job.get('required_education', '')}",
        f"INDUSTRY {job.get('industry', '')}",
        f"FUNCTION {job.get('function', '')}",
    ]
    return " ".join(parts)


def detect_fake(job: dict):
    combined_text = build_model_text(job)
    cleaned_text = clean_extension_text(combined_text)

    suspicious_count = count_suspicious_phrases(cleaned_text, suspicious_phrases)

    text_vector = vectorizer.transform([cleaned_text])
    phrase_vector = csr_matrix([[suspicious_count]])
    final_vector = hstack([text_vector, phrase_vector])

    fake_risk_score = float(model.predict_proba(final_vector)[0][1])
    predicted_label = int(fake_risk_score >= 0.75)

    if fake_risk_score >= 0.75:
        risk_level = "High Risk"
        warning_message = "Warning: This internship appears highly suspicious."
    elif fake_risk_score >= 0.40:
        risk_level = "Medium Risk"
        warning_message = "Caution: This internship has some suspicious patterns."
    else:
        risk_level = "Low Risk"
        warning_message = "This internship looks relatively safe based on the model."

    output = {
        "predicted_label": predicted_label,
        "fake_risk_score": round(fake_risk_score, 4),
        "risk_level": risk_level,
        "warning_message": warning_message,
        "suspicious_phrase_count": suspicious_count,
    }
    print("=== DEBUG INFO ===")
    pprint(output)
    return output


# ===== API =====
@app.get("/")
def home():
    return {"message": "Fake Internship Detector Running 😎"}


@app.post("/analyze")
def analyze(data: RawJobInput):

    if "internshala" not in data.domain:
        return {"error": "Only Internshala supported for now"}

    structured = parse_internshala(data.raw_text, str(data.url))
    
    result_ml = detect_fake(structured)

    return {
        "structured_data": structured,
        "analysis": result_ml
    }


# test = parse_internshala(''' "6 Sharks are hiring 1 intern each. Pitch your idea. Apply now\nLoading, please wait...\n\nDownload our App\n\n4.5\n|\n1M+ Downloads\nS\nSaransh Sapra\nsaranshsapra08@gmail.com\n 4.2 Know More \nInternships\nJobs\nCourses\nOFFER\nCareer Launchpads\nGET HIRED FASTER\nOnline Degrees\nIS PRO\nMy Applications\nMy Bookmarks\nEdit Resume\nEdit Preferences\nMore\nBack to search\n\n\nMobile App Testing - Internship\nActively hiring\nMobile App Testing\nYoliday LLP\nWork from home\nStarts immediately\n3 Months\n₹ 5,000 /month\n22 May' 26\nPosted 7 days ago\nInternship\n157 applicants\n \nApply now\n150+ candidates have already applied. Increase your profile visibility to get noticed\nGet\nAbout the work from home job/internship\nYoliday is building India's most exciting platform for real, local experiences - treks, workshops, walks, concerts, tours, and more. We are looking for a detail-oriented Testing Intern to ensure high-quality performance across our mobile and web applications.\n\nSelected intern's day-to-day responsibilites include:\n\n1. Manage and report defects using structured defect-tracking processes.\n2. Develop and execute test cases for new and existing features.\n3. Perform functional and non-functional testing across different user flows.\n4. Conduct mobile application testing - with a strong focus on device-specific behavior.\n5. Review business requirements and convert them into effective test scenarios.\nSkill(s) required\nJira\nManual Testing\nPostman\nREST API\nSoftware Testing\nUsability Testing\nEarn certifications in these skills\nLearn Software Testing\nLearn VLSI\nLearn AI in Data Science\nLearn Cloud Computing\nLearn Embedded Systems\nLearn Android App Development\nLearn Vibe Coding\n+ 1 more skills\n\nWho can apply\n\nOnly those candidates can apply who:\n\n1. are available for the work from home job/internship\n\n2. can start the work from home job/internship between 22nd Apr'26 and 27th May'26\n\n3. are available for duration of 3 months\n\n4. have relevant skills and interests\n\n* Women wanting to start/restart their career can also apply.\n\nOther requirements\n\n1. Candidates with an iPhone or iPad.\n\n2. Experience with JIRA and Agile methodologies is a must.\n\n3. Strong interest in software quality assurance and modern testing practices.\n\n4. Familiarity with testing tools, techniques, and QA workflows.\n\n5. Understanding of web and mobile application technologies.\n\n6. Excellent attention to detail, analysis, and problem-solving skills.\n\n7. Good communication skills to collaborate with cross-functional teams.\n\n8. Preferred: Candidates who have access to iOS devices such as an iPhone or iPad for expanded device testing.\n\nPerks\nCertificate\nFlexible work hours\n5 days a week\nNumber of openings\n1\nAbout Yoliday LLP\nWebsite \nYoliday connects like-minded travelers for shared adventures, emphasizing collaboration and community. It enables users to create or join travel experiences, fostering unique bonds and friendships. Yoliday is a fast-growing experiential travel and experience platform that connects people to unique local experiences across India, including heritage walks, art workshops, cooking classes, music gigs, treks, and adventure tours. Our goal is to bring together passionate hosts and curious travelers on one platform, making travel about meaningful experiences rather than just sightseeing. We are expanding across India and are looking for passionate interns to help identify, reach out to, and onboard new experience providers (hosts) in their cities and regions.\nActivity on Internshala\nHiring since December 2023\n127 opportunities posted\n108 candidates hired\nApply now\nInternship by Places\nInternship in Bangalore\nInternship in Delhi\nInternships in Hyderabad\nInternship in Mumbai\nInternship in Chennai\nInternship in Pune\nInternship in Kolkata\nInternship in Gurgaon\nWork From Home Internships\nView all internship\nInternship by Stream\nJobs by Places\nJobs by Type\nFresher Jobs by Places\nFresher Jobs by Type\nCareer Launchpads\nCertification Courses\nOFFER\nAbout us\nTeam Diary\nTerms & Conditions\nSitemap\nWe are hiring\nBlog\nPrivacy\nCollege TPO registration\nHire interns for your company\nOur Services\nContact us\nAnnual Returns\nGrievance Redressal\nList of Companies\nPost a Job\nCompetitions\n \n   \n© Copyright 2026 Internshala\n(Scholiverse Educare Private Limited)\nHome\nInternships\nJobs\nCourses\nLaunchpads"''' , "https://internshala.com/internship/detail/work-from-home-mobile-app-testing-internship-at-yoliday-llp1776856741")
# detect_fake(test)