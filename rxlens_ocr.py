import re
from typing import List, Dict, Any

try:
    import cv2
    import pytesseract
    HAS_OCR_LIBS = True
except ImportError:
    HAS_OCR_LIBS = False


NOISE_PREFIXES = re.compile(
    r"^\s*(?:rx|tab\.?|tablet|cap\.?|capsule|inj\.?|injection|syp\.?|syrup|susp\.?|suspension|drop|drops|crm\.?|cream|oint\.?|ointment|gel|inh\.?|inhaler|cap|tab)\b[:.\-\s]*",
    re.IGNORECASE,
)

DOSAGE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu|%)\b",
    re.IGNORECASE,
)

SCHEDULE_PATTERN = re.compile(
    r"\b(?:\d+\s*\+\s*\d+\s*\+\s*\d+(?:\s*\+\s*\d+)?|\b(?:od|bd|tds|qid|hs|sos|stat|daily|weekly)\b)\b",
    re.IGNORECASE,
)

DURATION_PATTERN = re.compile(
    r"\b(?:for\s+)?\d+\s*(?:days?|weeks?|months?|wks?|mos?)\b",
    re.IGNORECASE,
)


def preprocess_image(image_path: str):
    """Preprocess prescription image for cleaner OCR if OpenCV is available."""
    if not HAS_OCR_LIBS:
        raise RuntimeError("OpenCV / pytesseract is not installed in this environment.")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image at: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return thresh


def extract_text_from_image(image_path: str, lang: str = "eng") -> str:
    """Extract raw text from a prescription image."""
    processed = preprocess_image(image_path)
    return pytesseract.image_to_string(processed, lang=lang)


def parse_prescription_lines(raw_text: str) -> List[Dict[str, Any]]:
    """Parse raw prescription text into structured candidate medicine items."""
    items: List[Dict[str, Any]] = []
    if not raw_text:
        return items

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 2:
            continue

        if re.match(r"^(?:patient|age|sex|date|dr\.?|doctor|diagnosis|c/c|o/e|advice)\b[:.\-\s]*", line, re.IGNORECASE):
            continue

        cleaned = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line)

        strength_match = DOSAGE_PATTERN.search(cleaned)
        strength = strength_match.group(0).strip() if strength_match else None

        schedule_match = SCHEDULE_PATTERN.search(cleaned)
        schedule = schedule_match.group(0).strip() if schedule_match else None

        duration_match = DURATION_PATTERN.search(cleaned)
        duration = duration_match.group(0).strip() if duration_match else None

        med_candidate = NOISE_PREFIXES.sub("", cleaned)
        med_candidate = DOSAGE_PATTERN.sub("", med_candidate)
        med_candidate = SCHEDULE_PATTERN.sub("", med_candidate)
        med_candidate = DURATION_PATTERN.sub("", med_candidate)
        med_candidate = re.sub(r"\s{2,}", " ", med_candidate).strip(" ,.-/\\")

        if med_candidate:
            items.append({
                "raw_line": line,
                "medicine_query": med_candidate,
                "strength": strength,
                "schedule": schedule,
                "duration": duration,
            })

    return items


def build_ddi_input_text(raw_text: str) -> str:
    """Convert extracted prescription lines into clean medicine lines for DDI checking."""
    parsed = parse_prescription_lines(raw_text)
    lines = []
    for item in parsed:
        part = item["medicine_query"]
        if item["strength"]:
            part = f"{part} {item['strength']}"
        lines.append(part)
    return "\n".join(lines)
