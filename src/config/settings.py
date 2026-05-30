"""Configuration settings for LinkedIn scraper."""

import logging
import os
from typing import Optional

# LinkedIn Credentials — provide via CLI flags or the LINKEDIN_EMAIL /
# LINKEDIN_PASSWORD env vars. Never hardcode real credentials here.
EMAIL = os.getenv("LINKEDIN_EMAIL")
PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# Search Configuration
SEARCH_TEXT = os.getenv("LINKEDIN_SEARCH_TEXT", "Data Scientist")
MAX_SCROLL_ATTEMPTS = 20

# Browser Configuration
HEADLESS = os.getenv("LINKEDIN_HEADLESS", "false").lower() == "true"
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080

# Persistent Firefox profile — keeps the LinkedIn session (cookies, localStorage)
# alive between runs so login.py only needs to run once. Override with
# LINKEDIN_FIREFOX_PROFILE if you want the profile stored elsewhere.
FIREFOX_PROFILE_DIR = os.getenv(
    "LINKEDIN_FIREFOX_PROFILE",
    os.path.expanduser("~/.linkedin-scraper/firefox_profile"),
)

# Timing Configuration
MIN_SLEEP_TIME = 1
MAX_SLEEP_TIME = 4
WEBDRIVER_WAIT_TIMEOUT = 10  # seconds

# Anti-Detection Configuration
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# File Configuration
OUTPUT_XLSX_FILENAME = "linkedin_jobs.xlsx"
OUTPUT_COLUMNS = ["content", "profile_name", "profile_url", "hiring_post"]

MODEL_NAME = "gemma4:e4b"

# Ollama remote host. Leave as None/empty to run Ollama locally (auto-install + pull).
# Set to e.g. "http://server:11434" to use a remote Ollama API.
# The OLLAMA_HOST env var overrides this default.
OLLAMA_HOST = "http://10.135.14.18:11434" #os.getenv("OLLAMA_HOST", "").strip() or None

LOG_LEVEL_NAME = os.getenv("LINKEDIN_LOG_LEVEL", "INFO").upper()
LOG_FORMAT_DEFAULT = os.getenv(
    "LINKEDIN_LOG_FORMAT",
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

def configure_logging(level: Optional[int] = None, fmt: Optional[str] = None) -> None:
    """Configure application-wide logging."""
    logging.basicConfig(level=level or LOG_LEVEL, format=fmt or LOG_FORMAT_DEFAULT)

PROMPT_HIRING_POST = (
    "You are a classifier for LinkedIn posts. Decide whether a post is announcing an open role in the data / AI / ML domain.\n"
    "\n"
    "Return classification = 1 ONLY IF BOTH conditions hold:\n"
    "  (A) The post is a hiring/recruitment announcement — a company or recruiter is advertising an open role, "
    "asking candidates to apply, sharing a job description with responsibilities/requirements, or explicitly "
    "saying \"we're hiring\", \"now hiring\", \"open position\", \"apply here\", etc.\n"
    "  (B) The role is in data science, AI, machine learning, or an adjacent technical domain. Qualifying titles include "
    "(non-exhaustive):\n"
    "      - Data Scientist, Data Analyst, Data Engineer, Analytics Engineer\n"
    "      - Machine Learning Engineer, ML Researcher, Applied Scientist, Research Scientist (AI/ML)\n"
    "      - AI Engineer, AI Researcher, GenAI Engineer, LLM Engineer, Prompt Engineer\n"
    "      - Agentic AI Engineer / Developer, AI Agent Engineer\n"
    "      - MLOps Engineer, ML Platform / ML Infra Engineer, AI Platform Engineer\n"
    "      - Computer Vision Engineer, NLP Engineer, Speech / Audio AI Engineer\n"
    "      - Deep Learning Engineer, Reinforcement Learning Engineer\n"
    "\n"
    "Return classification = 0 if ANY of these are true:\n"
    "  - The post is NOT a hiring announcement (e.g., personal update like \"I just joined X\", industry commentary, "
    "thought-leadership, motivational/career advice, product launch, model/paper release, event or course promotion).\n"
    "  - The post IS a hiring announcement but for a role OUTSIDE the data/AI/ML domain "
    "(e.g., generic software/frontend/backend engineer with no AI scope, sales, marketing, HR, finance, ops, design).\n"
    "  - The post discusses AI/ML topics without recruiting anyone.\n"
    "  - Ambiguous referral asks (\"DM me if interested\") without an actual described role in the AI/ML domain.\n"
    "\n"
    "Borderline guidance:\n"
    "  - A hybrid role that includes ML responsibilities (e.g., \"Backend engineer working on our ML platform\") counts as 1.\n"
    "  - Internships and contract roles in the AI/ML domain count as 1.\n"
    "  - Reposts/referrals that clearly describe an AI/ML role count as 1.\n"
    "\n"
    "Output format — respond with EXACTLY one of these, and nothing else:\n"
    '{"classification": 1}\n'
    '{"classification": 0}\n'
    "\n"
    "Hard rules:\n"
    "  - The value must be the integer 1 or 0 (not the strings \"1\"/\"0\", not true/false).\n"
    "  - Do NOT include any explanation, reasoning, preamble, or markdown code fences.\n"
    "  - Do NOT add any keys beyond \"classification\".\n"
)