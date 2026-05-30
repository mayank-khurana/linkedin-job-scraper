"""
LinkedIn Job Scraper Module.

This module provides functionality to scrape job postings from LinkedIn
by searching posts, extracting relevant job information, and saving to CSV.
"""

import logging
import os
import random
import re
import time
import unicodedata
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.config.settings import (
    EMAIL,
    PASSWORD,
    SEARCH_TEXT,
    MAX_SCROLL_ATTEMPTS,
    MIN_SLEEP_TIME,
    MAX_SLEEP_TIME,
    WEBDRIVER_WAIT_TIMEOUT,
    HEADLESS,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    USER_AGENTS,
    FIREFOX_PROFILE_DIR,
)

# Constants
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"

# CSS/XPath Selectors
SELECTORS = {
    "email_field": (By.XPATH, "(//input[@type='email'])[2]"),
    "password_field": (By.XPATH, "(//input[@type='password'])[2]"),
    "search_bar": (By.CSS_SELECTOR, "input[data-testid='typeahead-input']"),
    "posts_tab": [
        (By.CSS_SELECTOR, "div[aria-label='Filter by Posts'] label"),
        (By.CSS_SELECTOR, "div[aria-label='Filter by Posts']"),
    ],
    "sort_by_button": (By.CSS_SELECTOR, "div[aria-label='Filter by Sort by'] label"),
    "latest_option": [
        (By.CSS_SELECTOR, "div[role='radio'][aria-label='Latest']"),
        (By.XPATH, "//div[@role='radio' and (@aria-label='Latest' or normalize-space()='Latest')]"),
        (By.XPATH, "//label[normalize-space()='Latest']"),
        (By.XPATH, "//span[normalize-space()='Latest']/ancestor::label[1]"),
        (By.XPATH, "//span[normalize-space()='Latest']/ancestor::*[@role='radio'][1]"),
        (By.XPATH, "//input[@type='radio' and (@value='date_posted' or @value='DATE_POSTED')]"),
    ],
    "show_results": (By.XPATH, "//span[normalize-space()='Show results']"),
    "post_containers": [
        (By.XPATH, "//div[h2/span[normalize-space()='Feed post']]"),
    ],
    "post_content": "span[data-testid='expandable-text-box']",
    "post_actor_title": "div[aria-label]",
}

logger = logging.getLogger(__name__)


