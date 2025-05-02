import re

def parse_groups(m3u_file: str):
    """
    Parse an M3U file into channel entries grouped by group-title,
    and classify group titles into Live, Movie, and Series categories
    based on the stream URLs:
      - Series: any URL contains "series"
      - Movie: any URL contains "movie" or "movies"
      - Live: all others

    Returns:
      - group_entries: dict mapping group_title -> list of entry dicts
      - categories: dict with keys 'Live', 'Movie', 'Series'
    """
    group_entries = {}

    # Read all lines from the M3U file
    with open(m3u_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Build entries keyed by their group-title, preserving order encountered
    for idx, line in enumerate(lines):
        if not line.strip().startswith('#EXTINF'):
            continue
        raw_extinf = line.strip()
        url = lines[idx+1].strip() if idx+1 < len(lines) else ''

        # Extract group-title attribute
        m_grp = re.search(r'group-title="([^"]*)"', raw_extinf)
        grp = m_grp.group(1) if m_grp else 'Unknown'

        # Extract channel name
        name = raw_extinf.split(',', 1)[1] if ',' in raw_extinf else ''

        # Extract or generate UID
        m_uid = re.search(r'CUID="([^\"]+)"', raw_extinf)
        uid = m_uid.group(1) if m_uid else f"{grp}:{name}:{idx}"

        entry = {
            'uid': uid,
            'extinf': raw_extinf,
            'name': name,
            'url': url,
        }
        # Preserve first-seen order of group_titles
        if grp not in group_entries:
            group_entries[grp] = []
        group_entries[grp].append(entry)

    # Classify group titles into categories, preserving original order
    categories = {'Live': [], 'Movie': [], 'Series': []}
    for grp_title, entries in group_entries.items():
        urls = [e['url'].lower() for e in entries]
        if any('series' in u for u in urls):
            categories['Series'].append(grp_title)
        elif any('movie' in u for u in urls):
            categories['Movie'].append(grp_title)
        else:
            categories['Live'].append(grp_title)

    return group_entries, categories