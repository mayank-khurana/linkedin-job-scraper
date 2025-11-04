"""Pipeline entry for scraping LinkedIn posts and running model inference."""

import argparse
import logging
import os
import time
from typing import Dict, List, Optional

import pandas as pd
from tqdm import tqdm

from src.config.settings import (
    MODEL_NAME,
    OUTPUT_CSV_FILENAME,
    PROMPT_HIRING_POST,
    PROMPT_NAMES_CLASSIFICATION,
    configure_logging,
)
from src.dataclass import HiringPost, NamesClassification
from src.ollama_setup import OllamaModelSetup
from src.scrape import LinkedInJobScraper


logger = logging.getLogger(__name__)


class ScrapeAndClassify:
    """Coordinate scraping LinkedIn posts and running classification models."""

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        search_text: Optional[str] = None,
        max_scroll_attempts: Optional[int] = None,
    ) -> None:
        self.ollama_model_setup = OllamaModelSetup(model_name=MODEL_NAME)
        self.scraper = LinkedInJobScraper(
            email=email,
            password=password,
            search_text=search_text,
            max_scroll_attempts=max_scroll_attempts,
        )
        logger.info(
            "Initialized ScrapeAndClassify pipeline (search='%s', model='%s')",
            self.scraper.search_text,
            MODEL_NAME,
        )

    def scrape_jobs(self) -> List[Dict[str, str]]:
        """Scrape LinkedIn posts using the configured scraper."""
        logger.info("Starting LinkedIn scrape run")
        posts = self.scraper.run()
        logger.info("Scrape completed; retrieved %s posts", len(posts))
        return posts

    def classify_jobs(
        self,
        posts: Optional[List[Dict[str, str]]] = None,
        prompt: str = PROMPT_HIRING_POST,
    ) -> List[Dict[str, str]]:
        """Classify posts as hiring-related using the Ollama model."""
        if not posts:
            logger.warning("No posts available to classify for hiring intent")
            return posts or []

        logger.info("Classifying %s posts for hiring intent", len(posts))
        logger.debug("Sleeping 10 seconds before hiring classification to throttle requests")
        time.sleep(10)
        for index, post in tqdm(
            enumerate(posts), total=len(posts), desc="Classifying jobs"
        ):
            result = self.ollama_model_setup.inference(
                input=post["content"], prompt=prompt, format=HiringPost
            )
            posts[index]["hiring_post"] = result.classification
        logger.info("Hiring classification complete")
        return posts

    def classify_names(
        self,
        posts: Optional[List[Dict[str, str]]] = None,
        prompt: str = PROMPT_NAMES_CLASSIFICATION,
    ) -> List[Dict[str, str]]:
        """Classify profile names using the Ollama model."""
        if not posts:
            logger.warning("No posts available to classify names")
            return posts or []

        logger.info("Classifying profile names for %s posts", len(posts))
        logger.debug("Sleeping 10 seconds before name classification to throttle requests")
        time.sleep(10)
        for index, post in tqdm(
            enumerate(posts), total=len(posts), desc="Classifying names"
        ):
            result = self.ollama_model_setup.inference(
                input=post["profile_name"], prompt=prompt, format=NamesClassification
            )
            posts[index]["names_classification"] = result.classification
        logger.info("Name classification complete")
        return posts

    def save_posts_to_csv(self, posts: Optional[List[Dict[str, str]]] = None) -> pd.DataFrame:
        """Persist processed posts to disk by appending to the CSV if it exists."""
        if not posts:
            logger.warning("No posts provided for CSV export")
            return pd.DataFrame()

        df_new = pd.DataFrame(posts)
        try:
            if os.path.exists(OUTPUT_CSV_FILENAME):
                df_existing = pd.read_csv(OUTPUT_CSV_FILENAME)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                df_combined.to_csv(OUTPUT_CSV_FILENAME, index=False)
                logger.info("Appended %s posts to %s (total now %s)", len(df_new), OUTPUT_CSV_FILENAME, len(df_combined))
                return df_combined
            else:
                df_new.to_csv(OUTPUT_CSV_FILENAME, index=False)
                logger.info("Saved %s posts to %s", len(df_new), OUTPUT_CSV_FILENAME)
                return df_new
        except Exception as e:
            logger.error("Failed to save to CSV: %s", str(e))
            return df_new

    def shutdown(self) -> None:
        """Release underlying resources."""
        logger.debug("Shutting down scraper resources")
        self.scraper.close()


