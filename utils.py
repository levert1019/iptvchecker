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
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if not m:
        return ''
    num = m.group(1)
    if num.endswith(".0"):
        num = num[:-2]
    return f"{sup_digits(num)}ᶠᵖˢ"

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

_SUP_CHARS = set(''.join(QUALITY_LABELS.values()) + 'ᶠᵖˢ' + ''.join('⁰¹²³⁴⁵⁶⁷⁸⁹×'))
_SUP_PATTERN = re.compile(f"[{''.join(_SUP_CHARS)}]")

def clean_name(name: str) -> str:
    """Strip all superscript quality/fps/resolution characters and collapse whitespace."""
    # 1) remove entire multi-char quality labels (just in case)
    for label in QUALITY_LABELS.values():
        name = name.replace(label, '')
    # 2) strip any remaining superscript chars (digits, x, letters, fps marker)
    name = _SUP_PATTERN.sub('', name)
    # 3) collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)
    return name.strip()
