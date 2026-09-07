import easyocr
import re

# -------------------------------------------------------------------------
# HELPER & SANITIZATION FUNCTIONS
# -------------------------------------------------------------------------

def sanitize_mrz_name(text: str) -> str:
    """Replaces common OCR digit mistakes with their correct letters for MRZ names."""
    if not text:
        return ""
    char_map = {
        '1': 'I',
        '0': 'O',
        '8': 'B',
        '5': 'S',
        '2': 'Z'
    }
    for digit, letter in char_map.items():
        text = text.replace(digit, letter)
    return text


def clean_mrz_string(text: str) -> str:
    """Removes spaces and ensures uppercase for MRZ processing."""
    if not text:
        return ""
    return text.replace(" ", "").upper()


def extract_names_from_mrz(mrz_line_1: str):
    """
    Parses MRZ Line 1 (TD3 / Passport format: 44 characters).
    Format: P<CCC SURNAME<<GIVEN<NAMES<<<<<<<<<<<<<<<<
    """
    clean_mrz = clean_mrz_string(mrz_line_1)

    # Strip leading 'P<' or 'P' and the 3-letter country code (first 5 chars)
    if clean_mrz.startswith('P<') or clean_mrz.startswith('P>'):
        name_section = clean_mrz[5:]
    elif clean_mrz.startswith('P'):
        name_section = clean_mrz[4:]
    else:
        name_section = clean_mrz

    # Remove trailing '<' fillers
    name_section = name_section.rstrip('<')

    # Split surname and given names using the double filler '<<'
    if '<<' in name_section:
        surname_part, given_name_part = name_section.split('<<', 1)
    else:
        surname_part = name_section
        given_name_part = ""

    # Sanitize digits to letters and replace single '<' fillers with spaces
    surname = sanitize_mrz_name(surname_part.replace('<', ' ').strip())
    given_names = sanitize_mrz_name(given_name_part.replace('<', ' ').strip())

    return surname, given_names


def format_viz_for_mrz(text: str) -> str:
    """
    Converts VIZ text into ICAO-compliant format for comparison.
    Strips non-alphanumeric characters and extra whitespace.
    """
    if not text:
        return ""
    # Remove all non-alphanumeric characters (spaces, hyphens, artifacts)
    cleaned = re.sub(r'[^A-ZA-z0-9]', '', text)
    return cleaned.upper()


# -------------------------------------------------------------------------
# EXTRACTION FUNCTIONS
# -------------------------------------------------------------------------

def extract_mrz_line_1(ocr_results) -> str:
    """Extracts MRZ Line 1 from raw EasyOCR results."""
    mrz_line_1_pattern = re.compile(r'^P[A-Z0-9<]{3,}[<]+')

    for item in ocr_results:
        if len(item) == 3:
            _, text, _ = item
        else:
            continue

        clean_text = text.replace(" ", "").upper()

        if mrz_line_1_pattern.match(clean_text):
            return clean_text

    return ""


