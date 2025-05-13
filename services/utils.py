import re

# Superscript quality labels
QUALITY_LABELS = {
    'sd': 'ˢᴰ',
    'hd': 'ᴴᴰ',
    'fhd': 'ᶠᴴᴰ',
    'uhd': 'ᵁᴴᴰ'
}

# Table for superscript digits
_SUP_DIGITS = str.maketrans({
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
})

# Characters used in superscript annotations
_SUP_CHARS = set(''.join(QUALITY_LABELS.values()) + 'ᶠᵖˢ' + ''.join('⁰¹²³⁴⁵⁶⁷⁸⁹×'))
_SUP_PATTERN = re.compile(f"[{''.join(_SUP_CHARS)}]")


def sup_digits(text: str) -> str:
    """Convert ASCII digits in text to their superscript equivalents."""
    return text.translate(_SUP_DIGITS)


def format_fps(text: str) -> str:
    """
    Round any numeric fps string to the nearest integer and superscript it.
    E.g. "25.0" → ²⁵ᶠᵖˢ, "59.94" → ⁶⁰ᶠᵖˢ. Non-numeric text yields an empty string.
    """
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not m:
        return ''
    num_str = m.group(1)
    try:
        num = round(float(num_str))
    except ValueError:
        return ''
    return sup_digits(str(num)) + 'ᶠᵖˢ'


def resolution_to_label(res: str) -> str:
    """Map a resolution string 'WIDTH×HEIGHT' to a quality superscript label."""
    parts = res.split('×')
    if len(parts) != 2:
        return ''
    try:
        w, h = map(int, parts)
    except ValueError:
        return ''
    if w >= 3840 or h >= 2160:
        key = 'uhd'
    elif w >= 1920 or h >= 1080:
        key = 'fhd'
    elif w >= 1280 or h >= 720:
        key = 'hd'
    else:
        key = 'sd'
    return QUALITY_LABELS[key]


def clean_name(name: str) -> str:
    """Strip all superscript quality/fps/resolution characters and collapse whitespace."""
    for label in QUALITY_LABELS.values():
        name = name.replace(label, '')
    name = _SUP_PATTERN.sub('', name)
    return re.sub(r'\s+', ' ', name).strip()


class RegexRules:
    """Central regex patterns for parsing M3U entries."""
    GROUP_RE   = re.compile(r'group-title="([^"]+)"')
    PREFIX_RE  = re.compile(r'^[A-Z0-9]{2,4}\s*')
    YEAR_RE    = re.compile(r'\b(19|20)\d{2}\b')
    MULTI_RE   = re.compile(r'\(MULTI\)', re.IGNORECASE)
    EPISODE_RE = re.compile(r'\bS\d{2}E\d{2}\b')
