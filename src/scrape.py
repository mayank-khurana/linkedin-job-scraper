"""
LinkedIn Job Scraper Module.

This module provides functionality to scrape job postings from LinkedIn
by searching posts, extracting relevant job information, and saving to CSV.
"""

import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import csv
import os
import re
from typing import Optional, Dict, List
from src.config.settings import (
    MAX_SCROLL_ATTEMPTS,
    MIN_SLEEP_TIME,
    MAX_SLEEP_TIME,
    WEBDRIVER_WAIT_TIMEOUT,
    RUN_INTERVAL,
    INDIAN_CITIES,
    JOB_KEYWORDS,
)

# Constants
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_POST_BASE_URL = "https://www.linkedin.com/feed/update/"

# CSS/XPath Selectors
SELECTORS = {
    "email_field": (By.ID, "username"),
    "password_field": (By.ID, "password"),
    "global_nav": (By.ID, "global-nav"),
    "search_bar": (By.CSS_SELECTOR, "input.search-global-typeahead__input"),
    "posts_tab": [
        (By.XPATH, "//a[contains(text(), 'Posts')]"),
        (By.XPATH, "//a[contains(text(), 'See all post')]"),
    ],
    "sort_by_button": (By.XPATH, "//button[contains(., 'Sort by')]"),
    "latest_option": (By.XPATH, "//span[contains(., 'Latest')]"),
    "show_results": (
        By.XPATH,
        "//button[contains(normalize-space(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')), 'show results')]",
    ),
    "post_containers": [
        "div.feed-shared-update-v2",
        "div.update-components-actor",
        "div[data-urn^='urn:li:activity']",
    ],
    "post_content": "span.break-words",
    "post_actor_title": "span.update-components-actor__title",
}

logger = logging.getLogger(__name__)


