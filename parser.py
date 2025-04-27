# parser.py

import re
from collections import OrderedDict

def parse_groups(path: str):
    """
    Returns:
      • group_urls: OrderedDict[group_name → list of (channel_name, url)]
      • categories: dict with keys 'Live','Movie','Series' → list of group_names
    """
    with open(path, encoding='utf-8', errors='ignore') as f:
        data = f.read()

    # 1) Build the full mapping, preserving file order:
    group_urls = OrderedDict()
    pattern = re.compile(
        r'#EXTINF:[^\n\r]*?group-title="([^"]+)"[^\n\r]*?,([^\n\r]+)\r?\n([^\n\r]+)',
        re.IGNORECASE
    )
    for m in pattern.finditer(data):
        grp, name, url = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        group_urls.setdefault(grp, []).append((name, url))

    # 2) Classify each group *into all bins it belongs to*:
    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp, entries in group_urls.items():
        lowers = [u.lower() for _, u in entries]
        has_movie  = any('movie'  in u for u in lowers)
        has_series = any('series' in u for u in lowers)
        has_live   = any('movie' not in u and 'series' not in u for u in lowers)

        # If a group has *both* movie & series URLs → sort its entries by URL now
        if has_movie and has_series:
            group_urls[grp] = sorted(entries, key=lambda x: x[1])

        # Allow multi‐bin membership:
        if has_movie:  categories['Movie'].append(grp)
        if has_series: categories['Series'].append(grp)
        if has_live:   categories['Live'].append(grp)

    return group_urls, categories
