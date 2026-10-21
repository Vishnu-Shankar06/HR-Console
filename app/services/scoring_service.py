from typing import Dict, Any, List

class ScoringConfig:
    WEIGHT_MANDATORY = 0.35
    WEIGHT_TECHNICAL = 0.25
    WEIGHT_EXPERIENCE = 0.20
    WEIGHT_EDUCATION = 0.10
    WEIGHT_EVIDENCE_QUALITY = 0.10

class ScoringService:
    """
    Transparent, configurable scoring engine adhering strictly to Section 8.3:
    - Mandatory requirements (35%)
    - Technical skills (25%)
    - Relevant experience & projects (20%)
    - Education / credentials (10%)
    - Evidence quality & specificity (10%)
    
    Explicitly excludes PII, demographics, and personal attributes.
    """

    def calculate_score(
        self,
        jd_reqs: Dict[str, Any],
        profile: Dict[str, Any],
        config: ScoringConfig = ScoringConfig()
    ) -> Dict[str, Any]:
        candidate_skills = {s.lower() for s in profile.get("skills", [])}
        
        # 1. Mandatory Requirements (35 points max)
        mand_list = jd_reqs.get("mandatory_requirements", [])
        if mand_list:
            mand_matches = 0
            for m in mand_list:
                if any(k.lower() in m.lower() for k in candidate_skills):
                    mand_matches += 1
            mand_ratio = mand_matches / len(mand_list)
        else:
            mand_ratio = 1.0
        score_mandatory = round(mand_ratio * (config.WEIGHT_MANDATORY * 100), 1)

        # 2. Technical / Role Skills (25 points max)
        tech_list = jd_reqs.get("technical_skills", [])
        if tech_list:
            tech_matches = sum(1 for t in tech_list if t.lower() in candidate_skills)
            tech_ratio = tech_matches / len(tech_list)
        else:
            tech_ratio = 0.8
        score_technical = round(tech_ratio * (config.WEIGHT_TECHNICAL * 100), 1)

        # 3. Relevant Experience & Projects (20 points max)
        projects = profile.get("projects", [])
        experience = profile.get("experience", [])
        exp_count = len(projects) + len(experience)
        exp_ratio = min(exp_count / 3.0, 1.0)
        score_experience = round(exp_ratio * (config.WEIGHT_EXPERIENCE * 100), 1)

        # 4. Education & Credentials (10 points max)
        qualifications = profile.get("qualifications", [])
        edu_ratio = 1.0 if qualifications else 0.5
        score_education = round(edu_ratio * (config.WEIGHT_EDUCATION * 100), 1)

        # 5. Evidence Quality & Specificity (10 points max)
        # Assesses whether claims have concrete text evidence
        has_evidence = any(len(p.get("evidence", "")) > 15 for p in projects + experience)
        evidence_ratio = 1.0 if has_evidence else 0.6
        score_evidence_quality = round(evidence_ratio * (config.WEIGHT_EVIDENCE_QUALITY * 100), 1)

        total_score = int(round(
            score_mandatory + score_technical + score_experience + score_education + score_evidence_quality
        ))
        total_score = max(0, min(total_score, 100))

        breakdown = {
            "mandatory_requirements": {
                "score": score_mandatory,
                "max": int(config.WEIGHT_MANDATORY * 100),
                "ratio": round(mand_ratio, 2),
                "matched_count": int(mand_ratio * len(mand_list)) if mand_list else 1,
                "total_count": len(mand_list) or 1
            },
            "technical_skills": {
                "score": score_technical,
                "max": int(config.WEIGHT_TECHNICAL * 100),
                "ratio": round(tech_ratio, 2),
                "matched_count": tech_matches if tech_list else 0,
                "total_count": len(tech_list)
            },
            "experience_and_projects": {
                "score": score_experience,
                "max": int(config.WEIGHT_EXPERIENCE * 100),
                "evaluated_items": exp_count
            },
            "education_credentials": {
                "score": score_education,
                "max": int(config.WEIGHT_EDUCATION * 100),
                "qualification": qualifications[0].get("name", "Degree") if qualifications else "Not specified"
            },
            "evidence_quality": {
                "score": score_evidence_quality,
                "max": int(config.WEIGHT_EVIDENCE_QUALITY * 100),
                "has_concrete_evidence": has_evidence
            }
        }

        return {
            "total_score": total_score,
            "breakdown": breakdown
        }

scoring_service = ScoringService()
