"""Configuration settings for LinkedIn scraper."""

import logging
import os
from typing import Optional

# Search Configuration
SEARCH_TEXT = "Data Scientist"
MAX_SCROLL_ATTEMPTS = 20
MAX_POSTS = 10

# Timing Configuration
MIN_SLEEP_TIME = 1
MAX_SLEEP_TIME = 4
WEBDRIVER_WAIT_TIMEOUT = 10  # seconds
RUN_INTERVAL = 1800  # seconds (30 minutes)

# File Configuration
OUTPUT_CSV_FILENAME = "linkedin_jobs.csv"
CSV_FIELDNAMES = ["content", "url", "profile_name"]

# Location Data
INDIAN_CITIES = [
    "mumbai",
    "delhi",
    "bangalore",
    "hyderabad",
    "chennai",
    "kolkata",
    "pune",
    "ahmedabad",
    "noida",
    "gurgaon",
    "bengaluru"
]

# Job-related Keywords for Filtering
JOB_KEYWORDS = [
    r"hiring",
    r"opening",
    r"opportunity",
    r"position",
    r"job",
    r"career",
    r"vacancy",
    r"recruitment",
    r"apply",
    r"experience required",
    r"skills required",
    r"role",
    r"responsibilities",
    r"qualifications",
    r"immediate joining",
    r"urgent hiring",
    r"job description"
]

MODEL_NAME = "deepseek-r1:1.5b"

LOG_LEVEL_NAME = os.getenv("LINKEDIN_LOG_LEVEL", "INFO").upper()
LOG_FORMAT_DEFAULT = os.getenv(
    "LINKEDIN_LOG_FORMAT",
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

def configure_logging(level: Optional[int] = None, format: Optional[str] = None) -> None:
    """Configure application-wide logging."""
    logging.basicConfig(level=level or LOG_LEVEL, format=format or LOG_FORMAT_DEFAULT)

PROMPT_NAMES_CLASSIFICATION = (
    "Classify the following text as an Indian name or not. "
    "Output your answer in the following structured JSON format:\n\n"
    "{\n  \"classification\": 0 or 1\n}\n\n"
    "Rules:\n"
    "- Respond with \"classification\": 0 if the text is clearly not an Indian name.\n"
    "- Respond with \"classification\": 1 if the text is an Indian name, cannot be classified, or appears to be an organization name.\n"
    "Strictly provide only the JSON output above without any extra explanation or text."
)

PROMPT_HIRING_POST = (
    "You will be given the content of a LinkedIn post. Analyze the post and determine if it is related to hiring, job postings, or recruitment activities. "
    "A hiring post generally refers to announcements or advertisements about job openings, available positions, recruitment drives, or opportunities that seek candidates. "
    "\n\n"
    "Instructions:\n"
    "1. Carefully review the LinkedIn post provided.\n"
    "2. Decide if it can be considered a hiring/recruitment-related post based on keywords, intent, and context.\n"
    "3. Output your result strictly in the following JSON format:\n"
    "{\n"
    '  "classification": 1 or 0\n'
    "}\n"
    "\nRules:\n"
    "- Respond with \"classification\": 1 if the post is a hiring/recruitment post.\n"
    "- Respond with \"classification\": 0 if the post is not related to hiring or recruitment.\n"
    "- Do NOT include any explanation, extra text, or context; only reply with the JSON as shown above.\n"
)