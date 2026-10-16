"""Educational Search & Resource Discovery Service for Mentor AI Copilot."""

import re
from typing import Any

from app.schemas.copilot import EducationalResource

# Verified Authoritative Educational Catalog for High-Frequency Academic Subjects
VERIFIED_EDUCATIONAL_CATALOG: dict[str, list[dict[str, Any]]] = {
    "math_101": [
        {
            "title": "MIT OpenCourseWare: Single Variable Calculus (18.01SC)",
            "url": "https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/",
            "platform": "MIT OpenCourseWare",
            "topic": "Calculus & Foundational Mathematics (Math 101)",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Comprehensive college calculus course covering derivatives, integrals, and applications with video lectures and practice problems.",
            "why_recommended": "Gold-standard university foundation for STEM students taught by Prof. David Jerison.",
        },
        {
            "title": "Khan Academy: College Calculus 1 & Precalculus",
            "url": "https://www.khanacademy.org/math/calculus-1",
            "platform": "Khan Academy",
            "topic": "Calculus & Limits (Math 101)",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Interactive step-by-step video lessons, practice exercises, and mastery quizzes for Calculus 1.",
            "why_recommended": "Intuitive visual explanations with immediate feedback, ideal for exam revision.",
        },
        {
            "title": "3Blue1Brown: Essence of Calculus",
            "url": "https://www.youtube.com/playlist?list=PLZHQObOWTQDMsr9K-rj53DwVRMYO3t5Yr",
            "platform": "YouTube (3Blue1Brown)",
            "topic": "Calculus Intuition & Geometry",
            "difficulty": "All Levels",
            "is_free": True,
            "description": "Visual geometric series that builds deep intuitive understanding of limits, derivatives, and the fundamental theorem.",
            "why_recommended": "Best visual explanations in mathematics to build conceptual confidence.",
        },
    ],
    "dfa": [
        {
            "title": "Neso Academy: Theory of Computation — Deterministic Finite Automata (DFA)",
            "url": "https://www.youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY64ZgK992j_Op",
            "platform": "YouTube (Neso Academy)",
            "topic": "Theory of Computation & Formal Languages",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Complete, structured video playlist explaining DFA definitions, transition diagrams, formal tuples, and state minimization.",
            "why_recommended": "The most widely recommended tutorial for undergraduate CS students studying automata.",
        },
        {
            "title": "Stanford Online: Automata and Formal Languages",
            "url": "https://online.stanford.edu/courses/soe-ycscs1-automata-theory",
            "platform": "Stanford Online",
            "topic": "Automata Theory (CS 154)",
            "difficulty": "Intermediate",
            "is_free": True,
            "description": "Rigorous treatment of finite automata, regular expressions, context-free grammars, and Turing machines by Prof. Jeffrey Ullman.",
            "why_recommended": "Authoritative university curriculum by the co-author of the classic Dragon book.",
        },
        {
            "title": "GeeksforGeeks: Introduction to Deterministic Finite Automata (DFA)",
            "url": "https://www.geeksforgeeks.org/introduction-of-finite-automata/",
            "platform": "GeeksforGeeks",
            "topic": "Automata Theory Reference",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Clear textual notes with transition tables, step-by-step example strings, and common gate/exam practice questions.",
            "why_recommended": "Great for quick revision of formal 5-tuple definitions and transition diagrams.",
        },
    ],
    "python": [
        {
            "title": "Official Python 3 Documentation & Tutorial",
            "url": "https://docs.python.org/3/tutorial/",
            "platform": "Python Software Foundation",
            "topic": "Python Programming",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "The official beginner tutorial directly from the creators of Python covering data structures, control flow, functions, and modules.",
            "why_recommended": "Primary source documentation that avoids outdated syntax and establishes standard idioms.",
        },
        {
            "title": "CS50P: CS50's Introduction to Programming with Python",
            "url": "https://cs50.harvard.edu/python/",
            "platform": "Harvard CS50 / edX",
            "topic": "Python Programming Foundations",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Harvard's world-renowned introductory course taught by David J. Malan, covering programming logic, testing, libraries, and best practices.",
            "why_recommended": "Exceptional pedagogical production value, clear problem sets, and supportive community.",
        },
        {
            "title": "freeCodeCamp: Python for Beginners Full Course",
            "url": "https://www.youtube.com/watch?v=eWRfhZUzrAc",
            "platform": "YouTube (freeCodeCamp)",
            "topic": "Python Programming",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Complete hands-on crash course covering variables, loops, object-oriented programming, and file I/O with practical exercises.",
            "why_recommended": "Zero-prerequisite, code-along format that gets beginners writing functional code immediately.",
        },
    ],
    "fastapi": [
        {
            "title": "FastAPI Official Documentation & Tutorial",
            "url": "https://fastapi.tiangolo.com/tutorial/",
            "platform": "Official Documentation",
            "topic": "Python Web API Development",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Award-winning, interactive documentation by Sebastián Ramírez with live code examples, OpenAPI schema docs, and dependency injection guides.",
            "why_recommended": "Widely regarded as the single best framework documentation in the modern Python ecosystem.",
        },
        {
            "title": "freeCodeCamp: Python API Development - Comprehensive FastAPI Course",
            "url": "https://www.youtube.com/watch?v=0sOvCWFmrtA",
            "platform": "YouTube (freeCodeCamp)",
            "topic": "REST APIs, SQLAlchemy, Postgres, JWT Auth",
            "difficulty": "Intermediate",
            "is_free": True,
            "description": "Full 19-hour curriculum building production-grade asynchronous REST APIs with Postgres, SQLAlchemy, Pydantic, and Docker.",
            "why_recommended": "Teaches the exact modern stack used in production applications including Mentor AI.",
        },
    ],
    "database_normalization": [
        {
            "title": "Database Normalization (1NF, 2NF, 3NF, BCNF) - Caleb Curry",
            "url": "https://www.youtube.com/watch?v=UrYLYV7WSHM",
            "platform": "YouTube (Caleb Curry)",
            "topic": "Relational Database Design",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Step-by-step video breakdown of database anomalies, functional dependencies, and normal forms from 1NF through BCNF.",
            "why_recommended": "Uses simple, relatable real-world table examples to demystify complex normalization rules.",
        },
        {
            "title": "PostgreSQL Official Documentation: Data Definition & Foreign Keys",
            "url": "https://www.postgresql.org/docs/current/ddl.html",
            "platform": "PostgreSQL Documentation",
            "topic": "Relational Schema Design & Constraints",
            "difficulty": "Intermediate",
            "is_free": True,
            "description": "Authoritative guide on table schemas, primary keys, foreign key constraints, and relational integrity.",
            "why_recommended": "Essential technical reference for implementing normalized schemas in production relational databases.",
        },
    ],
    "algorithms": [
        {
            "title": "MIT OpenCourseWare: Introduction to Algorithms (6.006)",
            "url": "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/",
            "platform": "MIT OpenCourseWare",
            "topic": "Data Structures & Algorithms",
            "difficulty": "Intermediate",
            "is_free": True,
            "description": "Classic MIT course covering sorting, trees, hashing, dynamic programming, and graph algorithms by Prof. Erik Demaine.",
            "why_recommended": "The definitive university algorithms curriculum for computer science and engineering majors.",
        },
        {
            "title": "NeetCode: Algorithms and Data Structures for Beginners",
            "url": "https://neetcode.io/courses/dsa-for-beginners",
            "platform": "NeetCode",
            "topic": "Practical Problem Solving & Coding Prep",
            "difficulty": "Beginner",
            "is_free": True,
            "description": "Concise visual diagrams and clean code walkthroughs for core data structures, binary search, and recursion.",
            "why_recommended": "Direct, practical visual explanations tailored for technical interviews and coursework.",
        },
    ],
}


