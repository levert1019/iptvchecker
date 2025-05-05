from typing import List, Dict
from parser import parse_groups

def sort_entries(
    m3u_path: str,
    group_order: List[str] = None,
    channel_sort_key: str = "name"     # or "resolution", etc.
) -> List[str]:
    """
    1. parse_groups(m3u_path)
    2. iterate over groups in group_order (or sorted(groups) if None)
    3. within each group: sort entries by the requested key
    4. flatten into one list of "#EXTINF" + URL lines
    5. return that list of lines (ready to write)
    """
    group_entries, _ = parse_groups(m3u_path)
    if group_order is None:
        group_order = sorted(group_entries.keys())
    out_lines = ["#EXTM3U\n"]
    for grp in group_order:
        for e in sorted(group_entries[grp], key=lambda x: x[channel_sort_key]):
            out_lines.append(e["raw_extinf"])
            out_lines.append(e["url"] + "\n")
    return out_lines

def write_sorted(
    out_lines: List[str],
    output_path: str
) -> None:
    """Simple file-dump of the sorted m3u."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(out_lines)
