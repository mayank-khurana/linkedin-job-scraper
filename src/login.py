"""One-shot LinkedIn login that persists the session in the Firefox profile.

Run this once (and again whenever LinkedIn invalidates the session — typically
after a password change, a suspicious-activity prompt, or several weeks idle):

    uv run python -m src.login --email <e> --password <p>

After it finishes, `python -m src.main ...` reuses the saved profile and skips
login entirely, so you don't re-authenticate every iteration.

The profile lives at FIREFOX_PROFILE_DIR (override via LINKEDIN_FIREFOX_PROFILE).
"""

import argparse
import logging

from src.config.settings import FIREFOX_PROFILE_DIR, configure_logging
from src.scrape import LinkedInJobScraper


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist a LinkedIn login in the Firefox profile.")
    parser.add_argument("--email", type=str, default=None, help="LinkedIn email (defaults to LINKEDIN_EMAIL / settings)")
    parser.add_argument("--password", type=str, default=None, help="LinkedIn password (defaults to LINKEDIN_PASSWORD / settings)")
    parser.add_argument("--profile_dir", type=str, default=FIREFOX_PROFILE_DIR, help="Firefox profile directory")
    # Always run headed so the user can solve CAPTCHA / 2FA if LinkedIn prompts.
    parser.add_argument("--headless", action="store_true", help="Run headless (not recommended — CAPTCHA may need a real window)")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    scraper = LinkedInJobScraper(
        email=args.email,
        password=args.password,
        search_text="",  # unused when login_only=True
        headless=args.headless,
        profile_dir=args.profile_dir,
        login_only=True,
    )
    try:
        logger.info("Login complete. Profile saved at %s", args.profile_dir)
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
