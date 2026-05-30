"""Classify scraped LinkedIn posts as hiring-related using Ollama.

Reads OUTPUT_XLSX_FILENAME, runs inference on rows where `hiring_post` is missing,
and writes the file back in place. Idempotent: re-running only classifies new rows.
"""

import logging
import os
import sys

import pandas as pd
from tqdm import tqdm

from src.config.settings import (
    MODEL_NAME,
    OLLAMA_HOST,
    OUTPUT_COLUMNS,
    OUTPUT_XLSX_FILENAME,
    PROMPT_HIRING_POST,
    configure_logging,
)
from src.dataclass import HiringPost
from src.ollama_setup import OllamaModelSetup


logger = logging.getLogger(__name__)


def classify_excel(xlsx_path: str = OUTPUT_XLSX_FILENAME) -> None:
    """Classify every row in `xlsx_path` that lacks a `hiring_post` value."""
    if not os.path.exists(xlsx_path):
        logger.info("Excel file not found, creating %s with canonical columns", xlsx_path)
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_excel(xlsx_path, index=False)
        return

    try:
        df = pd.read_excel(xlsx_path)
    except Exception as e:
        logger.error("Could not read %s (%s)", xlsx_path, e)
        sys.exit(1)

    if df.empty and not list(df.columns):
        logger.info("Excel file is blank, writing canonical columns to %s", xlsx_path)
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_excel(xlsx_path, index=False)
        return

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[OUTPUT_COLUMNS]

    if "content" not in df.columns:
        logger.error("Excel missing 'content' column: %s", xlsx_path)
        sys.exit(1)

    before = len(df)
    df = df.drop_duplicates(subset="content", keep="first").reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %s duplicate rows by content (kept first)", dropped)
        df.to_excel(xlsx_path, index=False)

    pending_mask = df["hiring_post"].isna() & df["content"].notna()
    pending_idx = df.index[pending_mask].tolist()

    if not pending_idx:
        logger.info("Nothing to classify — every row already has hiring_post")
        return

    logger.info("Classifying %s of %s rows in %s", len(pending_idx), len(df), xlsx_path)

    ollama = OllamaModelSetup(model_name=MODEL_NAME, host=OLLAMA_HOST)

    for idx in tqdm(pending_idx, desc="Classifying"):
        content = df.at[idx, "content"]
        try:
            result = ollama.inference(text=content, prompt=PROMPT_HIRING_POST, schema=HiringPost)
            df.at[idx, "hiring_post"] = result.classification
        except Exception as e:
            logger.error("Inference failed for row %s: %s", idx, e)

    df.to_excel(xlsx_path, index=False)
    logger.info("Wrote %s rows back to %s", len(df), xlsx_path)


def main() -> None:
    configure_logging()
    classify_excel()


if __name__ == "__main__":
    main()
