# parser.py

import re
from typing import Dict, List, Tuple

# Regexes for extracting attributes
ATTR_RE   = re.compile(r'(\w+)="([^"]*)"')
CUID_RE   = re.compile(r'CUID="([^"]*)"')
GROUP_RE  = re.compile(r'group-title="([^"]*)"')

def parse_groups(m3u_path: str) -> Tuple[Dict[str, List[dict]], Dict[str, List[str]]]:
    """
    Parse an M3U file into:
      - group_entries: { group_title: [entry, ...], … }
      - categories:    { category: [group_title, …], … }

    Each entry is a dict:
      {
        "uid": str,           # the CUID attribute
        "raw_extinf": str,    # full EXTINF line
        "url": str            # the URL on the next line
      }

    Category is taken as the text before " - " in the group-title, or "Other".
    """
    group_entries: Dict[str, List[dict]]   = {}
    categories:    Dict[str, List[str]]    = {}

    # Read the file
    with open(m3u_path, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]

    # Walk through lines looking for EXTINF
    for idx, line in enumerate(lines):
        if not line.startswith('#EXTINF'):
            continue

        extinf = line
        url    = lines[idx + 1] if idx + 1 < len(lines) else ''

        # Extract attributes
        attrs = dict(ATTR_RE.findall(extinf))
        uid   = attrs.get('CUID')
        group = attrs.get('group-title', 'Ungrouped')

        # Build entry object
        entry = {
            "uid":        uid,
            "raw_extinf": extinf,
            "url":        url
        }

        # Append to group_entries
        group_entries.setdefault(group, []).append(entry)

        # Determine category (prefix before " - ")
        if ' - ' in group:
            cat = group.split(' - ', 1)[0]
        else:
            cat = 'Other'
        categories.setdefault(cat, []).append(group)

    return group_entries, categories
