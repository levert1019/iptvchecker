# parser.py
import re
from collections import OrderedDict

def parse_groups(path: str):
    """
    Returns:
      group_urls: OrderedDict[group_name, list of (channel_name, url)]
      categories: dict with keys 'Live','Movie','Series' → list of group_names
    """
    with open(path, encoding='utf-8', errors='ignore') as f:
        data = f.read()

    # preserve insertion order of groups
    group_urls = OrderedDict()
    # capture group-title, channel name, and next-line URL
    pattern = re.compile(
        r'#EXTINF:[^\n\r]*?group-title="([^"]+)"[^\n\r]*?,([^\n\r]+)\r?\n([^\n\r]+)',
        re.IGNORECASE
    )
    for m in pattern.finditer(data):
        grp = m.group(1).strip()
        name = m.group(2).strip()
        url  = m.group(3).strip()
        group_urls.setdefault(grp, []).append((name, url))

    # categorize groups by URL keywords, preserving first-seen order
    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp, entries in group_urls.items():
        # a group can exist in multiple categories
        seen = set()
        for _, url in entries:
            lower = url.lower()
            if 'movie' in lower and grp not in seen:
                categories['Movie'].append(grp); seen.add(grp)
            elif 'series' in lower and grp not in seen:
                categories['Series'].append(grp); seen.add(grp)
            elif grp not in seen:
                categories['Live'].append(grp); seen.add(grp)
    return group_urls, categories