# Zero-width spaces, BOM, bidi marks — invisible but break diffs and dedup.
_INVISIBLE_RE = re.compile(r"[​-\u200F\u202A-\u202E⁠-⁯﻿]")
# C0/C1 control characters except \t and \n.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def clean_post_text(text: str) -> str:
    """Normalize post text: kill garbage characters, collapse extra whitespace, keep [text](url) links intact."""
    if not text:
        return ""
    # NFKC maps Unicode "mathematical bold" letters (𝗪𝗲'𝗿𝗲 𝗵𝗶𝗿𝗶𝗻𝗴) and other
    # presentation-form characters back to plain ASCII so dedup and the LLM see the same string.
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    # Collapse runs of spaces/tabs (but not newlines).
    text = re.sub(r"[ \t]+", " ", text)
    # Strip leading/trailing horizontal whitespace on each line.
    text = re.sub(r" *\n *", "\n", text)
    # Collapse 3+ consecutive newlines down to a single paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _ensure_int(value, default: int, name: str = "max_scroll_attempts") -> int:
    """Coerce a scroll-attempt count to ``int``.

    The value can arrive from argparse, config, or a stray single-element
    sequence, so we tolerate those shapes and fall back to ``default`` when the
    value can't be converted.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 1:
        logger.warning("%s is a sequence (%s), extracting first element", name, type(value).__name__)
        return int(value[0])
    if isinstance(value, (tuple, list)) and len(value) > 1:
        logger.error("%s is a sequence with multiple elements (%s), using first element", name, value)
        return int(value[0])
    try:
        logger.warning("%s is not an integer (%s), converting to int", name, type(value).__name__)
        return int(value)
    except (ValueError, TypeError) as e:
        logger.error("Cannot convert %s (%s) to int: %s. Using default %s", name, value, e, default)
        return default


class LinkedInJobScraper:
    """
    A scraper for extracting job postings from LinkedIn.

    This class handles authentication, navigation, and extraction of job-related
    posts from LinkedIn's search results.

    Attributes:
        email (str): LinkedIn email for authentication
        password (str): LinkedIn password for authentication
        search_text (str): Search query text
        max_scroll_attempts (int): Maximum number of scroll attempts
        driver (webdriver): Selenium WebDriver instance
        wait (WebDriverWait): WebDriverWait instance for explicit waits
    """

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        search_text: Optional[str] = None,
        max_scroll_attempts: Optional[int] = None,
        headless: Optional[bool] = None,
        profile_dir: Optional[str] = None,
        login_only: bool = False,
        skip_sort_by_latest: bool = False,
    ):
        """
        Initialize the LinkedInJobScraper instance.

        Args:
            email: LinkedIn email (defaults to config EMAIL)
            password: LinkedIn password (defaults to config PASSWORD)
            search_text: Search query text (defaults to config SEARCH_TEXT)
            max_scroll_attempts: Maximum scroll attempts (defaults to config MAX_SCROLL_ATTEMPTS)
            headless: Run browser in headless mode (defaults to config HEADLESS)
            profile_dir: Persistent Firefox profile directory (defaults to config FIREFOX_PROFILE_DIR).
                         Reusing this across runs keeps the LinkedIn session alive.
            login_only: If True, log in and stop (skip search navigation). Used by src/login.py.
            skip_sort_by_latest: If True, leave LinkedIn's default "Top match" sort in place
                                 instead of switching the Posts results to "Latest".
        """
        self.email = email or EMAIL
        self.password = password or PASSWORD
        self.search_text = search_text or SEARCH_TEXT
        self.headless = headless if headless is not None else HEADLESS
        self.profile_dir = profile_dir or FIREFOX_PROFILE_DIR
        self.login_only = login_only
        self.skip_sort_by_latest = skip_sort_by_latest
        raw_scroll = max_scroll_attempts if max_scroll_attempts is not None else MAX_SCROLL_ATTEMPTS
        self.max_scroll_attempts = _ensure_int(raw_scroll, default=MAX_SCROLL_ATTEMPTS)

        self.driver: Optional[webdriver.Firefox] = None
        self.wait: Optional[WebDriverWait] = None

        logger.info(
            "Initialized LinkedInJobScraper with search='%s', max_scroll=%s, headless=%s",
            self.search_text,
            self.max_scroll_attempts,
            self.headless,
        )
        self._initialize()

    def setup_driver(self) -> webdriver.Firefox:
        """
        Initialize and configure the Selenium WebDriver with anti-detection measures.

        Returns:
            Firefox WebDriver instance
        """
        logger.debug("Setting up Firefox WebDriver (headless=%s, wait_timeout=%s)", self.headless, WEBDRIVER_WAIT_TIMEOUT)
        
        # Configure Firefox options
        options = webdriver.FirefoxOptions()
        
        # Headless mode
        if self.headless:
            options.add_argument("--headless")
            logger.info("Running in headless mode")

        # Persistent profile — Firefox stores cookies/localStorage here, which is what
        # keeps the LinkedIn session alive across runs. The directory must exist.
        if self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True)
            options.add_argument("-profile")
            options.add_argument(self.profile_dir)
            logger.info("Using persistent Firefox profile: %s", self.profile_dir)

        # Anti-detection: Set a random user agent
        user_agent = random.choice(USER_AGENTS)
        options.set_preference("general.useragent.override", user_agent)
        logger.debug("Using user agent: %s", user_agent[:50] + "...")
        
        # Anti-detection: Disable WebDriver flag
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        
        # Anti-detection: Privacy and tracking preferences
        options.set_preference("privacy.trackingprotection.enabled", False)
        options.set_preference("privacy.trackingprotection.socialtracking.enabled", False)
        
        # Anti-detection: Disable automation indicators
        options.set_preference("marionette", True)
        
        # Performance optimizations
        options.set_preference("browser.cache.disk.enable", False)
        options.set_preference("browser.cache.memory.enable", False)
        options.set_preference("browser.cache.offline.enable", False)
        options.set_preference("network.http.use-cache", False)
        
        # Disable images for faster loading (optional - can be commented out if images are needed)
        # options.set_preference("permissions.default.image", 2)
        
        # Initialize driver
        self.driver = webdriver.Firefox(options=options)
        
        # Set window size (important for consistent rendering in headless mode)
        self.driver.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Anti-detection: Execute JavaScript to hide WebDriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Anti-detection: Add additional JavaScript overrides
        self.driver.execute_cdp_cmd = lambda *args, **kwargs: None  # Disable CDP
        
        self.wait = WebDriverWait(self.driver, WEBDRIVER_WAIT_TIMEOUT)
        logger.debug("Firefox WebDriver setup complete")
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

            # After successful login, LinkedIn redirects to https://www.linkedin.com/feed/.
            # (The DOM uses obfuscated rotating class names, so URL-based detection is more
            # stable than waiting for a specific nav element.)
            self.wait.until(EC.url_contains("/feed/"))
            logger.info("LinkedIn login successful (landed on %s)", self.driver.current_url)
            return True

        except Exception:
            logger.exception("Login failed during authentication")
            try:
                logger.error("Current URL after login attempt: %s", self.driver.current_url)
                logger.error("Page title: %s", self.driver.title)
                snapshot_path = "/tmp/linkedin_login_failure.html"
                with open(snapshot_path, "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.error("Saved page source to %s", snapshot_path)
            except Exception:
                logger.exception("Could not capture post-failure debug info")
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

            if self.skip_sort_by_latest:
                logger.info("Skipping 'Latest' sort — using LinkedIn's default 'Top match' order")
            elif not self._configure_sorting():
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
            raw_scroll = max_scroll_attempts if max_scroll_attempts is not None else self.max_scroll_attempts
            scroll_attempts = _ensure_int(raw_scroll, default=self.max_scroll_attempts)

            logger.info("Starting scrape cycle (max_scroll=%s)", scroll_attempts)
            self.driver.maximize_window()
            fetched_posts: List[Dict[str, str]] = []
            seen_contents = set()
            body = self.driver.find_element(By.TAG_NAME, "body")

            self._scroll_page(body, scroll_attempts)
            posts = self._find_post_elements()

            if not posts:
                logger.warning("No posts found on page")
                return []

            for post_element in posts:
                post_data = self.extract_post_details(post_element)

                if not post_data or post_data["content"] in seen_contents:
                    continue

                seen_contents.add(post_data["content"])
                fetched_posts.append(post_data)
                logger.debug("Queued post #%s by %s", len(fetched_posts), post_data["profile_name"])

            logger.info("Scraping completed; collected %s posts", len(fetched_posts))
            return fetched_posts

        except Exception:
            logger.exception("Error encountered during scraping")
            return []

    def extract_post_details(self, post_element) -> Optional[Dict[str, str]]:
        """
        Extract relevant details from a post element.

        Args:
            post_element: Selenium WebElement representing a LinkedIn post

        Returns:
            Dictionary with 'content', 'profile_name', and 'profile_url' keys, or None on error
        """
        try:
            # Image/video/poll posts have no text container — skip them quietly.
            content_elements = post_element.find_elements(
                By.CSS_SELECTOR, SELECTORS["post_content"],
            )
            if not content_elements:
                logger.debug("Skipping post with no text content (likely media-only)")
                return None
            content_element = content_elements[0]
            # element.text only yields visible rendered text, dropping <a href> URLs
            # (hashtags, profile mentions, external links). Walk the DOM in JS to
            # preserve URLs inline as markdown-style [text](url).
            content = self.driver.execute_script(
                """
                function extract(el) {
                    let out = '';
                    for (const node of el.childNodes) {
                        if (node.nodeType === 3) {
                            out += node.textContent;
                        } else if (node.nodeType === 1) {
                            const tag = node.tagName.toUpperCase();
                            if (tag === 'BR') {
                                out += '\\n';
                            } else if (tag === 'A') {
                                const href = node.getAttribute('href') || '';
                                const text = node.textContent.trim();
                                const isHashtag = href.includes('HASH_TAG_FROM_FEED');
                                if (!href || href === text || isHashtag) {
                                    out += text;
                                } else {
                                    out += `[${text}](${href})`;
                                }
                            } else {
                                out += extract(node);
                            }
                        }
                    }
                    return out;
                }
                return extract(arguments[0]).trim();
                """,
                content_element,
            )

            content = clean_post_text(content)
            if not content:
                return None

            name_elements = post_element.find_elements(
                By.CSS_SELECTOR, SELECTORS["post_actor_title"],
            )
            if not name_elements:
                logger.debug("Skipping post with no actor element")
                return None
            name_element = name_elements[0]
            # New SDUI: actor wrapper exposes "<NAME>, <SUBTITLE> <CONNECTION>" as aria-label.
            aria_label = name_element.get_attribute("aria-label") or ""
            profile_name = aria_label.split(",")[0].strip() or name_element.text.split("\n")[0].strip()

            profile_url = ""
            try:
                link_element = name_element.find_element(
                    By.XPATH, "./ancestor::a[contains(@href, '/in/')][1]",
                )
                href = link_element.get_attribute("href") or ""
                profile_url = href.split("?")[0]
            except NoSuchElementException:
                logger.debug("No profile URL found for post by %s", profile_name)

            return {
                "content": content,
                "profile_name": profile_name,
                "profile_url": profile_url,
            }
        except Exception:
            logger.exception("Error extracting post details")
            return None

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
        Initialize the scraper: setup driver, login if needed, and navigate to search.

        If the persistent profile already has a valid LinkedIn session, login is
        skipped entirely. When `login_only` is True, navigation to search is also
        skipped (used by src/login.py to populate the profile once).
        """
        logger.debug("Beginning scraper initialization sequence")
        self.setup_driver()
        self.random_sleep()
        if self._is_logged_in():
            logger.info("Reusing existing LinkedIn session from profile %s", self.profile_dir)
        else:
            logger.info("No active session — performing login")
            self.login()
            self.random_sleep()
            if self.login_only:
                # Auto-login may fail (account picker, CAPTCHA, 2FA, "is this you?"
                # prompts). Block here so the user can click through manually before
                # we close the browser and lose the cookies.
                self.wait_for_login_completion()
                self.random_sleep()
        if self.login_only:
            logger.info("login_only=True; skipping search navigation")
            return
        self.navigate_to_search()
        self.random_sleep()

    def _is_logged_in(self) -> bool:
        """
        Check whether the saved profile already has a valid LinkedIn session.

        The `li_at` cookie is LinkedIn's primary session token — URL alone is
        unreliable because the account-picker / checkpoint pages can contain
        "/feed" or redirect through it.
        """
        try:
            self.driver.get("https://www.linkedin.com/feed/")
            self.random_sleep(15, 20)  # Wait for potential redirects and cookie setting
            current_url = self.driver.current_url
            li_at = self.driver.get_cookie("li_at")
            login_markers = ("/login", "/checkpoint", "/authwall", "/uas", "/m/login")
            looks_like_login = any(m in current_url for m in login_markers)
            if li_at and li_at.get("value") and not looks_like_login:
                logger.debug("Existing session detected (URL: %s)", current_url)
                return True
            logger.debug("No active session (URL: %s, li_at=%s)", current_url, bool(li_at))
            return False
        except Exception:
            logger.exception("Error while probing existing session state")
            return False

    def wait_for_login_completion(self, timeout: int = 300) -> bool:
        """
        Block until LinkedIn drops the `li_at` session cookie or `timeout` expires.

        Used by login_only mode so the user has time to click through any manual
        step LinkedIn throws up (account picker, CAPTCHA, 2FA, "is this you?")
        before the browser closes and the profile is finalized.
        """
        logger.info(
            "Waiting up to %ss for login to complete in the browser window... "
            "(complete any account picker / CAPTCHA / 2FA prompts now)",
            timeout,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                cookie = self.driver.get_cookie("li_at")
                current_url = self.driver.current_url or ""
                if cookie and cookie.get("value") and "/feed" in current_url:
                    logger.info("Login detected (URL: %s)", current_url)
                    return True
            except Exception:
                logger.debug("Session probe failed; will retry", exc_info=True)
            time.sleep(2)
        logger.error("Timed out waiting for manual login to complete")
        return False

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

            latest_option = None
            for selector_tuple in SELECTORS["latest_option"]:
                try:
                    latest_option = self.wait.until(
                        EC.element_to_be_clickable(selector_tuple)
                    )
                    logger.debug("'Latest' option located using selector %s", selector_tuple)
                    break
                except TimeoutException:
                    logger.debug("'Latest' selector %s not found, trying next", selector_tuple)
                    continue

            if latest_option is None:
                snapshot_path = "/tmp/linkedin_sort_dropdown.html"
                try:
                    with open(snapshot_path, "w", encoding="utf-8") as f:
                        f.write(self.driver.page_source)
                    logger.error(
                        "Could not find 'Latest' option with any selector — saved page source to %s",
                        snapshot_path,
                    )
                except Exception:
                    logger.exception("Could not save sort-dropdown snapshot")
                return False

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
        scroll_attempts = _ensure_int(scroll_attempts, default=20, name="scroll_attempts")

        # LinkedIn's SDUI renders the feed inside a virtual scroll container; the
        # window itself doesn't grow, so window.scrollBy is a no-op. Scrolling the
        # last rendered post into view triggers the loader regardless of which
        # element is the actual scroll parent.
        for attempt in range(scroll_attempts):
            count = self.driver.execute_script(
                """
                const posts = document.querySelectorAll('div[componentkey^="expanded"]');
                if (posts.length > 0) {
                    posts[posts.length - 1].scrollIntoView({block: 'end'});
                } else {
                    window.scrollTo(0, document.body.scrollHeight);
                }
                return posts.length;
                """
            )
            logger.debug("Scroll attempt %s/%s — %s posts loaded", attempt + 1, scroll_attempts, count)
            self.random_sleep()

    def _find_post_elements(self) -> List:
        """
        Find post elements using multiple CSS selectors.

        Tries each selector until posts are found.

        Returns:
            List of WebElements representing posts
        """
        posts: List = []
        for by, value in SELECTORS["post_containers"]:
            logger.debug("Searching for posts using selector: %s %s", by, value)
            posts = self.driver.find_elements(by, value)
            if posts:
                logger.debug("Found %s posts with selector (%s, %s)", len(posts), by, value)
                break
        return posts