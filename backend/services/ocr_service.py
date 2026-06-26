import base64
import io
import logging
import re

logger = logging.getLogger(__name__)


# ── Text parser (works with any OCR engine output) ──────────────────────────

def parse_scale_screenshot(text: str) -> dict:
    """
    Extract the five core fields from OCR'd scale-app text:
      weight, body_fat_pct, fat_mass, muscle_mass, water_pct
    BMI is excluded — the server computes it from height/weight.
    """
    result = {}
    text = re.sub(r"[ \t]+", " ", text)

    def _s(pattern, flags=re.IGNORECASE | re.DOTALL):
        return re.search(pattern, text, flags)

    # Weight
    m = _s(r"\bWEIGHT\b[\s\S]{0,100}?(\d+\.?\d*)\s*kg")
    if m:
        result["weight"] = float(m.group(1))

    # Body Fat % (label may or may not carry the % sign)
    m = _s(r"BODY\s+FAT\s*%[\s\S]{0,120}?(\d+\.?\d*)")
    if not m:
        m = _s(r"BODY\s+FAT(?!\s{0,5}MASS)[\s\S]{0,120}?(\d+\.?\d*)\s*%")
    if m:
        result["body_fat_pct"] = float(m.group(1))

    # Fat Mass (kg) — "BODY FAT MASS"
    m = _s(r"BODY\s+FAT\s+MASS[\s\S]{0,120}?(\d+\.?\d*)\s*kg")
    if m:
        result["fat_mass"] = float(m.group(1))

    # Muscle Mass (kg) — avoid matching "SKELETAL MUSCLE MASS"
    skel_idx = text.upper().find("SKELETAL")
    muscle_area = text[:skel_idx] if skel_idx >= 0 else text
    m = re.search(r"MUSCLE\s+MASS[\s\S]{0,120}?(\d+\.?\d*)\s*kg",
                  muscle_area, re.IGNORECASE | re.DOTALL)
    if m:
        result["muscle_mass"] = float(m.group(1))

    # Body Water %
    m = _s(r"\bWATER\b[\s\S]{0,100}?(\d+\.?\d*)\s*%")
    if m:
        result["water_pct"] = float(m.group(1))

    return result


# ── Image → text (EasyOCR, with Tesseract fallback) ─────────────────────────

def _preprocess(image_bytes: bytes):
    """Return a preprocessed PIL image ready for OCR."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = img.filter(ImageFilter.SHARPEN)

    w, h = img.size
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _easyocr_to_text(image_bytes: bytes) -> str:
    """Run EasyOCR and reconstruct a line-ordered plain-text string."""
    import numpy as np
    import easyocr

    img = _preprocess(image_bytes)
    img_array = np.array(img)

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    results = reader.readtext(img_array, detail=1)

    # Filter very low confidence detections
    results = [(bbox, txt, conf) for bbox, txt, conf in results if conf >= 0.25]

    # Sort top-to-bottom, then left-to-right
    results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

    # Group items whose top-y values are close into the same line
    h_px = img.size[1]
    threshold = max(h_px * 0.025, 20)

    lines: list[list[tuple]] = []  # each entry: list of (x, text)
    current: list[tuple] = []
    prev_y: float | None = None

    for bbox, txt, _conf in results:
        top_y = float(bbox[0][1])
        if prev_y is None or abs(top_y - prev_y) <= threshold:
            current.append((float(bbox[0][0]), txt))
            prev_y = top_y if prev_y is None else min(prev_y, top_y)
        else:
            if current:
                lines.append(sorted(current, key=lambda t: t[0]))
            current = [(float(bbox[0][0]), txt)]
            prev_y = top_y

    if current:
        lines.append(sorted(current, key=lambda t: t[0]))

    return "\n".join(" ".join(t for _, t in line) for line in lines)


def _tesseract_to_text(image_bytes: bytes) -> str:
    """Run pytesseract if the binary is installed."""
    import pytesseract

    # Common Windows install path
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    img = _preprocess(image_bytes).convert("L")
    return pytesseract.image_to_string(img, config="--oem 3 --psm 6")


def analyze_image(image_bytes: bytes) -> dict:
    """
    Extract body-composition measurements from a smart scale screenshot.
    Tries EasyOCR first, then pytesseract, then returns an error.
    """
    # ── Engine 1: EasyOCR (pure Python, no system binary needed) ─────────────
    try:
        text = _easyocr_to_text(image_bytes)
        logger.info("EasyOCR extracted %d chars", len(text))
        fields = parse_scale_screenshot(text)
        fields["_ocr_text"] = text
        return fields
    except ImportError:
        logger.warning("easyocr not installed, trying tesseract…")
    except Exception as exc:
        logger.exception("EasyOCR failed: %s", exc)

    # ── Engine 2: Tesseract (if binary is installed on Windows) ──────────────
    try:
        text = _tesseract_to_text(image_bytes)
        logger.info("Tesseract extracted %d chars", len(text))
        fields = parse_scale_screenshot(text)
        fields["_ocr_text"] = text
        return fields
    except ImportError:
        logger.warning("pytesseract not installed")
    except Exception as exc:
        err = str(exc)
        if "tesseract is not installed" in err or "not found" in err.lower():
            pass  # handled below
        else:
            logger.exception("Tesseract failed: %s", exc)

    return {
        "error": (
            "OCR engine not available. "
            "Fix: run  pip install easyocr  in the backend folder "
            "(one-time ~300 MB download), then restart the server."
        )
    }


def analyze_base64_image(data_url_or_b64: str) -> dict:
    """Analyze a base64-encoded image (with or without data-URL prefix)."""
    if "," in data_url_or_b64:
        data_url_or_b64 = data_url_or_b64.split(",", 1)[1]
    try:
        return analyze_image(base64.b64decode(data_url_or_b64))
    except Exception as e:
        return {"error": f"Failed to decode image: {e}"}
