"""
classify_names.py
-----------------
Classifies entries in the YAGP winners Name column as:
  person       – individual dancer or award recipient
  multi_person – two dancers listed together (PDD, duet)
  dance        – a dance/piece title
  school       – a school or company name
  unknown      – NaN or unclassifiable

Strategy:
  Tier 1 – structural column signals (very high confidence)
  Tier 2 – content-based regex (for rows with no clear structural signal)
"""

import regex as re

# ── Constants ────────────────────────────────────────────────────────────────

SOLO_DIVS = {
    "JUNIOR AGE DIVISION",
    "SENIOR AGE DIVISION",
    "PRE-COMPETITIVE AGE DIVISION",
}

ENSEMBLE_CATS = {
    "ENSEMBLES", "LARGE ENSEMBLES", "SMALL ENSEMBLES",
    "DUETS & TRIOS", "DUET/TRIO", "DUET", "TRIO",
}

# Division / Position values that indicate group pieces (not solo persons)
ENSEMBLE_DIV_POS = {"LARGE ENSEMBLES", "SMALL ENSEMBLES", "ENSEMBLES", "DUET/TRIO"}

SOLO_DANCE_CATS = {
    "CLASSICAL DANCE CATEGORY",
    "CONTEMPORARY DANCE CATEGORY",
    "CLASSICAL & CONTEMPORARY DANCE CATEGORY",
    "CONTEMPORARY/OPEN DANCE CATEGORY",
    "TRADITIONAL DANCE CATEGORY",
}

# ── Compiled regex ────────────────────────────────────────────────────────────

# School / company indicators
SCHOOL_RE = re.compile(
    r"\b(ACADEMY|BALLET SCHOOL|CONSERVATORY|PERFORMING ARTS|DANCE CENTER|"
    r"DANCE THEATRE|DANCE COMPANY|DANCE STUDIO|SCHOOL OF|SCHOOL FOR|"
    r"INSTITUTE|CORPS DE BALLET)\b",
    re.IGNORECASE,
)

# Dance-specific musical / choreographic keywords
DANCE_KEYWORD_RE = re.compile(
    r"\b(PAS DE|WALTZ|SUITE|CONCERTO|VARIATION|POLKA|TARANTELL|NOCTURNE|SONATA|"
    r"PRELUDE|ADAGIO|SYMPHONY|BOLERO|OVERTURE|MAZURKA|DIVERTISS|"
    r"HOPAK|GOPAK|JOTA|CZARDAS|SCHERZO|REQUIEM|FUGUE|GALOP|SERENADE|"
    r"INTERMEZZO|PIZZICATO|MINUET|RONDO|BERCEUSE|FINALE|EXCERPT|"
    r"FANTASIA|LEZGINKA|TARANTELLA|PAVANE|SICILIAN|SEGUIDILLA|HABANERA)\b",
    re.IGNORECASE,
)

# Title openings that are almost never personal names
TITLE_START_RE = re.compile(
    r"^(A |AN |THE |FOR |ALL |FROM |INTO |UPON |IN THE |AT THE |"
    r"ON THE |TO THE |OF THE |UNDER THE |OVER THE |BEYOND |BETWEEN |"
    r"DANCE OF|DANCE FOR|WALTZ OF|SUITE OF|SONG OF|DREAM OF|SPIRIT OF|"
    r"VOICES |ECHOES |SHADOWS |WAVES |FRAGMENTS |MOMENTS |MEMORIES |COLORS |"
    r"COLOURS |SPARKS |ROOTS |WINGS |THREADS |BORDERS |HORIZONS |"
    r"SOMETHING |NOTHING |EVERYTHING |SOMEWHERE )",
    re.IGNORECASE,
)

# Age digits (e.g., "(12)" or ", 16,") – indicates annotated multi-person entries
HAS_AGE_DIGITS = re.compile(r"\b\d{1,2}\b")

# Personal name pattern: 2–5 capitalized tokens, optional state suffix
# Allows apostrophes (O'Brien), hyphens (Mei-Lin), accented chars, dots (St. John)
PERSON_NAME_RE = re.compile(
    r"^[A-ZÀ-Öa-zà-ö'][A-ZÀ-Öa-zà-ö'\-\.]*"
    r"(?:\s+[A-ZÀ-Öa-zà-ö'][A-ZÀ-Öa-zà-ö'\-\.]*){1,4}"
    r"(?:,\s*[A-Z]{2})?$"
)

