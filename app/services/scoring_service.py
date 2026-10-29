import re
from typing import Dict, Any, List, Optional

class ScoringConfig:
    WEIGHT_MANDATORY = 0.35
    WEIGHT_TECHNICAL = 0.25
    WEIGHT_EXPERIENCE = 0.20
    WEIGHT_EDUCATION = 0.10
    WEIGHT_EVIDENCE_QUALITY = 0.10

class ScoringService:
    """
    Unified, deterministic scoring engine shared between Candidate Matching and Improve Resume.
    Adheres strictly to the mandatory weighted formula:
    Final Score = (Mandatory Requirements × 0.35) + (Technical Skills × 0.25) + 
                  (Experience & Projects × 0.20) + (Education × 0.10) + (Evidence Quality × 0.10)
    
    Each component is scored from 0 to 100 points.
    Formula weights are handled strictly in the backend and not shown in UI category titles.
    """

    def calculate_score(
        self,
        jd_reqs: Dict[str, Any],
        profile: Dict[str, Any],
        config: ScoringConfig = ScoringConfig()
    ) -> Dict[str, Any]:
        candidate_skills = {s.strip().lower() for s in profile.get("skills", []) if s}
        projects = profile.get("projects", [])
        experience = profile.get("experience", [])
        qualifications = profile.get("qualifications", [])
        
        # Build comprehensive candidate corpus for evidence verification
        exp_corpus_parts = []
        for e in experience:
            exp_corpus_parts.append(f"{e.get('role', '')} {e.get('evidence', '')} {e.get('description', '')}")
        for p in projects:
            exp_corpus_parts.append(f"{p.get('name', '')} {p.get('evidence', '')} {p.get('description', '')}")
        exp_corpus = " ".join(exp_corpus_parts).lower()

        # Helper to search for keyword/skill in text with word boundary
        def has_skill_evidence(skill_name: str, text: str) -> bool:
            if not skill_name:
                return False
            sn = skill_name.lower().strip()
            # Escaped pattern with word boundaries or punctuation boundaries
            pattern = r'(?:\b|_)' + re.escape(sn) + r'(?:\b|_)'
            return bool(re.search(pattern, text, re.IGNORECASE))

        # -------------------------------------------------------------
        # 1. Mandatory Requirements (0 to 100)
        # -------------------------------------------------------------
        mand_list = jd_reqs.get("mandatory_requirements", [])
        if not mand_list:
            # Fallback to top 2-3 essential technical skills if no explicit mandatory list
            top_tech = jd_reqs.get("technical_skills", [])[:3]
            mand_list = top_tech if top_tech else ["Core Professional Competence in Role"]

        mand_matched = []
        mand_missing = []
        for m in mand_list:
            m_clean = m.strip()
            # Check if requirement is evidenced in skills or experience corpus
            words = [w for w in re.split(r'[\s,;/]+', m_clean) if len(w) > 2 and w.lower() not in ["years", "experience", "must", "have", "with", "plus", "required", "knowledge", "strong"]]
            is_matched = False
            matched_words = []
            for w in words:
                if w.lower() in candidate_skills or has_skill_evidence(w, exp_corpus):
                    is_matched = True
                    matched_words.append(w)

            if is_matched or any(has_skill_evidence(k, m_clean) for k in candidate_skills):
                mand_matched.append({
                    "requirement": m_clean,
                    "evidence": f"Demonstrated competence via {', '.join(matched_words) if matched_words else 'candidate profile record'}"
                })
            else:
                mand_missing.append(m_clean)

        mand_ratio = len(mand_matched) / max(1, len(mand_list))
        # Each category is scored on 0-100 scale
        score_mandatory = round(mand_ratio * 100.0, 1)

        # Generate clear justification for Mandatory Requirements
        if mand_missing:
            mand_justification = (
                f"Candidate satisfies {len(mand_matched)} of {len(mand_list)} mandatory qualifications. "
                f"Missing mandatory requirements: {', '.join(mand_missing[:3])}. "
                f"Appropriate deduction applied reflecting critical role prerequisites."
            )
        else:
            mand_justification = (
                f"All {len(mand_list)} mandatory requirements are verified with supporting evidence in the candidate profile."
            )

        # -------------------------------------------------------------
        # 2. Technical / Role Skills (0 to 100)
        # Distinguish merely listed skills from demonstrated experience
        # -------------------------------------------------------------
        tech_list = jd_reqs.get("technical_skills", [])
        if not tech_list:
            tech_list = list(candidate_skills)[:5] or ["Python", "REST APIs", "SQL"]

        tech_matched = []
        tech_missing = []
        earned_points = 0.0

        for t in tech_list:
            t_clean = t.strip()
            t_lower = t_clean.lower()
            is_listed = t_lower in candidate_skills or any(t_lower in s for s in candidate_skills)
            is_demonstrated = has_skill_evidence(t_clean, exp_corpus)

            if is_demonstrated:
                # Full credit for demonstrated skills in real projects/work
                earned_points += 1.0
                tech_matched.append({
                    "skill": t_clean,
                    "level": "Demonstrated with experience/project evidence"
                })
            elif is_listed:
                # Partial credit (0.75) for skills merely listed without project context
                earned_points += 0.75
                tech_matched.append({
                    "skill": t_clean,
                    "level": "Listed in skills section (requires project elaboration)"
                })
            else:
                tech_missing.append(t_clean)

        tech_ratio = min(1.0, earned_points / max(1, len(tech_list)))
        score_technical = round(tech_ratio * 100.0, 1)

        if tech_missing:
            tech_justification = (
                f"Candidate demonstrates alignment on {len(tech_matched)} technical skills ({len([m for m in tech_matched if 'Demonstrated' in m['level']])} with project evidence). "
                f"Missing required or preferred technical skills: {', '.join(tech_missing[:4])}."
            )
        else:
            tech_justification = (
                f"Strong technical alignment across all {len(tech_list)} evaluated skills, with verified application in project history."
            )

        # -------------------------------------------------------------
        # 3. Relevant Experience & Projects (0 to 100)
        # Evaluate depth, complexity, and years of experience
        # -------------------------------------------------------------
        total_items = len(projects) + len(experience)
        
        # Check for technical complexity and deliverables
        has_metrics = bool(re.search(r'\b(?:\d+[%kKmM]?|\$\d+|\d+\s*years?)\b', exp_corpus))
        has_production = any(term in exp_corpus for term in ["production", "architecture", "deployed", "scaled", "lead", "optimized", "managed"])
        
        # Baseline from quantity of verified experience items (up to 3 items gives 70 base)
        base_exp = min(total_items / 3.0, 1.0) * 70.0
        # Qualitative bonus up to 30 points for complexity and verifiable outcomes
        bonus = (15.0 if has_metrics else 5.0) + (15.0 if has_production else 5.0)
        score_experience = round(min(100.0, base_exp + bonus), 1)

        exp_justification = (
            f"Evaluated {len(experience)} professional roles and {len(projects)} technical projects. "
            f"{'Demonstrates concrete deliverables with quantifiable outcomes. ' if has_metrics else 'Work descriptions provide solid context; adding STAR metrics can further highlight impact. '}"
            f"{'Includes production deployment and systems architecture experience.' if has_production else ''}"
        ).strip()

        # -------------------------------------------------------------
        # 4. Education & Credentials (0 to 100)
        # Evaluate candidate qualifications vs JD requirement
        # -------------------------------------------------------------
        edu_name = "Not specified"
        if qualifications:
            edu_name = qualifications[0].get("name", "Degree")
        
        edu_lower = edu_name.lower()
        if any(deg in edu_lower for deg in ["master", "m.s.", "ph.d", "doctorate"]):
            score_education = 100.0
            edu_justification = f"Advanced degree verified: {edu_name}."
        elif any(deg in edu_lower for deg in ["bachelor", "b.s.", "b.tech", "b.e.", "degree", "university", "college"]):
            score_education = 95.0
            edu_justification = f"Relevant undergraduate degree documented: {edu_name}."
        elif qualifications:
            score_education = 85.0
            edu_justification = f"Documented credential: {edu_name}."
        else:
            # If no education is explicitly stated, do not unfairly penalize excessively
            score_education = 70.0
            edu_justification = "Education details not explicitly detailed in resume; baseline score awarded."

        # -------------------------------------------------------------
        # 5. Evidence Quality & Specificity (0 to 100)
        # Assess credibility, specificity, and avoidance of keyword stuffing
        # -------------------------------------------------------------
        long_evidence_count = sum(1 for p in projects + experience if len(p.get("evidence", "") or p.get("description", "")) > 40)
        
        if long_evidence_count >= 3 and has_metrics:
            score_evidence_quality = 95.0
            evidence_justification = "High evidence quality: resume provides detailed, verifiable accomplishments and quantifiable STAR metrics."
        elif long_evidence_count >= 2:
            score_evidence_quality = 85.0
            evidence_justification = "Solid evidence quality with clear responsibility statements across multiple engagements."
        elif long_evidence_count >= 1:
            score_evidence_quality = 75.0
            evidence_justification = "Moderate evidence quality: core activities are documented, but broader detail would strengthen validation."
        else:
            score_evidence_quality = 55.0
            evidence_justification = "Limited specific evidence: resume relies on brief summaries or listed keywords without extended project detail."

        # -------------------------------------------------------------
        # Final Score Calculation (Strictly Backend Weighted Formula)
        # Final Score = (Mandatory × 0.35) + (Technical × 0.25) + 
        #               (Experience × 0.20) + (Education × 0.10) + (Evidence × 0.10)
        # -------------------------------------------------------------
        raw_final = (
            score_mandatory * config.WEIGHT_MANDATORY +
            score_technical * config.WEIGHT_TECHNICAL +
            score_experience * config.WEIGHT_EXPERIENCE +
            score_education * config.WEIGHT_EDUCATION +
            score_evidence_quality * config.WEIGHT_EVIDENCE_QUALITY
        )
        total_score = int(round(raw_final))
        total_score = max(0, min(total_score, 100))

        breakdown = {
            "mandatory_requirements": {
                "name": "Mandatory Requirements",
                "score": score_mandatory,
                "max": 100,
                "weight_percent": 35,
                "score_weighted": round(score_mandatory * config.WEIGHT_MANDATORY, 1),
                "ratio": round(mand_ratio, 2),
                "matched_count": len(mand_matched),
                "total_count": len(mand_list),
                "matched": mand_matched,
                "missing": mand_missing,
                "justification": mand_justification
            },
            "technical_skills": {
                "name": "Technical Skills",
                "score": score_technical,
                "max": 100,
                "weight_percent": 25,
                "score_weighted": round(score_technical * config.WEIGHT_TECHNICAL, 1),
                "ratio": round(tech_ratio, 2),
                "matched_count": len(tech_matched),
                "total_count": len(tech_list),
                "matched": tech_matched,
                "missing": tech_missing,
                "justification": tech_justification
            },
            "experience_and_projects": {
                "name": "Experience & Projects",
                "score": score_experience,
                "max": 100,
                "weight_percent": 20,
                "score_weighted": round(score_experience * config.WEIGHT_EXPERIENCE, 1),
                "evaluated_items": total_items,
                "justification": exp_justification
            },
            "education_credentials": {
                "name": "Education",
                "score": score_education,
                "max": 100,
                "weight_percent": 10,
                "score_weighted": round(score_education * config.WEIGHT_EDUCATION, 1),
                "qualification": edu_name,
                "justification": edu_justification
            },
            "evidence_quality": {
                "name": "Evidence Quality",
                "score": score_evidence_quality,
                "max": 100,
                "weight_percent": 10,
                "score_weighted": round(score_evidence_quality * config.WEIGHT_EVIDENCE_QUALITY, 1),
                "has_concrete_evidence": long_evidence_count > 0,
                "justification": evidence_justification
            }
        }

        return {
            "total_score": total_score,
            "breakdown": breakdown
        }

scoring_service = ScoringService()