class LinkedInJobScraper:
    """
    A scraper for extracting job postings from LinkedIn.

    This class handles authentication, navigation, and extraction of job-related
    posts from LinkedIn's search results. It includes filtering logic to identify
    job postings and saves results to a CSV file.

    Attributes:
        email (str): LinkedIn email for authentication
        password (str): LinkedIn password for authentication
        search_text (str): Search query text
        max_scroll_attempts (int): Maximum number of scroll attempts
        driver (webdriver): Selenium WebDriver instance
        wait (WebDriverWait): WebDriverWait instance for explicit waits
        indian_cities (set): Set of Indian city names for filtering
        job_keywords (list): List of regex patterns for job keywords
        job_pattern (Pattern): Compiled regex pattern for job detection
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        search_text: Optional[str] = None,
        max_scroll_attempts: Optional[int] = None,
    ):
        """
        Initialize the LinkedInJobScraper instance.

        Args:
            email: LinkedIn email (defaults to config EMAIL)
            password: LinkedIn password (defaults to config PASSWORD)
            search_text: Search query text (defaults to config SEARCH_TEXT)
            max_scroll_attempts: Maximum scroll attempts (defaults to config MAX_SCROLL_ATTEMPTS)
        """
        self.email = email
        self.password = password
        self.search_text = search_text
        # Ensure max_scroll_attempts is an integer
        scroll_attempts = max_scroll_attempts if max_scroll_attempts is not None else MAX_SCROLL_ATTEMPTS
        if not isinstance(scroll_attempts, int):
            if isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) == 1:
                logger.warning("max_scroll_attempts is a sequence (%s), extracting first element", type(scroll_attempts).__name__)
                scroll_attempts = int(scroll_attempts[0])
            elif isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) > 1:
                logger.error("max_scroll_attempts is a sequence with multiple elements (%s), using first element", scroll_attempts)
                scroll_attempts = int(scroll_attempts[0])
            else:
                try:
                    logger.warning("max_scroll_attempts is not an integer (%s), converting to int", type(scroll_attempts).__name__)
                    scroll_attempts = int(scroll_attempts)
                except (ValueError, TypeError) as e:
                    logger.error("Cannot convert max_scroll_attempts (%s) to int: %s. Using default value %s", scroll_attempts, e, MAX_SCROLL_ATTEMPTS)
                    scroll_attempts = MAX_SCROLL_ATTEMPTS
        self.max_scroll_attempts = scroll_attempts

        self.driver: Optional[webdriver.Firefox] = None
        self.wait: Optional[WebDriverWait] = None

        self.indian_cities = set(INDIAN_CITIES)
        self.job_keywords = JOB_KEYWORDS
        self.job_pattern = re.compile("|".join(self.job_keywords), re.IGNORECASE)

        logger.info(
            "Initialized LinkedInJobScraper with search='%s' and max_scroll=%s",
            self.search_text,
            self.max_scroll_attempts,
        )
        self._initialize()

    def setup_driver(self) -> webdriver.Firefox:
        """
        Initialize and configure the Selenium WebDriver.

        Returns:
            Firefox WebDriver instance
        """
        logger.debug("Setting up Firefox WebDriver with wait timeout %s", WEBDRIVER_WAIT_TIMEOUT)
        self.driver = webdriver.Firefox()
        self.wait = WebDriverWait(self.driver, WEBDRIVER_WAIT_TIMEOUT)
        return self.driver

    def random_sleep(
        self,
        min_time: Optional[float] = None,
        max_time: Optional[float] = None,
    ) -> None:
        """
        Add random delay to avoid detection by LinkedIn.

        Args:
            min_time: Minimum sleep time in seconds (defaults to config MIN_SLEEP_TIME)
            max_time: Maximum sleep time in seconds (defaults to config MAX_SLEEP_TIME)
        """
        min_time = min_time or MIN_SLEEP_TIME
        max_time = max_time or MAX_SLEEP_TIME
        delay = random.uniform(min_time, max_time)
        logger.debug("Sleeping for %.2f seconds", delay)
        time.sleep(delay)

    def login(self) -> bool:
        """
        Handle LinkedIn login process.

        Returns:
            True if login successful, False otherwise
        """
        try:
            logger.info("Navigating to LinkedIn login page")
            self.driver.get(LINKEDIN_LOGIN_URL)
            self.random_sleep()

            email_field = self.wait.until(
                EC.presence_of_element_located(SELECTORS["email_field"])
            )
            email_field.send_keys(self.email)

            password_field = self.wait.until(
                EC.presence_of_element_located(SELECTORS["password_field"])
            )
            password_field.send_keys(self.password)
            password_field.send_keys(Keys.RETURN)

            self.wait.until(EC.presence_of_element_located(SELECTORS["global_nav"]))
            logger.info("LinkedIn login successful")
            return True

        except (TimeoutException, Exception):
            logger.exception("Login failed during authentication")
            return False

    def navigate_to_search(self) -> bool:
        """
        Navigate to search results and configure filters.

        Sets up search query, navigates to Posts tab, sorts by latest,
        and applies filters.

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info("Navigating to search results for '%s'", self.search_text)
            self._perform_search()
            self.random_sleep()

            if not self._navigate_to_posts_tab():
                return False

            self.random_sleep()

            if not self._configure_sorting():
                return False

            logger.debug("Search results ready for scraping")
            return True

        except Exception:
            logger.exception("Navigation to search results failed")
            return False

    def scrape_posts(
        self,
        max_scroll_attempts: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Main function to scrape posts from the current page.

        Scrolls the page, finds post elements, extracts details,
        filters for relevant posts, and saves incrementally.

        Args:
            max_scroll_attempts: Maximum number of scroll attempts
                                (defaults to instance max_scroll_attempts)

        Returns:
            List of dictionaries containing post data, or empty list on error
        """
        try:
            scroll_attempts = max_scroll_attempts if max_scroll_attempts is not None else self.max_scroll_attempts
            # Ensure scroll_attempts is an integer
            if not isinstance(scroll_attempts, int):
                if isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) == 1:
                    logger.warning("max_scroll_attempts is a sequence (%s), extracting first element", type(scroll_attempts).__name__)
                    scroll_attempts = int(scroll_attempts[0])
                elif isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) > 1:
                    logger.error("max_scroll_attempts is a sequence with multiple elements (%s), using first element", scroll_attempts)
                    scroll_attempts = int(scroll_attempts[0])
                else:
                    try:
                        logger.warning("max_scroll_attempts is not an integer (%s), converting to int", type(scroll_attempts).__name__)
                        scroll_attempts = int(scroll_attempts)
                    except (ValueError, TypeError) as e:
                        logger.error("Cannot convert max_scroll_attempts (%s) to int: %s. Using instance value %s", scroll_attempts, e, self.max_scroll_attempts)
                        scroll_attempts = self.max_scroll_attempts

            logger.info("Starting scrape cycle (max_scroll=%s)", scroll_attempts)
            self.driver.maximize_window()
            fetched_posts: List[Dict[str, str]] = []
            processed_urls = set()
            body = self.driver.find_element(By.TAG_NAME, "body")

            self._scroll_page(body, scroll_attempts)
            posts = self._find_post_elements()

            if not posts:
                logger.warning("No posts found on page")
                return []

            for post_element in posts:
                post_data = self.extract_post_details(post_element)

                if not post_data or post_data["url"] in processed_urls:
                    continue

                processed_urls.add(post_data["url"])
                fetched_posts.append(post_data)
                logger.debug("Queued post #%s: %s", len(fetched_posts), post_data["url"])

            logger.info("Scraping completed; collected %s posts", len(fetched_posts))
            return fetched_posts

        except Exception:
            logger.exception("Error encountered during scraping")
            return []

    def save_to_csv(self, posts: List[Dict[str, str]], filename: str) -> None:
        """
        Save posts to CSV file in append mode.

        Creates the file with headers if it doesn't exist.

        Args:
            posts: List of dictionaries containing post data
            filename: Path to CSV file
        """
        file_exists = os.path.exists(filename)

        with open(filename, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            writer.writerows(posts)
        logger.info("Appended %s posts to %s", len(posts), filename)

    def extract_post_details(self, post_element) -> Optional[Dict[str, str]]:
        """
        Extract relevant details from a post element.

        Args:
            post_element: Selenium WebElement representing a LinkedIn post

        Returns:
            Dictionary with 'content', 'url', and 'name' keys, or None on error
        """
        try:
            content_element = post_element.find_element(
                By.CSS_SELECTOR, SELECTORS["post_content"],
            )
            content = content_element.text.strip()

            if not content:
                return None

            name_element = post_element.find_element(
                By.CSS_SELECTOR, SELECTORS["post_actor_title"],
            )
            profile_name = name_element.text.split("\n")[0].strip()

            data_urn = post_element.get_attribute("data-urn")
            post_url = f"{LINKEDIN_POST_BASE_URL}{data_urn}" if data_urn else None

            if not post_url:
                return None

            logger.debug("Extracted post details for %s", post_url)
            return {
                "content": content,
                "url": post_url,
                "profile_name": profile_name,
            }
        except (NoSuchElementException, Exception):
            logger.exception("Error extracting post details")
            return None

    def is_job_post(self, content: str) -> bool:
        """
        Determine if the content represents a job posting.

        Uses pattern matching and keyword detection to identify job postings.
        Requires at least 2 job-related indicators to confirm.

        Args:
            content: Text content to analyze

        Returns:
            True if content appears to be a job posting, False otherwise
        """
        if not content:
            return False

        if not self.job_pattern.search(content):
            return False

        has_requirements = re.search(
            r"requirements?|qualifications?", content, re.IGNORECASE
        )
        has_experience = re.search(
            r"\d+\+?\s*years?|years? of experience", content, re.IGNORECASE
        )
        has_apply_action = re.search(
            r"apply|send|email|dm|interested|opportunity", content, re.IGNORECASE
        )

        content_lower = content.lower()
        indicators = sum(
            [
                bool(has_requirements),
                bool(has_experience),
                bool(has_apply_action),
                "resume" in content_lower,
                "cv" in content_lower,
                "position" in content_lower,
                "role" in content_lower,
            ]
        )

        return indicators >= 2

    def is_relevant_post(self, post_data: Optional[Dict]) -> bool:
        """
        Filter posts based on relevance criteria.

        Currently filters only for job postings. Can be extended to include
        location-based filtering (e.g., Indian cities, relocation opportunities).

        Args:
            post_data: Dictionary containing post data

        Returns:
            True if post is relevant, False otherwise
        """
        if not post_data:
            return False

        content = post_data.get("content", "").lower()
        return self.is_job_post(content)

    def run(self) -> List[Dict[str, str]]:
        """
        Main execution function.

        Refreshes the page and runs the scraping process.
        """
        self.driver.refresh()
        logger.debug("Browser refreshed; starting scrape run")
        posts = self.scrape_posts(self.max_scroll_attempts)
        logger.info("Scrape run collected %s posts", len(posts))
        return posts
    def close(self) -> None:
        """
        Close the WebDriver and cleanup resources.
        """
        if self.driver:
            logger.info("Closing WebDriver session")
            self.driver.quit()
            self.driver = None
            self.wait = None

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """
        Initialize the scraper: setup driver, login, and navigate to search.

        This method orchestrates the initial setup sequence with delays
        between steps to avoid detection.
        """
        logger.debug("Beginning scraper initialization sequence")
        self.setup_driver()
        self.random_sleep()
        self.login()
        self.random_sleep()
        self.navigate_to_search()
        self.random_sleep()

    def _perform_search(self) -> None:
        """Perform the search query."""
        logger.debug("Submitting search query: %s", self.search_text)
        search_bar = self.wait.until(
            EC.presence_of_element_located(SELECTORS["search_bar"])
        )
        search_bar.send_keys(self.search_text)
        search_bar.send_keys(Keys.RETURN)

    def _navigate_to_posts_tab(self) -> bool:
        """
        Navigate to the Posts tab in search results.

        Tries multiple selectors to find the Posts tab.

        Returns:
            True if successful, False otherwise
        """
        posts_tab = None
        for selector_tuple in SELECTORS["posts_tab"]:
            try:
                posts_tab = self.wait.until(
                    EC.element_to_be_clickable(selector_tuple)
                )
                logger.debug("Posts tab located using selector %s", selector_tuple)
                break
            except TimeoutException:
                logger.debug("Posts tab selector %s not found", selector_tuple)
                continue

        if posts_tab:
            posts_tab.click()
            return True

        logger.warning("Could not find Posts tab")
        return False

    def _configure_sorting(self) -> bool:
        """
        Configure sorting to show latest posts first.

        Returns:
            True if successful, False otherwise
        """
        try:
            sort_by_button = self.wait.until(
                EC.element_to_be_clickable(SELECTORS["sort_by_button"])
            )
            sort_by_button.click()
            self.random_sleep()

            latest_option = self.wait.until(
                EC.element_to_be_clickable(SELECTORS["latest_option"])
            )
            latest_option.click()

            show_results = self.wait.until(
                EC.element_to_be_clickable(SELECTORS["show_results"])
            )
            show_results.click()

            logger.debug("Applied 'Latest' sorting to search results")
            return True
        except TimeoutException:
            logger.exception("Failed to configure sorting to 'Latest'")
            return False

    def _scroll_page(self, body_element, scroll_attempts: int) -> None:
        """
        Scroll the page to load more content.
        Uses JavaScript scrolling which works even when window is in background.

        Args:
            body_element: Body element to scroll (kept for compatibility)
            scroll_attempts: Number of times to scroll
        """
        # Ensure scroll_attempts is an integer
        if not isinstance(scroll_attempts, int):
            if isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) == 1:
                logger.warning("scroll_attempts is a sequence (%s), extracting first element", type(scroll_attempts).__name__)
                scroll_attempts = int(scroll_attempts[0])
            elif isinstance(scroll_attempts, (tuple, list)) and len(scroll_attempts) > 1:
                logger.error("scroll_attempts is a sequence with multiple elements (%s), using first element", scroll_attempts)
                scroll_attempts = int(scroll_attempts[0])
            else:
                try:
                    logger.warning("scroll_attempts is not an integer (%s), converting to int", type(scroll_attempts).__name__)
                    scroll_attempts = int(scroll_attempts)
                except (ValueError, TypeError) as e:
                    logger.error("Cannot convert scroll_attempts (%s) to int: %s. Using default value 20", scroll_attempts, e)
                    scroll_attempts = 20
        
        # Use JavaScript scrolling - this works even when window doesn't have focus
        # This is the key fix for background operation
        for attempt in range(scroll_attempts):
            logger.debug("Scroll attempt %s/%s", attempt + 1, scroll_attempts)
            # JavaScript scrolling doesn't require window focus
            self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            self.random_sleep()

    def _find_post_elements(self) -> List:
        """
        Find post elements using multiple CSS selectors.

        Tries each selector until posts are found.

        Returns:
            List of WebElements representing posts
        """
        posts: List = []
        for selector in SELECTORS["post_containers"]:
            logger.debug("Searching for posts using selector: %s", selector)
            posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if posts:
                logger.debug("Found %s posts with selector %s", len(posts), selector)
                break
        return posts


def scrape_jobs() -> None:
    """Main entry point for running the scraper in a loop."""
    scraper = LinkedInJobScraper()
    try:
        while True:
            posts = scraper.run()
            logger.info(
                "Waiting for the next interval (%s minutes)...", RUN_INTERVAL // 60
            )
            time.sleep(RUN_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Scraper interrupted by user")
    finally:
        scraper.close()


if __name__ == "__main__":
    scrape_jobs()

