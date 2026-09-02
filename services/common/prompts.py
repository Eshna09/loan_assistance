"""
prompts.py
The RAG prompt template, owned by the orchestration layer.

Kept separate from any single service so the exact wording used in the notebook
stays reviewable in one place.
"""

CONTEXT_SEPARATOR = "\n---\n"
FALLBACK_PHRASE = "This information is not available in my knowledge base."


def build_rag_prompt(context_string: str, question: str) -> str:
    """Assemble the grounded prompt: persona, constraints, context, question."""
    return (
        "You are an educational loan knowledge assistant.\n"
        "Answer the user's question ONLY using the provided context.\n"
        "Do not invent information.\n"
        "If the answer cannot be found in the context, say:\n"
        f"'{FALLBACK_PHRASE}'\n"
        "This system provides general educational loan information and is not personalized lending, legal, tax, or financial advice.\n"
        "\n"
        f"Context:\n{context_string}\n"
        "\n"
        f"Question:\n{question}\n"
        "\n"
        "Answer:"
    )