def run_pipeline(
    email: Optional[str],
    password: Optional[str],
    search_text: Optional[str],
    max_scroll_attempts: Optional[int],
    interval_hours: Optional[float]
) -> pd.DataFrame:
    """
    Execute the scrape and classification pipeline end-to-end in a loop.
    
    Args:
        email: LinkedIn email address
        password: LinkedIn password
        search_text: Search query text
        max_scroll_attempts: Maximum scroll attempts
        interval_hours: Hours to wait between iterations (default: 1.0 hour)
    """
    configure_logging()
    pipeline = ScrapeAndClassify(
        email=email,
        password=password,
        search_text=search_text,
        max_scroll_attempts=max_scroll_attempts,
    )
    
    # Convert hours to seconds
    INTERVAL_SECONDS = int(interval_hours * 3600)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            logger.info("=" * 80)
            logger.info("Starting pipeline iteration #%s", iteration)
            logger.info("=" * 80)
            
            try:
                posts = pipeline.scrape_jobs()
                if posts:
                    posts = pipeline.classify_jobs(posts=posts, prompt=PROMPT_HIRING_POST)
                    # posts = pipeline.classify_names(posts=posts, prompt=PROMPT_NAMES_CLASSIFICATION)
                    pipeline.save_posts_to_csv(posts=posts)
                    logger.info("Iteration #%s completed successfully. Collected %s posts", iteration, len(posts))
                else:
                    logger.warning("Iteration #%s completed but no posts were collected", iteration)
            except Exception as e:
                logger.error("Error during iteration #%s: %s", iteration, e, exc_info=True)
            
            logger.info("Waiting %.1f hour(s) (%.0f minutes) until next iteration... (Press Ctrl+C to stop)", 
                       interval_hours, interval_hours * 60)
            
            # Wait for specified interval before next iteration
            # Sleep in smaller chunks to allow faster interrupt response
            sleep_chunks = max(60, int(INTERVAL_SECONDS / 60))  # Check every minute, or adjust if interval is less than 1 hour
            chunk_duration = INTERVAL_SECONDS / sleep_chunks
            for i in range(sleep_chunks):
                time.sleep(chunk_duration)
                if i % 10 == 0:  # Log every 10 minutes
                    remaining_minutes = (sleep_chunks - i - 1) * (chunk_duration / 60)
                    logger.debug("Waiting... %d minutes remaining until next run", int(remaining_minutes))
        
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 80)
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
        logger.info("=" * 80)
    finally:
        pipeline.shutdown()
        logger.info("Pipeline shutdown complete")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the pipeline."""
    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper & Classifier")
    parser.add_argument("--email", type=str, required=True, help="LinkedIn Email Address")
    parser.add_argument("--password", type=str, required=True, help="LinkedIn Password")
    parser.add_argument("--search_text", type=str, required=True, help="Search Text")
    parser.add_argument(
        "--max_scroll_attempts",
        type=int,
        default=20,
        help="Max Scroll Attempts (optional)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Hours to wait between iterations (default: 1.0 hour)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry-point for the scrape-and-classify pipeline."""
    configure_logging()
    args = parse_args()
    run_pipeline(
        email=args.email,
        password=args.password,
        search_text=args.search_text,
        max_scroll_attempts=args.max_scroll_attempts,
        interval_hours=args.interval,
    )


if __name__ == "__main__":
    main()