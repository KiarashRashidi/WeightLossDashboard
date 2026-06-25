import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # exponential backoff in seconds


def generate_patient_report(prompt: str, data: str) -> str | None:
    """
    Calls the GapGPT API (OpenAI-compatible) to generate a patient report.
    Returns the report text, or None on failure (UI must show a Retry button).
    Implements exponential backoff for transient network errors.
    """
    from flask import current_app
    api_key = current_app.config.get("GAPGPT_API_KEY", "")

    if not api_key:
        logger.error("GAPGPT_API_KEY is not configured.")
        return None

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.gapgpt.app/v1",
    )

    for attempt in range(MAX_RETRIES):
        try:
            logger.info("GapGPT API call attempt %d/%d", attempt + 1, MAX_RETRIES)
            response = client.responses.create(
                model="gapgpt-qwen-3.5",
                input=f"{prompt}\nData: {data}",
            )
            text = response.output_text
            logger.info("GapGPT report generated successfully (%d chars).", len(text))
            return text

        except Exception as e:
            logger.error("GapGPT API Error (attempt %d): %s", attempt + 1, e, exc_info=True)
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)

    logger.error("GapGPT API failed after %d attempts.", MAX_RETRIES)
    return None
