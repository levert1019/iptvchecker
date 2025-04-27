import re

def parse_groups(path: str) -> tuple[dict, dict]:
    """
    Read a local M3U file and return:
      - group_urls: { group_name: [url, ...], ... }
      - categories: { 'Live': [...], 'Movie': [...], 'Series': [...] }

    A group belongs to:
      * Movie if any URL contains 'movie' or 'movies'
      * Series if any URL contains 'series'
      * Live if neither 'movie' nor 'movies' nor 'series' in URLs

    Original group order preserved.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = f.read()

    pattern = re.compile(
        r'#EXTINF:.*?group-title="([^\"]+)".*?\r?\n([^\r\n]+)',
        re.IGNORECASE
    )
    group_urls: dict[str, list[str]] = {}
    for match in pattern.finditer(data):
        grp = match.group(1)
        url = match.group(2).strip()
        group_urls.setdefault(grp, []).append(url)

    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp, urls in group_urls.items():
        ul = [u.lower() for u in urls]
        if any('movie' in u or 'movies' in u for u in ul):
            categories['Movie'].append(grp)
        if any('series' in u for u in ul):
            categories['Series'].append(grp)
        if all('movie' not in u and 'movies' not in u and 'series' not in u for u in ul):
            categories['Live'].append(grp)

    return group_urls, categories
