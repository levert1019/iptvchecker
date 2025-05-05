import os
import re
from utils import resolution_to_label, format_fps

# Constants
EXTINF_PREFIX = '#EXTINF:0 '
# Regex to capture attributes like key="value"
ATTR_RE = re.compile(r'(\S+?)="([^"]*)"')


def _parse_extinf(line: str):
    """
    Parse an #EXTINF line into (attrs_dict, display_name).
    """
    if not line.startswith(EXTINF_PREFIX):
        return {}, ''
    body = line[len(EXTINF_PREFIX):].rstrip('\n')
    # Split into attributes part and display name (after first comma)
    try:
        attr_part, disp = body.split(',', 1)
    except ValueError:
        return {}, ''
    attrs = {m.group(1): m.group(2) for m in ATTR_RE.finditer(attr_part)}
    return attrs, disp


def _build_extinf(attrs: dict, display: str) -> str:
    """
    Reconstruct an #EXTINF line from attrs dict and display name.
    """
    parts = [f'{k}="{v}"' for k, v in attrs.items()]
    return f"{EXTINF_PREFIX}{' '.join(parts)},{display}"


def write_output_files(
    original_lines,
    entry_map,
    status_map,
    base_name,
    output_dir,
    split=False,
    update_quality=False,
    update_fps=False,
    include_untested=False
) -> list:
    """
    Write M3U files based on statuses and user options.

    Returns a list of written file paths.
    """
    # 1) Early exit: no options
    if not any((split, update_quality, update_fps, include_untested)):
        return []

    # 2) Classify UIDs
    working_uids = [uid for uid, st in status_map.items() if st == 'UP']
    black_uids   = [uid for uid, st in status_map.items() if st == 'BLACK_SCREEN']
    non_uids     = [uid for uid, st in status_map.items() if st not in ('UP', 'BLACK_SCREEN')]

    # 3) Helper to collect entries by uid list
    def _collect(uids):
        collected = []
        for idx, line in enumerate(original_lines):
            if not line.startswith(EXTINF_PREFIX):
                continue
            attrs, disp = _parse_extinf(line)
            uid = attrs.get('CUID')
            if uid in uids:
                # apply labels
                name = disp
                entry = entry_map.get(uid, {})
                if update_quality:
                    lbl = resolution_to_label(entry.get('resolution', ''))
                    if lbl:
                        name += f' {lbl}'
                if update_fps:
                    fl = format_fps(entry.get('fps', 0))
                    if fl:
                        name += f' {fl}'
                # update tvg-name attr
                attrs['tvg-name'] = name
                # rebuild extinf line
                ext = _build_extinf(attrs, name)
                # next line is URL
                url = original_lines[idx+1].strip() if idx+1 < len(original_lines) else ''
                collected.append((ext, url))
        return collected

    # 4) Write a single M3U
    def _write(entries, filename):
        if not entries:
            return None
        path = os.path.join(output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for ext, url in entries:
                f.write(ext + '\n')
                f.write(url + '\n')
        return path

    files = []
    # Split into separate files
    if split:
        # Working channels
        e_work = _collect(working_uids)
        p = _write(e_work, f"{base_name}_working.m3u")
        if p: files.append(p)
        # Black screen channels
        e_black = _collect(black_uids)
        p = _write(e_black, f"{base_name}_black_screen.m3u")
        if p: files.append(p)
        # Non-working channels (only those tested and failed)
        e_non = _collect(non_uids)
        p = _write(e_non, f"{base_name}_non_working.m3u")
        if p: files.append(p)
        # Optional: include untested in an 'all' file
        if include_untested:
            all_uids = list(entry_map.keys())
            e_all = _collect(all_uids)
            p = _write(e_all, f"{base_name}_all.m3u")
            if p: files.append(p)
    else:
        # Single file: either only tested or include all
        if include_untested:
            uids = list(entry_map.keys())
        else:
            uids = working_uids + black_uids + non_uids
        entries = _collect(uids)
        p = _write(entries, f"{base_name}_all.m3u")
        if p: files.append(p)

    return files