class EducationalSearchService:
    """Discovers and recommends authoritative educational resources."""

    @classmethod
    def is_educational_query(cls, text: str) -> bool:
        """Verify whether a query is strictly educational in nature."""
        lower = text.lower()
        # Non-educational intent patterns
        non_educational = [
            r"\b(buy|flight|hotel|ticket|shoes|sneakers|pizza|restaurant|shopping|deal|discount|movie|crypto|betting)\b",
            r"\b(hire|job\s+offer|celebrity|dating|lottery)\b",
        ]
        for pattern in non_educational:
            if re.search(pattern, lower):
                return False

        # Positive educational keywords
        educational_keywords = [
            "course", "tutorial", "video", "lecture", "learn", "study", "documentation",
            "docs", "explain", "how to", "concept", "subject", "guide", "book", "practice",
            "math", "dfa", "automata", "python", "fastapi", "algorithm", "database",
            "calculus", "physics", "chemistry", "biology", "computer science", "bhalo course",
            "porashona", "shikhte", "suggest", "recommend"
        ]
        return any(kw in lower for kw in educational_keywords)

    @classmethod
    def search_educational_resources(
        cls, query: str
    ) -> tuple[list[EducationalResource], str]:
        """Match query to authoritative verified educational materials.

        Returns:
            Tuple of (list of verified EducationalResource objects, rationale/topic label).
        """
        lower = query.lower()

        # 1. Math 101 / Calculus / Foundational Math
        if any(term in lower for term in ["math 101", "math101", "calculus", "differentiation", "integration", "math"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["math_101"]]
            return resources, "Math 101 & Calculus Foundations"

        # 2. DFA / Automata / Theory of Computation
        if any(term in lower for term in ["dfa", "automata", "theory of computation", "finite automata", "regular language", "nfa"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["dfa"]]
            return resources, "Deterministic Finite Automata (DFA) & Automata Theory"

        # 3. Python Tutorials / Foundations
        if any(term in lower for term in ["python", "python tutorial", "python beginner", "learn python"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["python"]]
            return resources, "Python Programming for Beginners"

        # 4. FastAPI Documentation & Guides
        if any(term in lower for term in ["fastapi", "fast api", "rest api python", "pydantic api"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["fastapi"]]
            return resources, "FastAPI Framework & Documentation"

        # 5. Database Normalization / SQL
        if any(term in lower for term in ["normalization", "database normalization", "1nf", "2nf", "3nf", "bcnf", "sql schema"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["database_normalization"]]
            return resources, "Relational Database Normalization"

        # 6. Algorithms & Data Structures
        if any(term in lower for term in ["algorithm", "data structure", "dsa", "sorting", "binary search", "graph"]):
            resources = [EducationalResource(**item) for item in VERIFIED_EDUCATIONAL_CATALOG["algorithms"]]
            return resources, "Algorithms & Data Structures"

        # Default fallback to high-quality academic platforms for general topics
        generic_resources = [
            EducationalResource(
                title=f"MIT OpenCourseWare: Computer Science & Mathematics",
                url="https://ocw.mit.edu/",
                platform="MIT OpenCourseWare",
                topic=query.capitalize(),
                difficulty="All Levels",
                is_free=True,
                description="Freely available MIT university course materials, lecture videos, notes, and exam archives.",
                why_recommended="Authoritative university curriculum accessible worldwide without cost.",
            ),
            EducationalResource(
                title=f"Khan Academy: Free Online Courses, Lessons & Practice",
                url="https://www.khanacademy.org/",
                platform="Khan Academy",
                topic=query.capitalize(),
                difficulty="Beginner",
                is_free=True,
                description="Interactive educational lessons and mastery exercises across mathematics, computing, and sciences.",
                why_recommended="Structured mastery-based learning suitable for concept reinforcement.",
            ),
            EducationalResource(
                title=f"freeCodeCamp: Interactive Coding & Technology Curriculum",
                url="https://www.freecodecamp.org/",
                platform="freeCodeCamp",
                topic=query.capitalize(),
                difficulty="Beginner",
                is_free=True,
                description="Comprehensive, verified project-based learning curriculum for programming and computer science.",
                why_recommended="Hands-on interactive practice with recognized completion certifications.",
            ),
        ]
        return generic_resources, f"Educational Resources for {query}"
