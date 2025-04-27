import re

def parse_groups(path: str) -> dict:
    """
    Read a local M3U file and return:
      - group_urls: { group_name: [url, ...], ... }
      - categories: { 'Live': [...], 'Movie': [...], 'Series': [...] }
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = f.read()

    # Capture group-title and the URL on the next line
    pattern = re.compile(
        r'#EXTINF:.*?group-title="([^\\"]+)".*?\\r?\\n([^\\r\\n]+)',
        re.IGNORECASE
    )
    group_urls = {}
    for match in pattern.finditer(data):
        grp = match.group(1)
        url = match.group(2).strip()
        group_urls.setdefault(grp, []).append(url)

    # Categorize groups based on URL keywords
    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp, urls in group_urls.items():
        for u in urls:
            lower = u.lower()
            if 'movie' in lower:
                categories['Movie'].append(grp)
            elif 'series' in lower:
                categories['Series'].append(grp)
            else:
                categories['Live'].append(grp)

    return group_urls, categories
