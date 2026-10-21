import logging
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class InMemoryGraphStore:
    """
    Resilient in-memory graph repository matching the Neo4j schema exactly:
    (:Candidate {doc_id})
      -[:HAS_SKILL]-> (:Skill {normalized_name})
      -[:HAS_QUALIFICATION]-> (:Qualification {name, field})
      -[:HAS_EXPERIENCE]-> (:Experience {role})
      -[:HAS_PROJECT]-> (:Project {name})
      -[:HAS_DOCUMENT]-> (:Document {doc_id, dms_ref})
    """
    def __init__(self):
        self.candidates: Dict[str, Dict[str, Any]] = {}
        self.skills: Dict[str, set] = {}  # skill_name -> set(doc_ids)
        self.qualifications: Dict[str, List[Dict[str, str]]] = {}  # doc_id -> list of qual nodes
        self.experiences: Dict[str, List[Dict[str, str]]] = {}     # doc_id -> list of exp nodes
        self.projects: Dict[str, List[Dict[str, str]]] = {}        # doc_id -> list of proj nodes
        self.documents: Dict[str, str] = {}                        # doc_id -> dms_ref

    def sync_candidate(self, doc_id: str, profile: Dict[str, Any], dms_ref: str):
        self.candidates[doc_id] = {"doc_id": doc_id}
        self.documents[doc_id] = dms_ref

        # Skills
        for skill in profile.get("skills", []):
            norm = skill.strip().lower()
            if norm not in self.skills:
                self.skills[norm] = set()
            self.skills[norm].add(doc_id)

        # Qualifications
        self.qualifications[doc_id] = profile.get("qualifications", [])
        # Experiences
        self.experiences[doc_id] = profile.get("experience", [])
        # Projects
        self.projects[doc_id] = profile.get("projects", [])

    def find_candidates_having_skills(self, required_skills: List[str]) -> List[str]:
        if not required_skills:
            return list(self.candidates.keys())

        matched_doc_ids = set()
        for s in required_skills:
            norm = s.strip().lower()
            matched_doc_ids.update(self.skills.get(norm, set()))
        return list(matched_doc_ids)

    def get_candidate_subgraph(self, doc_id: str) -> Dict[str, Any]:
        candidate = self.candidates.get(doc_id)
        if not candidate:
            return {}
        
        # Traverse relationships
        candidate_skills = [
            skill_name for skill_name, docs in self.skills.items()
            if doc_id in docs
        ]
        return {
            "candidate": candidate,
            "skills": candidate_skills,
            "qualifications": self.qualifications.get(doc_id, []),
            "experiences": self.experiences.get(doc_id, []),
            "projects": self.projects.get(doc_id, []),
            "document": {"doc_id": doc_id, "dms_ref": self.documents.get(doc_id)}
        }


class Neo4jRepository:
    """
    Manages Graph Database operations.
    Connects to Neo4j if enabled; otherwise uses InMemoryGraphStore.
    """
    def __init__(self):
        self._in_memory = InMemoryGraphStore()
        self._driver = None
        if settings.NEO4J_ENABLED:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(
                    settings.NEO4J_URI,
                    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                logger.info("Connected to live Neo4j instance at %s", settings.NEO4J_URI)
            except Exception as e:
                logger.warning("Could not connect to Neo4j: %s. Using in-memory graph repository.", str(e))
                self._driver = None

    def sync_candidate_profile(self, doc_id: str, profile: Dict[str, Any], dms_ref: str):
        # Always update in-memory graph
        self._in_memory.sync_candidate(doc_id, profile, dms_ref)

        if self._driver:
            query = """
            MERGE (c:Candidate {doc_id: $doc_id})
            MERGE (d:Document {doc_id: $doc_id, dms_ref: $dms_ref})
            MERGE (c)-[:HAS_DOCUMENT]->(d)
            WITH c
            UNWIND $skills AS skillName
                MERGE (s:Skill {normalized_name: toLower(trim(skillName))})
                MERGE (c)-[:HAS_SKILL]->(s)
            """
            try:
                with self._driver.session() as session:
                    session.run(query, doc_id=doc_id, dms_ref=dms_ref, skills=profile.get("skills", []))
            except Exception as e:
                logger.error("Failed to run Neo4j Cypher query: %s", str(e))

    def query_candidates_by_skills(self, skills: List[str]) -> List[str]:
        if self._driver:
            query = """
            MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)
            WHERE s.normalized_name IN [name IN $skills | toLower(trim(name))]
            RETURN DISTINCT c.doc_id AS doc_id
            """
            try:
                with self._driver.session() as session:
                    result = session.run(query, skills=skills)
                    return [record["doc_id"] for record in result]
            except Exception as e:
                logger.error("Failed to query Neo4j: %s", str(e))
        return self._in_memory.find_candidates_having_skills(skills)

    def get_candidate_graph(self, doc_id: str) -> Dict[str, Any]:
        return self._in_memory.get_candidate_subgraph(doc_id)

neo4j_repository = Neo4jRepository()
