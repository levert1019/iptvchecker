# services/parser.py

import re
from typing import Dict, List, Tuple

# Match key="value" pairs, including hyphens in the key
ATTR_RE   = re.compile(r'([\w-]+)="([^"]*)"')
GROUP_RE  = re.compile(r'group-title="([^"]*)"', re.IGNORECASE)

def parse_groups(m3u_path: str) -> Tuple[Dict[str, List[dict]], Dict[str, List[str]]]:
    """
    Parse an M3U file into:
      - group_entries: { group_title: [entry_dict, ...], ... }
      - categories:    { category_name: [group_title, ...], ... }

    Each entry_dict has:
      {
        "uid":        str,  # from CUID=""
        "name":       str,  # the display name after the comma
        "raw_extinf": str,  # full #EXTINF line
        "url":        str   # the following URL
      }
    """
    group_entries: Dict[str, List[dict]] = {}
    categories:    Dict[str, List[str]] = {}

    # Read all lines
    with open(m3u_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    for idx, line in enumerate(lines):
        if not line.startswith("#EXTINF"):
            continue

        extinf = line
        url    = lines[idx + 1] if idx + 1 < len(lines) else ""

        # Extract attributes
        attrs = dict(ATTR_RE.findall(extinf))
        uid   = attrs.get("CUID")

        # Extract the display name (text after the first comma)
        if "," in extinf:
            name = extinf.split(",", 1)[1]
        else:
            name = ""

        # Extract group-title
        m = GROUP_RE.search(extinf)
        group = m.group(1) if m else "Ungrouped"

        entry = {
            "uid":        uid,
            "name":       name,
            "raw_extinf": extinf,
            "url":        url
        }

        # Append to group_entries
        group_entries.setdefault(group, []).append(entry)

        # Derive category (prefix before " - ")
        if " - " in group:
            cat = group.split(" - ", 1)[0].strip()
        else:
            cat = group
        categories.setdefault(cat, []).append(group)

    return group_entries, categories
