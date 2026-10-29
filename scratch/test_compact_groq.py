import os, json, time, httpx
from dotenv import load_dotenv

load_dotenv(".env", override=True)
api_key = os.getenv("GROQ_API_KEY")
base_url = "https://api.groq.com/openai/v1"

system_prompt = (
    "You are Groq, an elite executive talent strategist. Optimize the anonymized resume for the target role.\n"
    "RULES:\n"
    "1. STRICT TRUTHFULNESS: Never invent qualifications, companies, dates, or arbitrary metrics.\n"
    "2. Report missing skills honestly under 'gaps'.\n"
    "3. PRESERVE PLACEHOLDERS: Keep [CANDIDATE_NAME], [CANDIDATE_EMAIL], [CANDIDATE_PHONE], [CANDIDATE_LOCATION], [CANDIDATE_LINK_...] exactly intact.\n"
    "4. NO MARKDOWN HASHES: Do NOT use #, ##, ###. Use clean plain text.\n"
    "5. Must be 100% English.\n"
    "6. Sections formatting: 'improved_resume_text' MUST include uppercase headers:\n"
    "   'PROFESSIONAL SUMMARY', 'TECHNICAL SKILLS' (with bullet '- Languages & Frameworks:'), and 'PROFESSIONAL EXPERIENCE'.\n"
    "7. Use active executive STAR verbs (Architected, Engineered, Optimized, Spearheaded) with metrics.\n"
    "8. Keep 'reason' to 1 concise sentence. Keep each change focused. Generate exactly 3 targeted items in 'changes'.\n"
    "9. Output ONLY valid JSON matching this schema:\n"
    "{\n"
    '  "changes": [{"section": "professional_summary"|"skills"|"professional_experience", "target_element_id": "elem-1", "original_text": "...", "proposed_text": "...", "reason": "...", "supporting_evidence": [{"source": "candidate_resume", "text": "..."}], "requires_user_confirmation": false}],\n'
    '  "improved_resume_text": "...",\n'
    '  "gaps": [{"requirement": "...", "status": "not_demonstrated", "evidence": null}],\n'
    '  "matched_requirements": [{"requirement": "...", "status": "demonstrated", "evidence": "..."}],\n'
    '  "change_summary": "..."\n'
    "}"
)

user_content = {
    "target_role": "Senior Python Engineer",
    "job_requirements": {"role": "Senior Python Engineer", "required_skills": ["Python", "FastAPI", "Docker", "PostgreSQL"]},
    "candidate_resume_anonymized": (
        "[CANDIDATE_NAME]\n"
        "[CANDIDATE_EMAIL] | [CANDIDATE_PHONE] | [CANDIDATE_LOCATION]\n\n"
        "PROFESSIONAL SUMMARY\n"
        "Software Engineer with 4 years building scalable web services in Python and microservices.\n\n"
        "TECHNICAL SKILLS\n"
        "- Languages & Frameworks: Python, FastAPI, Django, Flask, PostgreSQL\n\n"
        "PROFESSIONAL EXPERIENCE\n"
        "Backend Engineer at Acme Corp (2021 - Present)\n"
        "- Built high throughput REST APIs using Python and PostgreSQL handling 1M daily requests.\n"
        "- Containerized and deployed backend services with Docker on AWS."
    )
}

headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
payload = {
    "model": "openai/gpt-oss-120b",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_content)}
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0.15,
    "max_tokens": 1800
}

t0 = time.time()
with httpx.Client(timeout=15.0) as client:
    r = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
    elapsed = time.time() - t0
    print(f"Status: {r.status_code}, Latency: {elapsed:.2f}s")
    if r.status_code == 200:
        data = r.json()
        print("Prompt tokens:", data.get("usage", {}).get("prompt_tokens"))
        print("Completion tokens:", data.get("usage", {}).get("completion_tokens"))
        print("Total tokens:", data.get("usage", {}).get("total_tokens"))
        raw_resp = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw_resp)
        print("Keys:", list(parsed.keys()))
        print("Changes count:", len(parsed.get("changes", [])))
        print("Summary:", parsed.get("change_summary"))
        print("Improved text length:", len(parsed.get("improved_resume_text", "")))
    else:
        print("Error:", r.text[:300])
