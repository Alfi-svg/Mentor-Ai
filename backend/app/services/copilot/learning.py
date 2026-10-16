"""Student growth, programming education tutor policy, and 100-line code enforcement."""

import re

MAX_CODE_LINES_PER_EXAMPLE = 100


def count_code_block_lines(text: str) -> list[int]:
    """Find all code blocks and return the line count of each."""
    code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    line_counts = []
    for block in code_blocks:
        lines = [line for line in block.strip().split("\n") if line.strip()]
        line_counts.append(len(lines))
    return line_counts


def enforce_code_line_limits(text: str) -> tuple[str, int]:
    """Enforce the strict 100-line maximum per code example rule.

    If any code block exceeds MAX_CODE_LINES_PER_EXAMPLE (100 lines),
    it is bounded with an educational explanation encouraging modular learning.

    Returns:
        Tuple of (processed_text, max_line_count_observed).
    """
    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    max_lines_seen = 0

    def _replace_block(match: re.Match[str]) -> str:
        nonlocal max_lines_seen
        lang = match.group(1) or ""
        code = match.group(2).strip()
        lines = code.split("\n") if code else []
        line_count = len(lines)
        if line_count > max_lines_seen:
            max_lines_seen = line_count

        if line_count <= MAX_CODE_LINES_PER_EXAMPLE:
            return match.group(0)


        # Truncate to 100 lines with an educational guidance note
        bounded_lines = lines[:MAX_CODE_LINES_PER_EXAMPLE]
        note = (
            f"\n# ... [Mentor Educational Guardrail: Example focused to {MAX_CODE_LINES_PER_EXAMPLE} lines]\n"
            f"# To master this topic effectively, build the remaining components incrementally step by step."
        )
        bounded_code = "\n".join(bounded_lines) + note
        return f"```{lang}\n{bounded_code}\n```"

    processed = pattern.sub(_replace_block, text)
    return processed, max_lines_seen


def is_complete_project_request(prompt: str) -> bool:
    """Detect whether user is asking to build/generate a full application/project."""
    lower = prompt.lower()
    project_patterns = [
        r"\b(build|create|generate|write|make)\s+(me\s+)?(a\s+|an\s+)?(entire|full|complete|whole)\s+.*?\b(app|application|project|website|system|software|clone|saas)\b",
        r"\b(build\s+me\s+a\s+full-stack|create\s+a\s+complete\s+saas)\b",
        r"\b(code\s+the\s+whole\s+thing|give\s+me\s+all\s+the\s+code\s+for)\b",
    ]
    return any(re.search(p, lower) for p in project_patterns)



def generate_educational_project_roadmap(topic: str) -> str:
    """Provide an architectural roadmap instead of a monolithic code dump."""
    return f"""### Architecture & Learning Roadmap for {topic.title()}

As your educational copilot, I want to help you understand and build this project step by step rather than delivering an unexamined monolithic codebase. Here is the recommended engineering roadmap:

#### 1. Architecture Overview
- **Frontend / Client**: User interface, state management, and real-time interaction.
- **Backend / API**: RESTful / GraphQL endpoints, business logic validation, and authentication.
- **Database**: Relational schema (PostgreSQL) with foreign keys and normalization.

#### 2. Suggested Directory Structure
```
project/
├── backend/
│   ├── app/
│   │   ├── api/          # Route handlers & endpoints
│   │   ├── core/         # Config & security
│   │   ├── db/           # Models & migrations
│   │   └── services/     # Business logic
│   └── tests/
├── frontend/
│   ├── app/              # Next.js App Router pages
│   ├── components/       # Reusable UI widgets
│   └── lib/              # API clients & state
└── README.md
```

#### 3. Step-by-Step Implementation Strategy
1. **Milestone 1 — Data Modeling**: Define the core relational entities and apply database migrations.
2. **Milestone 2 — Core API Handlers**: Implement CRUD endpoints with request validation (Pydantic / Zod).
3. **Milestone 3 — Frontend Integration**: Connect API endpoints to user interface components.
4. **Milestone 4 — Testing & Verification**: Write unit tests for business logic edge cases.

Which specific component would you like us to explore and implement first?
"""
