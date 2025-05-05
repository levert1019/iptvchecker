import os
import re
from services.utils import resolution_to_label, format_fps

# Constants & regexes
EXTINF_PREFIX = '#EXTINF'
CUID_RE       = re.compile(r'CUID="([^"]+)"')
ATTR_RE       = re.compile(r'(\w+)="([^"]*)"')
# Map internal statuses to filename suffixes
WRITE_MAP     = {
    'UP':            'working',
    'BLACK_SCREEN':  'black_screen',
    'DOWN':          'non_working'
}

def _build_extinf(orig_extinf: str,
                  entry: dict,
                  update_quality: bool,
                  update_fps: bool) -> str:
    """
    Rebuilds an EXTINF line, preserving all attributes except
    tvg-name, which is overridden (and has quality/FPS appended).
    """
    # Split off the "display name" part
    prefix, orig_name = orig_extinf.split(',', 1)

    # Parse all key="value" attributes into a dict
    attrs = dict(ATTR_RE.findall(prefix))

    # Construct new display name
    new_name = orig_name
    if update_quality:
        q = resolution_to_label(entry.get('resolution', ''))
        if q:
            new_name += f" {q}"
    if update_fps:
        f = format_fps(entry.get('fps', ''))
        if f:
            new_name += f" {f}"

    # Override the tvg-name attribute
    attrs['tvg-name'] = new_name

    # Re-serialize all attributes in a single string
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f'{EXTINF_PREFIX}:0 {attr_str},{new_name}'


def write_output_files(original_lines: list[str],
                       entry_map: dict[str, dict],
                       status_map: dict[str, str],
                       base_name: str,
                       output_dir: str,
                       split: bool,
                       update_quality: bool,
                       update_fps: bool,
                       include_untested: bool) -> list[str]:
    """
    Writes out one or more M3U files according to the user's settings.

    Returns the list of full file paths written.
    """
    # If no options selected, don't write anything
    if not any([split, update_quality, update_fps, include_untested]):
        return []

    # Collect tested vs. untested entries
    tested = []   # tuples of (uid, extinf_line, url, status)
    untested = [] # tuples of (uid, extinf_line, url)
    for idx, raw in enumerate(original_lines):
        line = raw.rstrip('\n')
        if not line.startswith(EXTINF_PREFIX):
            continue
        extinf = line
        url    = original_lines[idx+1].rstrip('\n') if idx+1 < len(original_lines) else ''
        m = CUID_RE.search(extinf)
        if not m:
            continue
        uid    = m.group(1)
        status = status_map.get(uid)
        if status:
            tested.append((uid, extinf, url, status))
        else:
            untested.append((uid, extinf, url))

    # Bucket tested entries by status
    buckets: dict[str, list[tuple[str,str,str]]] = {
        'UP': [], 'BLACK_SCREEN': [], 'DOWN': []
    }
    for uid, extinf, url, status in tested:
        key = status if status in buckets else 'DOWN'
        buckets[key].append((uid, extinf, url))

    written_files: list[str] = []

    def _write_file(suffix: str, items: list[tuple[str,str,str]]):
        """Helper to write one M3U file for the given items."""
        path = os.path.join(output_dir, f"{base_name}_{suffix}.m3u")
        with open(path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for uid, extinf, url in items:
                entry    = entry_map.get(uid, {})
                new_ext  = _build_extinf(extinf, entry, update_quality, update_fps)
                f.write(new_ext + "\n")
                f.write(url + "\n")
        written_files.append(path)

    if split:
        # Write one for each non-empty bucket
        for status, items in buckets.items():
            if items:
                _write_file(WRITE_MAP[status], items)
        # Optionally write a fourth "all" file including untested
        if include_untested:
            all_items = [(uid, ext, url) for uid, ext, url, _ in tested] \
                      + [(uid, ext, url)       for uid, ext, url   in untested]
            _write_file('all', all_items)
    else:
        # Single combined file
        items = [(uid, ext, url) for uid, ext, url, _ in tested]
        if include_untested:
            items += [(uid, ext, url) for uid, ext, url in untested]
        _write_file('all', items)

    return written_files
