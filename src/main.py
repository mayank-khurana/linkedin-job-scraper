"""Scrape loop: pull LinkedIn posts on an interval and append them to Excel.

Classification runs in a separate process — see src/classify.py.
"""

import argparse
import logging
import os
import time
from typing import Dict, List, Optional

import pandas as pd

from src.config.settings import OUTPUT_COLUMNS, OUTPUT_XLSX_FILENAME, configure_logging
from src.scrape import LinkedInJobScraper


logger = logging.getLogger(__name__)


def _load_existing_excel() -> pd.DataFrame:
    """Read the Excel workbook if present; fall back to an empty frame with canonical columns."""
    if not os.path.exists(OUTPUT_XLSX_FILENAME):
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    try:
        df = pd.read_excel(OUTPUT_XLSX_FILENAME)
    except Exception as e:
        logger.warning("Could not read %s (%s); starting fresh", OUTPUT_XLSX_FILENAME, e)
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    if df.empty and not list(df.columns):
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def save_posts_to_excel(posts: List[Dict[str, str]]) -> pd.DataFrame:
    """Append scraped posts to OUTPUT_XLSX_FILENAME (creates the file with headers if missing or blank)."""
    if not posts:
        logger.warning("No posts provided for Excel export")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df_new = pd.DataFrame(posts)
    for col in OUTPUT_COLUMNS:
        if col not in df_new.columns:
            df_new[col] = pd.NA
    df_new = df_new[OUTPUT_COLUMNS]

    df_existing = _load_existing_excel()
    df_combined = pd.concat([df_existing, df_new], ignore_index=True)[OUTPUT_COLUMNS]

    try:
        df_combined.to_excel(OUTPUT_XLSX_FILENAME, index=False)
        logger.info("Wrote %s posts to %s (total now %s)", len(df_new), OUTPUT_XLSX_FILENAME, len(df_combined))
    except Exception as e:
        logger.error("Failed to save to Excel: %s", e)
    return df_combined


def run_pipeline(
    email: Optional[str],
    password: Optional[str],
    search_text: Optional[str],
    max_scroll_attempts: Optional[int],
    interval_hours: float,
    headless: Optional[bool] = None,
    skip_sort_by_latest: bool = False,
) -> None:
    """Scrape posts in a loop, saving each batch to CSV between waits."""
    configure_logging()
    scraper = LinkedInJobScraper(
        email=email,
        password=password,
        search_text=search_text,
        max_scroll_attempts=max_scroll_attempts,
        headless=headless,
        skip_sort_by_latest=skip_sort_by_latest,
    )
    logger.info("Scraper ready (search='%s', interval=%.2fh)", scraper.search_text, interval_hours)

    interval_seconds = int(interval_hours * 3600)

    try:
        iteration = 0
        while True:
            iteration += 1
            logger.info("=" * 80)
            logger.info("Starting scrape iteration #%s", iteration)
            logger.info("=" * 80)

            try:
                posts = scraper.run()
                if posts:
                    save_posts_to_excel(posts)
                    logger.info("Iteration #%s collected %s posts", iteration, len(posts))
                else:
                    logger.warning("Iteration #%s collected no posts", iteration)
            except Exception as e:
                logger.error("Error during iteration #%s: %s", iteration, e, exc_info=True)

            logger.info(
                "Waiting %.1fh (%.0f min) until next iteration… (Ctrl+C to stop)",
                interval_hours, interval_hours * 60,
            )

            # Chunk the sleep so KeyboardInterrupt fires quickly.
            sleep_chunks = max(60, int(interval_seconds / 60))
            chunk_duration = interval_seconds / sleep_chunks
            for i in range(sleep_chunks):
                time.sleep(chunk_duration)
                if i % 10 == 0:
                    remaining_minutes = (sleep_chunks - i - 1) * (chunk_duration / 60)
                    logger.debug("Waiting… %d minutes remaining", int(remaining_minutes))

    except KeyboardInterrupt:
        logger.info("\n%s\nKeyboard interrupt received. Shutting down gracefully…\n%s", "=" * 80, "=" * 80)
    finally:
        scraper.close()
        logger.info("Scraper shutdown complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinkedIn post scraper (loop)")
    parser.add_argument("--email", type=str, required=True, help="LinkedIn email")
    parser.add_argument("--password", type=str, required=True, help="LinkedIn password")
    parser.add_argument("--search_text", type=str, required=True, help="Search query")
    parser.add_argument("--max_scroll_attempts", type=int, default=20, help="Max scroll attempts per iteration")
    parser.add_argument("--interval", type=float, default=0.5, help="Hours between iterations")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument(
        "--skip_sort_by_latest",
        action="store_true",
        help="Skip sorting Posts by 'Latest'; use LinkedIn's default 'Top match' order",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    run_pipeline(
        email=args.email,
        password=args.password,
        search_text=args.search_text,
        max_scroll_attempts=args.max_scroll_attempts,
        interval_hours=args.interval,
        headless=args.headless,
        skip_sort_by_latest=args.skip_sort_by_latest,
    )


if __name__ == "__main__":
    main()
