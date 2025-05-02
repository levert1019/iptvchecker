# output_writer.py

import os
import re
from utils import clean_name, resolution_to_label, format_fps

# Regex to extract CUID from an EXTINF line
CUID_RE = re.compile(r'CUID=\"([^\\\"]+)\"')

# Build EXTINF line with optional quality/fps updates,
# and ensure tvg-name matches the updated display.
def build_extinf(entry, update_quality=False, update_fps=False):
    # Base channel name
    base_name = clean_name(entry['name'])

    # Apply quality/fps updates
    display = base_name
    if update_quality and entry.get('res'):
        display += ' ' + resolution_to_label(entry['res'])
    if update_fps and entry.get('fps'):
        display += ' ' + format_fps(entry['fps'])

    # Always include CUID and tvg-name
    attrs = [f'CUID="{entry["uid"]}"',
             f'tvg-name="{display}"']

    # Preserve all other tvg-*/group/catchup attributes
    for k, v in entry.items():
        if k.startswith('tvg-') or k in ('group-title','catchup-type','catchup-days'):
            attrs.append(f'{k}="{v}"')

    return f"#EXTINF:0 {' '.join(attrs)},{display}\n"


# Write M3U outputs in the original order.
# Returns list of the file paths that were written.
def write_output_files(original_lines, entry_map, statuses,
                       base_name, output_dir,
                       split=False, update_quality=False,
                       update_fps=False, include_untested=False):
    header = "#EXTM3U\n"

    # 1) Extract UIDs in the order they appear in the source
    ordered_uids = []
    for ln in original_lines:
        if ln.startswith('#EXTINF') and (m := CUID_RE.search(ln)):
            uid = m.group(1)
            if uid not in ordered_uids:
                ordered_uids.append(uid)

    written = []

    def _write_by_status(suffix, target_status):
        fn = os.path.join(output_dir, f"{base_name}_{suffix}.m3u")
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(header)
            for uid in ordered_uids:
                if statuses.get(uid) == target_status:
                    e = entry_map.get(uid)
                    if e:
                        f.write(build_extinf(e, update_quality, update_fps))
                        f.write(e['url'] + '\n')
        written.append(fn)

    if split:
        _write_by_status('working',    'UP')
        _write_by_status('blackscreen','BLACK_SCREEN')
        _write_by_status('notworking','NON_WORKING')

        if include_untested:
            fn = os.path.join(output_dir, f"{base_name}_all.m3u")
            with open(fn, 'w', encoding='utf-8') as f:
                f.write(header)
                for uid in ordered_uids:
                    if statuses.get(uid) in ('UP','BLACK_SCREEN','NON_WORKING'):
                        e = entry_map.get(uid)
                        if e:
                            f.write(build_extinf(e, update_quality, update_fps))
                            f.write(e['url'] + '\n')
            written.append(fn)
    else:
        fn = os.path.join(output_dir, f"{base_name}_all.m3u")
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(header)
            for uid in ordered_uids:
                e = entry_map.get(uid)
                if e:
                    f.write(build_extinf(e, update_quality, update_fps))
                    f.write(e['url'] + '\n')
        written.append(fn)

    return written
