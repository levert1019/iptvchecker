# parser.py
import re
from collections import OrderedDict

def parse_groups(path: str):
    """
    Parses an M3U, returning:
      • group_entries: OrderedDict[
            group_name → list of dict{extinf: str, name: str, url: str}
        ]
      • categories:    dict of Live/Movie/Series → list of group_names
    """
    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.read().splitlines()

    group_entries = OrderedDict()
    # Pattern to capture full EXTINF line, channel name, and URL
    extinf_re = re.compile(
        r'(#EXTINF:[^,]*,(.*))$'
    )
    group_re  = re.compile(r'group-title="([^"]+)"', re.IGNORECASE)

    i = 0
    while i < len(lines):
        line = lines[i]
        m = extinf_re.match(line)
        if m and i+1 < len(lines):
            raw_extinf = m.group(1)
            name       = m.group(2).strip()
            url        = lines[i+1].strip()
            # extract group
            gm = group_re.search(line)
            grp = gm.group(1).strip() if gm else "Ungrouped"
            entry = {'extinf': raw_extinf, 'name': name, 'url': url}
            group_entries.setdefault(grp, []).append(entry)
            i += 2
        else:
            i += 1

    # Build categories
    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp, entries in group_entries.items():
        urls = [e['url'].lower() for e in entries]
        has_movie  = any('movie'  in u for u in urls)
        has_series = any('series' in u for u in urls)
        has_live   = any(not ('movie' in u or 'series' in u) for u in urls)

        if has_movie and has_series:
            entries.sort(key=lambda e: e['url'])

        if has_movie:  categories['Movie'].append(grp)
        if has_series: categories['Series'].append(grp)
        if has_live:   categories['Live'].append(grp)

    return group_entries, categories
