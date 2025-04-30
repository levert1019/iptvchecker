import re

def parse_groups(m3u_file: str):
    """
    Parse an M3U file into channel entries grouped by group-title.
    Each entry dict has:
      - 'uid': unique CUID or generated fallback
      - 'extinf': full EXTINF line
      - 'name': display name after the comma
      - 'url': the stream URL
    Returns (group_entries, categories).
    """
    group_entries = {}
    categories = {}

    with open(m3u_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for idx, line in enumerate(lines):
        if not line.strip().startswith('#EXTINF'):
            continue
        raw_extinf = line.strip()
        url = lines[idx+1].strip() if idx+1 < len(lines) else ''

        # Determine group-title
        m_grp = re.search(r'group-title="([^"]*)"', raw_extinf)
        grp = m_grp.group(1) if m_grp else ''

        # Extract name after comma
        parts = raw_extinf.split(',', 1)
        name = parts[1] if len(parts) > 1 else ''

        # Extract unique CUID if present
        m_uid = re.search(r'CUID="([^"]+)"', raw_extinf)
        uid = m_uid.group(1) if m_uid else f"{grp}:{name}:{idx}"

        entry = {
            'uid': uid,
            'extinf': raw_extinf,
            'name': name,
            'url': url
        }
        group_entries.setdefault(grp, []).append(entry)

    return group_entries, categories
