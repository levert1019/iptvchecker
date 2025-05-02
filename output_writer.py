import os
import re
from utils import clean_name, resolution_to_label, format_fps

# Regex to extract CUID from an EXTINF line
CUID_RE = re.compile(r'CUID="([^\"]+)"')

# Build EXTINF line with optional quality/fps updates
# Ensures tvg-name matches the display (including any updates)
def build_extinf(entry, update_quality=False, update_fps=False):
    # Base channel name
    base_name = clean_name(entry['name'])
    # Apply quality and fps updates to display name
    display = base_name
    if update_quality and entry.get('res'):
        display += ' ' + resolution_to_label(entry['res'])
    if update_fps and entry.get('fps'):
        display += ' ' + format_fps(entry['fps'])

    # Build attribute list, with tvg-name set to the updated display
    attrs = []
    attrs.append(f'CUID="{entry.get("uid","")}"')
    attrs.append(f'tvg-name="{display}"')
    if 'tvg-id' in entry:
        attrs.append(f'tvg-id="{entry["tvg-id"]}"')
    if 'tvg-logo' in entry:
        attrs.append(f'tvg-logo="{entry["tvg-logo"]}"')
    if 'group-title' in entry:
        attrs.append(f'group-title="{entry["group-title"]}"')
    if 'catchup-type' in entry:
        attrs.append(f'catchup-type="{entry["catchup-type"]}"')
    if 'catchup-days' in entry:
        attrs.append(f'catchup-days="{entry["catchup-days"]}"')

    # Return the EXTINF line
    return f"#EXTINF:0 {' '.join(attrs)},{display}\n"

# Write M3U outputs, preserving original order and applying split/merged logic
# Returns list of written file paths
def write_output_files(original_lines, entry_map, statuses,
                       base_name, output_dir,
                       split=False, update_quality=False,
                       update_fps=False, include_untested=False):
    header = "#EXTM3U\n"

    # Determine original order of UIDs from the main M3U
    ordered_uids = []
    for ln in original_lines:
        if ln.startswith('#EXTINF') and (m := CUID_RE.search(ln)):
            uid = m.group(1)
            if uid not in ordered_uids:
                ordered_uids.append(uid)

    written_files = []

    # Helper: write a status-specific file
    def _write_by_status(suffix, target_status):
        fn = os.path.join(output_dir, f"{base_name}_{suffix}.m3u")
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(header)
            for uid in ordered_uids:
                if statuses.get(uid) == target_status:
                    entry = entry_map.get(uid)
                    if entry:
                        f.write(build_extinf(entry, update_quality, update_fps))
                        f.write(entry['url'] + '\n')
        written_files.append(fn)

    if split:
        _write_by_status('working', 'UP')
        _write_by_status('blackscreen', 'BLACK_SCREEN')
        _write_by_status('notworking', 'NON_WORKING')
        # Optional merged file including tested channels
        if include_untested:
            fn_all = os.path.join(output_dir, f"{base_name}_all.m3u")
            with open(fn_all, 'w', encoding='utf-8') as f:
                f.write(header)
                for uid in ordered_uids:
                    if statuses.get(uid) in ('UP', 'BLACK_SCREEN', 'NON_WORKING'):
                        entry = entry_map.get(uid)
                        if entry:
                            f.write(build_extinf(entry, update_quality, update_fps))
                            f.write(entry['url'] + '\n')
            written_files.append(fn_all)
    else:
        # Single merged file preserving all channels
        fn_all = os.path.join(output_dir, f"{base_name}_all.m3u")
        with open(fn_all, 'w', encoding='utf-8') as f:
            f.write(header)
            for uid in ordered_uids:
                entry = entry_map.get(uid)
                if entry:
                    f.write(build_extinf(entry, update_quality, update_fps))
                    f.write(entry['url'] + '\n')
        written_files.append(fn_all)

    return written_files