# Words that strongly indicate a non-person (title / lyric words)
NON_NAME_WORDS = {
    "THE", "FOR", "FROM", "WITH", "INTO", "OVER", "UNDER", "AND", "BUT",
    "OR", "OF", "IN", "ON", "AT", "TO", "BY", "AS", "AN", "IS", "IT",
    "MY", "YOUR", "HER", "HIS", "OUR", "THEIR", "THIS", "THAT", "WHICH",
    "STILL", "JUST", "ONLY", "NEVER", "ALWAYS", "EVER", "ONCE", "MORE",
    "NOW", "HERE", "THERE", "WHERE", "WHEN", "HOW", "WHY", "WHAT",
    "LOST", "FOUND", "RISE", "FALL", "FLOW", "GROW", "GONE", "LEFT",
    "BROKEN", "SHATTERED", "FALLEN", "RISING", "FALLING", "MOVING",
    "RUNNING", "DANCING", "FLYING", "HOLDING", "LEAVING", "REACHING",
    "ABOVE", "BELOW", "WITHIN", "WITHOUT", "BEYOND", "BETWEEN",
}

# Single-word entries that are clearly not personal names
SINGLE_WORD_NON_NAMES = {
    "ALL", "FOR", "TOP", "NONE", "YES", "NO", "OK", "OKAY",
    "DANCE", "BALLET", "MUSIC", "ART", "SHOW", "WORK", "PIECES", "NUMBERS",
}

# ── Classifier ────────────────────────────────────────────────────────────────

def classify_name(row) -> str:
    """
    Given a row from the winners DataFrame, return a classification label.

    Expected columns (may be NaN): Name, Division, Division / Position,
    Category, Dance Category.
    """
    raw_name = str(row.get("Name", "") or "").strip()
    if not raw_name or raw_name.upper() == "NAN":
        return "unknown"

    name = raw_name.upper()

    div     = str(row.get("Division", "")            or "").strip().upper()
    div_pos = str(row.get("Division / Position", "") or "").strip().upper()
    cat     = str(row.get("Category", "")            or "").strip().upper()
    dc      = str(row.get("Dance Category", "")      or "").strip().upper()

    # Use whichever column is populated
    eff_div = div if div and div != "NAN" else div_pos
    eff_cat = cat if cat and cat != "NAN" else dc

    # ── TIER 1: structural column signals ────────────────────────────────────

    # Solo age division → person
    if eff_div in SOLO_DIVS:
        return "person"

    # Ensemble division/position → dance title (even if Name looks like a person)
    if eff_div in ENSEMBLE_DIV_POS:
        return "dance"

    # Ensemble category → dance title
    if eff_cat in ENSEMBLE_CATS:
        return "dance"

    # Solo dance categories → individual performer
    if eff_cat in SOLO_DANCE_CATS:
        return "person"

    # Special awards → person (or school, checked below)
    if eff_cat == "SPECIAL AWARDS":
        if SCHOOL_RE.search(name):
            return "school"
        return "person"

    # Pas De Deux division – Name may be a person OR a dance title
    if "PAS DE" in eff_div:
        if DANCE_KEYWORD_RE.search(name) or TITLE_START_RE.match(name):
            return "dance"
        if HAS_AGE_DIGITS.search(name):
            return "multi_person"   # e.g. "NAME (12), NAME (14)"
        if " & " in name:
            # "&" + dance keyword → dance title; otherwise multi-person
            return "dance" if DANCE_KEYWORD_RE.search(name) else "multi_person"
        return "person"

    # Pas De Deux dance category (rows where Division / Position is empty)
    if "PAS DE DEUX" in eff_cat or "DUETS & PAS DE DEUX" in eff_cat:
        if DANCE_KEYWORD_RE.search(name) or TITLE_START_RE.match(name):
            return "dance"
        if HAS_AGE_DIGITS.search(name):
            return "multi_person"
        if " & " in name:
            return "dance" if DANCE_KEYWORD_RE.search(name) else "multi_person"
        return "person"

    # ── TIER 2: content-based signals ────────────────────────────────────────

    # Multiple people joined by &
    if " & " in name:
        return "dance" if DANCE_KEYWORD_RE.search(name) else "multi_person"

    # Contains age-like digits → likely annotated multi-person PDD entry
    if HAS_AGE_DIGITS.search(name):
        return "multi_person" if "," in name else "dance"

    # School / company name
    if SCHOOL_RE.search(name):
        return "school"

    # Starts with a title-like word
    if TITLE_START_RE.match(name):
        return "dance"

    # Contains dance-specific keywords
    if DANCE_KEYWORD_RE.search(name):
        return "dance"

    # Single-word entries
    words = name.split()
    if len(words) == 1:
        if name in SINGLE_WORD_NON_NAMES:
            return "dance"
        if len(name) <= 8:          # Short single words are almost always dance titles
            return "dance"

    # Count non-name filler words
    non_name_count = sum(1 for w in words if w in NON_NAME_WORDS)
    if non_name_count >= 2:
        return "dance"

    # Check personal-name regex
    if PERSON_NAME_RE.match(raw_name):
        if len(words) == 2 and non_name_count >= 1:
            return "dance"          # e.g. "My Heart", "Lost Soul"
        return "person"

    # Default: treat as dance
    return "dance"