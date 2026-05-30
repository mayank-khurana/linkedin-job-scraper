"""Pydantic schemas that define the classifier's response contract.

The model's output is constrained to and validated against these schemas — see
`OllamaModelSetup.inference` in src/ollama_setup.py.
"""

from pydantic import BaseModel


class HiringPost(BaseModel):
    """Whether a post advertises an open data/AI/ML role: 1 (yes) or 0 (no)."""

    classification: int