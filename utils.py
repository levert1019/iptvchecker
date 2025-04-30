import re

# Superscript quality labels
QUALITY_LABELS = {
    'sd': 'ˢᴰ',
    'hd': 'ᴴᴰ',
    'fhd': 'ᶠᴴᴰ',
    'uhd': 'ᵁᴴᴰ'
}

def sup_digits(text: str) -> str:
    """Convert digits to superscript."""
    tbl = str.maketrans({
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
    })
    return text.translate(tbl)

def format_fps(text: str) -> str:
    """ If it's purely numeric, convert to superscript; otherwise append ' FPS'."""
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if m:
        num = m.group(1)
        if num.endswith(".0"):
            num = num[:-2]
        return f"{sup_digits(num)}ᶠᵖˢ"
    # not numeric: keep the original text plus " FPS"
    return f"{text} FPS"


def resolution_to_label(res: str) -> str:
    """Map a resolution string 'WIDTH×HEIGHT' to a quality label."""
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
    """Remove existing quality/fps tokens from the channel name."""
    # Remove superscript fps
    name = re.sub(r"\d+ᶠᵖˢ", '', name)
    # Remove existing quality labels
    for v in QUALITY_LABELS.values():
        name = name.replace(v, '')
    # Remove text tokens
    name = re.sub(r"\b(sd|hd|fhd|uhd)\b", '', name, flags=re.IGNORECASE)
    name = re.sub(r"\b\d+(?:\.\d+)?fps\b", '', name, flags=re.IGNORECASE)
    return name.strip()
