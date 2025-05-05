# services/output_writer.py

import os
import re
from services.utils import resolution_to_label, format_fps

EXTINF_PREFIX = "#EXTINF"
CUID_RE       = re.compile(r'CUID="([^"]+)"')
ATTR_RE       = re.compile(r'([\w-]+)="([^"]*)"')

# Matches any superscript or modifier characters from prior labels
_SUPER_RE = re.compile(
    "[" +
    "\u00B9\u00B2\u00B3\u2070-\u209F" +   # Unicode superscripts
    "\u1D2C-\u1D5C" +                    # Unicode modifiers
    "]+"
)

def _build_extinf(orig_extinf: str,
                  entry: dict,
                  update_quality: bool,
                  update_fps: bool) -> str:
    """
    Rebuilds an EXTINF line by stripping any old quality/FPS labels
    (superscript/barrier chars) and appending the newly detected ones.
    """
    # Split off the comma and display name
    prefix, disp = orig_extinf.split(",", 1)
    # Remove any old superscript bits
    base_name = re.sub(_SUPER_RE, "", disp).strip()

    # Re-parse attributes
    attrs = dict(ATTR_RE.findall(prefix))

    # Construct new display name
    new_name = base_name
    if update_quality:
        q = resolution_to_label(entry.get("resolution", ""))
        if q:
            new_name += f" {q}"
    if update_fps:
        f = format_fps(entry.get("fps", ""))
        if f:
            new_name += f" {f}"

    # Override the tvg-name field
    attrs["tvg-name"] = new_name

    # Re-serialize attributes in original-order-ish
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f'{EXTINF_PREFIX}:0 {attr_str},{new_name}'


def write_output_files(original_lines,
                       entry_map,
                       status_map,
                       base_name,
                       output_dir,
                       split: bool,
                       update_quality: bool,
                       update_fps: bool,
                       include_untested: bool) -> list[str]:
    """
    Writes out one or more M3U files based on the user's settings.
    Returns the list of filepaths written.
    """
    # If no export option is selected, skip
    if not (split or update_quality or update_fps or include_untested):
        return []

    tested = []
    untested = []
    for idx, raw in enumerate(original_lines):
        line = raw.rstrip("\n")
        if not line.startswith(EXTINF_PREFIX):
            continue
        url = original_lines[idx+1].rstrip("\n") if idx+1 < len(original_lines) else ""
        m = CUID_RE.search(line)
        if not m:
            continue
        uid = m.group(1)
        st  = status_map.get(uid)
        if st:
            tested.append((uid, line, url, st))
        else:
            untested.append((uid, line, url))

    # Bucket tested entries
    buckets = {"UP": [], "BLACK_SCREEN": [], "DOWN": []}
    for uid, ext, url, st in tested:
        key = st if st in buckets else "DOWN"
        buckets[key].append((uid, ext, url))

    written_files = []

    def _write(suffix: str, items: list[tuple[str,str,str]]):
        path = os.path.join(output_dir, f"{base_name}_{suffix}.m3u")
        with open(path, "w", encoding="utf-8") as fout:
            fout.write("#EXTM3U\n")
            for uid, extinf, url in items:
                entry = entry_map.get(uid, {})
                new_ext = _build_extinf(extinf, entry, update_quality, update_fps)
                fout.write(new_ext + "\n")
                fout.write(url + "\n")
        written_files.append(path)

    if split:
        # one file per status
        for st, items in buckets.items():
            if items:
                suf = {"UP":"working","BLACK_SCREEN":"black_screen","DOWN":"non_working"}[st]
                _write(suf, items)
        # optional “all” including untested
        if include_untested:
            all_items = [(u, e, u2) for u,e,u2,_ in tested] + untested
            _write("all", all_items)
    else:
        # single “all” file
        items = [(u,e,u2) for u,e,u2,_ in tested]
        if include_untested:
            items += untested
        _write("all", items)

    return written_files
