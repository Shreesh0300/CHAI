"""
Relevance-based memory retrieval for CHAI.
Filters and ranks stored user memories so that only genuinely relevant
facts are injected into Chat or Solve prompts.
"""
import re
from typing import List, Set, Tuple
from backend.memory.models import MemoryItem, MemoryCategory
from backend.shared.logger import get_logger

logger = get_logger(__name__)

# Stopwords to ignore in lexical matching
STOPWORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do",
    "does", "did", "and", "or", "but", "if", "then", "else", "when", "where", "why",
    "how", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now", "i", "me", "my", "myself", "we", "our",
    "you", "your", "he", "she", "it", "they", "them", "what", "which", "who", "whom",
    "this", "that", "these", "those", "am", "as", "about", "into", "through", "during",
    "before", "after", "above", "below", "up", "down", "out", "off", "over", "under",
}

# Domain keyword clusters for semantic category matching
TOPIC_CLUSTERS = {
    MemoryCategory.CAREER_GOAL: {
        "job", "career", "internship", "startup", "company", "business", "founder",
        "entrepreneur", "hiring", "offer", "salary", "role", "work", "profession",
        "future", "goal", "plans", "industry", "promotion", "corporate", "saas",
    },
    MemoryCategory.EDUCATION: {
        "college", "university", "student", "degree", "course", "major", "school",
        "study", "studying", "graduation", "graduate", "semester", "internship",
        "gpa", "exam", "professor", "campus",
    },
    MemoryCategory.PROJECT: {
        "project", "building", "app", "application", "software", "product", "platform",
        "code", "repo", "architecture", "system", "stack", "startup", "saas", "chai",
    },
    MemoryCategory.PREFERENCE: {
        "prefer", "preference", "style", "practical", "concise", "detailed",
        "technical", "format", "tone", "answer", "response",
    },
    MemoryCategory.EXPERTISE: {
        "experience", "skill", "language", "python", "typescript", "react", "fastapi",
        "backend", "frontend", "expert", "intermediate", "beginner", "knowledge",
    },
}

# Queries that should explicitly suppress unrelated personal background
PURE_KNOWLEDGE_PATTERNS = [
    re.compile(r"^(?:explain|what is|how does|define|summarize)\b", re.IGNORECASE),
    re.compile(r"^(?:hello|hey|hi|good morning|how are you|what'?s up)\b", re.IGNORECASE),
]


def extract_keywords(text: str) -> Set[str]:
    """Tokenizes text into normalized keywords without stopwords."""
    words = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


class MemoryRetriever:
    """
    Selects relevant memories for a given user query.
    Enforces that casual or pure academic queries do not get polluted
    with irrelevant career or life goals.
    """

    def is_pure_knowledge_query(self, query: str) -> bool:
        """Checks if a query is a pure conceptual/factual or greeting question."""
        stripped = query.strip()
        for pattern in PURE_KNOWLEDGE_PATTERNS:
            if pattern.search(stripped):
                # But if the query mentions personal words like "my", "i am", "mine", allow memory
                if any(k in extract_keywords(stripped) for k in ["my", "i", "mine", "project", "startup"]):
                    return False
                return True
        return False

    def score_memory(self, query: str, memory_item: MemoryItem) -> float:
        """
        Calculates a relevance score between 0.0 and 1.0 for a memory given a query.
        """
        query_lower = query.lower()
        memory_lower = memory_item.memory.lower()

        query_keywords = extract_keywords(query)
        memory_keywords = extract_keywords(memory_item.memory)

        if not query_keywords:
            return 0.0

        # Direct word overlap
        overlap = query_keywords.intersection(memory_keywords)
        overlap_score = len(overlap) / max(1, len(query_keywords))

        # Check topic cluster affinity
        cluster = TOPIC_CLUSTERS.get(memory_item.category, set())
        cluster_overlap = query_keywords.intersection(cluster)
        cluster_score = len(cluster_overlap) * 0.35

        # Substring mentions (e.g. startup in both query and memory)
        bonus_score = 0.0
        for kw in query_keywords:
            if kw in memory_lower:
                bonus_score += 0.2

        total_score = overlap_score + cluster_score + bonus_score

        # Weight by memory importance (1 to 5)
        importance_multiplier = 0.8 + (memory_item.importance * 0.1)
        final_score = total_score * importance_multiplier

        return final_score

    def retrieve(
        self,
        query: str,
        memories: List[MemoryItem],
        min_relevance_score: float = 0.30,
        limit: int = 5,
    ) -> List[MemoryItem]:
        """
        Filters and ranks memories, returning only those exceeding the relevance threshold.
        """
        if not memories or not query.strip():
            return []

        # If it's a pure explanation like "explain binary search", do NOT inject personal career goals
        if self.is_pure_knowledge_query(query):
            # Only allow PREFERENCE category memories if they describe response styling
            preference_memories = [
                m for m in memories
                if m.category == MemoryCategory.PREFERENCE
                and any(k in m.memory.lower() for k in ["concise", "simple", "detailed", "practical", "technical"])
            ]
            return preference_memories[:2]

        scored: List[Tuple[float, MemoryItem]] = []
        for mem in memories:
            score = self.score_memory(query, mem)
            if score >= min_relevance_score:
                scored.append((score, mem))

        # Sort by relevance score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [m for _, m in scored[:limit]]

        logger.debug(
            f"[MEMORY RETRIEVER] Query: '{query[:40]}' - Evaluated {len(memories)} memories, "
            f"retrieved {len(relevant)} relevant."
        )
        return relevant


# Global singleton instance
memory_retriever = MemoryRetriever()
