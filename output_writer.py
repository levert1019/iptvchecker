import os
import re
from utils import resolution_to_label, format_fps


def write_output_files(original_lines, entry_map, statuses, base_name, output_dir,
                       split=False, update_quality=False, update_fps=False,
                       include_untested=False):
    """
    Writes M3U output files based on user options.
    - split: if True, outputs separate files for each status.
    - update_quality: append resolution label to channel name.
    - update_fps: append FPS label to channel name.
    - include_untested: include entries never tested.
    Returns a list of generated file paths.
    """
    # Do nothing if no options selected
    if not any([split, update_quality, update_fps, include_untested]):
        return []

    # Organize entries by test status
    groups = {'working': [], 'blackscreen': [], 'notworking': []}
    for cuid, entry in entry_map.items():
        status = statuses.get(cuid, 'untested')
        if status == 'ok':
            groups['working'].append(entry)
        elif status == 'black':
            groups['blackscreen'].append(entry)
        elif status == 'fail':
            groups['notworking'].append(entry)
    
    # Helper to collect untested entries
    untested = [entry for cuid, entry in entry_map.items() if statuses.get(cuid) is None]

    def write(entries, suffix):
        filename = f"{base_name}{suffix}.m3u"
        path = os.path.join(output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for entry in entries:
                ext = build_extinf(entry, update_quality, update_fps)
                f.write(ext + '\n')
                f.write(entry['uri'] + '\n')
        return path

    output_paths = []
    if split:
        output_paths.append(write(groups['working'], '_working'))
        output_paths.append(write(groups['blackscreen'], '_blackscreen'))
        output_paths.append(write(groups['notworking'], '_notworking'))
        if include_untested:
            all_entries = groups['working'] + groups['blackscreen'] + groups['notworking'] + untested
            output_paths.append(write(all_entries, '_all'))
    else:
        combined = groups['working'] + groups['blackscreen'] + groups['notworking']
        if include_untested:
            combined += untested
        output_paths.append(write(combined, '_all'))

    return output_paths


def build_extinf(entry, update_quality=False, update_fps=False):
    """
    Reconstructs the EXTINF line, preserving all original attributes
    and optionally appending resolution/FPS labels to the display name.
    """
    # Copy all original attributes
    attrs = entry.get('attributes', {}).copy()
    # Base display name is from tvg-name or fallback to parsed name
    display_name = attrs.get('tvg-name', entry.get('name', ''))
    # Remove any existing FPS superscripts for fresh labeling
    base_display = re.sub(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+fps', '', display_name)

    # Append resolution label if requested
    if update_quality:
        res_label = resolution_to_label(entry.get('resolution'))
        if res_label:
            base_display = f"{base_display} {res_label}"
            attrs['tvg-name'] = base_display
    # Append FPS label if requested
    if update_fps:
        fps_label = format_fps(entry.get('fps'))
        if fps_label:
            base_display = f"{base_display} {fps_label}"
            attrs['tvg-name'] = base_display

    # Reconstruct attribute string (order preserved by dict)
    attr_str = ' '.join(f'{k}="{v}"' for k, v in attrs.items())
    # Final EXTINF line
    return f"#EXTINF:0 {attr_str},{base_display}"
