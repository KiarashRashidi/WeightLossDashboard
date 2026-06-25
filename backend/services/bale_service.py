import base64
import io
import time
import logging
import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # exponential backoff in seconds


def register_webhook(bot_token: str, webhook_url: str) -> dict | None:
    """Registers (or re-registers) the webhook URL with Bale for the given bot token."""
    url = f"https://tapi.bale.ai/bot{bot_token}/setWebhook"
    try:
        response = requests.post(url, json={"url": webhook_url}, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get("ok"):
            logger.info("Bale webhook registered successfully: %s", webhook_url)
        else:
            logger.error("Bale setWebhook returned not-ok: %s", result)
        return result
    except requests.exceptions.RequestException as e:
        logger.error("Failed to register Bale webhook: %s", e, exc_info=True)
        return None


def get_webhook_info(bot_token: str) -> dict | None:
    """Returns current webhook info from Bale API."""
    url = f"https://tapi.bale.ai/bot{bot_token}/getWebhookInfo"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Failed to get Bale webhook info: %s", e, exc_info=True)
        return None


def send_bale_message(bot_token: str, chat_id: str, message: str) -> dict | None:
    """
    Sends a text message via the Bale Messenger API.
    Returns the API response dict on success, None on failure.
    Implements exponential backoff retries.
    """
    base_url = f"https://tapi.bale.ai/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(base_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Bale message successfully sent to %s", chat_id)
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Error sending Bale message to %s (attempt %d): %s",
                chat_id, attempt + 1, e, exc_info=True,
            )
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)

    logger.error("Bale sendMessage failed after %d attempts for chat_id=%s.", MAX_RETRIES, chat_id)
    return None


def send_bale_photo(bot_token: str, chat_id: str, image_base64: str, caption: str = "") -> dict | None:
    """
    Sends a photo (progress chart) via the Bale Messenger API.
    image_base64 is a base64-encoded PNG string.
    """
    base_url = f"https://tapi.bale.ai/bot{bot_token}/sendPhoto"
    image_bytes = base64.b64decode(image_base64)
    files = {"photo": ("chart.png", io.BytesIO(image_bytes), "image/png")}
    data = {"chat_id": chat_id, "caption": caption}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(base_url, data=data, files=files, timeout=15)
            response.raise_for_status()
            logger.info("Bale photo successfully sent to %s", chat_id)
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Error sending Bale photo to %s (attempt %d): %s",
                chat_id, attempt + 1, e, exc_info=True,
            )
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)

    logger.error("Bale sendPhoto failed after %d attempts for chat_id=%s.", MAX_RETRIES, chat_id)
    return None
