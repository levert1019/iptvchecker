# parser.py

import re
from typing import Dict, List, Tuple

# Match attributes like key="value", allowing hyphens in keys
ATTR_RE  = re.compile(r'([\w-]+)="([^"]*)"')
CUID_RE  = re.compile(r'CUID="([^"]*)"')
GROUP_RE = re.compile(r'group-title="([^"]*)"', re.IGNORECASE)

def parse_groups(m3u_path: str) -> Tuple[Dict[str, List[dict]], Dict[str, List[str]]]:
    """
    Parse an M3U file into:
      - group_entries: { group_title: [entry_dict, ...], ... }
      - categories:    { category_name: [group_title, ...], ... }

    Each entry_dict has:
      {
        "uid":        str,    # from CUID=""
        "raw_extinf": str,    # the full #EXTINF line
        "url":        str     # the following URL line
      }

    Groups are taken from the 'group-title' attribute; categories are
    derived by splitting the group-title at the first dash (if present),
    otherwise the entire group-title is its own category.
    """
    group_entries: Dict[str, List[dict]] = {}
    categories:    Dict[str, List[str]] = {}

    # Read all lines once
    with open(m3u_path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f]

    for idx, line in enumerate(lines):
        if not line.startswith('#EXTINF'):
            continue

        extinf = line
        url    = lines[idx + 1] if idx + 1 < len(lines) else ''

        # Extract all key="value" pairs
        attrs = dict(ATTR_RE.findall(extinf))

        # UID
        uid = attrs.get('CUID')

        # Group title
        m = GROUP_RE.search(extinf)
        group = m.group(1) if m else 'Ungrouped'

        # Build the entry dict
        entry = {
            "uid":        uid,
            "raw_extinf": extinf,
            "url":        url
        }

        # Append to group_entries
        group_entries.setdefault(group, []).append(entry)

        # Derive category: text before first "-" (dash), or the group itself
        if '-' in group:
            cat = group.split('-', 1)[0].strip()
        else:
            cat = group
        categories.setdefault(cat, []).append(group)

    return group_entries, categories