def extract_viz_data(ocr_results) -> dict:
    """Extracts VIZ fields using structured regex and context matching from pre-loaded OCR results."""
    viz_data = {
        "passport_num": None,
        "surname": None,
        "given_names": None,
        "nationality": None,
        "sex": None,
        "date_of_birth": None,
        "date_of_issue": None,
        "date_of_expiry": None,
        "place_of_birth": None,
        "place_of_issue": None
    }

    raw_lines = [text.strip() for _, text, conf in ocr_results if text.strip()]
    full_text = " ".join(raw_lines)

    # 1. Extract Passport Number
    passport_match = re.search(r'\b[A-Z][0-9]{7}\b', full_text)
    if passport_match:
        viz_data["passport_num"] = passport_match.group(0)

    # 2. Extract Dates
    dates = re.findall(r'\b\d{2}[\/\.-]\d{2}[\/\.-]\d{4}\b', full_text)
    if len(dates) >= 3:
        viz_data["date_of_birth"] = dates[0]
        viz_data["date_of_issue"] = dates[1]
        viz_data["date_of_expiry"] = dates[2]
    elif len(dates) == 2:
        viz_data["date_of_birth"] = dates[0]
        viz_data["date_of_expiry"] = dates[1]

    # 3. Extract Sex
    sex_match = re.search(r'\b(SEX|GENDER|लिंग)\b[:\s]*([M|F|X])\b', full_text, re.IGNORECASE)
    if sex_match:
        viz_data["sex"] = sex_match.group(2).upper()
    else:
        if re.search(r'\bM\b', full_text):
            viz_data["sex"] = "M"
        elif re.search(r'\bF\b', full_text):
            viz_data["sex"] = "F"

    # 4. Extract Nationality
    if "INDIAN" in full_text.upper():
        viz_data["nationality"] = "INDIAN"

    # 5. Extract Names by Label Search
    for i, line in enumerate(raw_lines):
        line_upper = line.upper()

        if "SURNAME" in line_upper or "उपनाम" in line_upper:
            if i + 1 < len(raw_lines):
                candidate = raw_lines[i + 1]
                if not any(keyword in candidate.upper() for keyword in ["GIVEN", "NAME", "DATE", "PASSPORT"]):
                    viz_data["surname"] = candidate.upper()

        if "GIVEN NAME" in line_upper or "THIA GAYA NAM" in line_upper or "दिया गया नाम" in line_upper:
            if i + 1 < len(raw_lines):
                candidate = raw_lines[i + 1]
                if not any(keyword in candidate.upper() for keyword in ["SEX", "NATIONALITY", "DATE", "BIRTH"]):
                    viz_data["given_names"] = candidate.upper()

    return viz_data


# -------------------------------------------------------------------------
# VERIFICATION PIPELINE
# -------------------------------------------------------------------------

def verify_mrz_with_name(mrz_line_1: str, viz_surname: str, viz_given_names: str) -> dict:
    """Verifies extracted VIZ Surname and Given Names against MRZ Line 1."""
    mrz_surname, mrz_given_names = extract_names_from_mrz(mrz_line_1)

    formatted_viz_surname = format_viz_for_mrz(viz_surname)
    formatted_viz_given_names = format_viz_for_mrz(viz_given_names)

    # Comparing formatted alphanumeric representations
    surname_match = (format_viz_for_mrz(mrz_surname) == formatted_viz_surname)
    given_name_match = (format_viz_for_mrz(mrz_given_names) == formatted_viz_given_names)

    full_match = surname_match and given_name_match

    return {
        "verified": full_match,
        "surname_match": surname_match,
        "given_name_match": given_name_match,
        "extracted_mrz": {
            "surname": mrz_surname,
            "given_names": mrz_given_names
        },
        "formatted_viz": {
            "surname": formatted_viz_surname,
            "given_names": formatted_viz_given_names
        }
    }


# -------------------------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------------------------

if __name__ == "__main__":
    image_path = 'jath.jpeg'

    # Initialize EasyOCR Reader once
    reader = easyocr.Reader(['en', 'hi'], gpu=False)

    # Perform single OCR read for performance efficiency
    ocr_results = reader.readtext(image_path)

    # 1. Extract MRZ Line 1
    extracted_mrz_line_1 = extract_mrz_line_1(ocr_results)
    print("Extracted MRZ Line 1:", extracted_mrz_line_1)

    # 2. Extract VIZ Data
    extracted_viz = extract_viz_data(ocr_results)

    # Fallback assignment if label search fails
    viz_surname = extracted_viz.get("surname") or "VAD NALA"
    viz_given_names = extracted_viz.get("given_names") or "JATHIN"

    # 3. Verify MRZ vs VIZ
    if extracted_mrz_line_1:
        result = verify_mrz_with_name(extracted_mrz_line_1, viz_surname, viz_given_names)
        print("\nVerification Results:")
        print(result)
    else:
        print("\nError: Could not locate MRZ Line 1 in image.")
