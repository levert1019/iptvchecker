# services/output_writer.py

import os
import re
from services.utils import resolution_to_label, format_fps

EXTINF_PREFIX = '#EXTINF'
CUID_RE       = re.compile(r'CUID="([^"]+)"')
ATTR_RE       = re.compile(r'([\w-]+)="([^"]*)"')
WRITE_MAP     = {
    'UP': 'working',
    'BLACK_SCREEN': 'black_screen',
    'DOWN': 'non_working'
}

def _build_extinf(orig_extinf: str,
                  entry: dict,
                  update_quality: bool,
                  update_fps: bool) -> str:
    prefix, orig_name = orig_extinf.split(",", 1)
    attrs = dict(ATTR_RE.findall(prefix))

    new_name = orig_name
    if update_quality:
        q = resolution_to_label(entry.get('resolution', ''))
        if q: new_name += f" {q}"
    if update_fps:
        f = format_fps(entry.get('fps', ''))
        if f: new_name += f" {f}"

    attrs['tvg-name'] = new_name
    # Rebuild attribute string in original order
    parts = [f'{k}="{v}"' for k,v in attrs.items()]
    attr_str = " ".join(parts)
    return f'{EXTINF_PREFIX}:0 {attr_str},{new_name}'

def write_output_files(original_lines,
                       entry_map,
                       status_map,
                       base_name,
                       output_dir,
                       split,
                       update_quality,
                       update_fps,
                       include_untested):
    if not any([split, update_quality, update_fps, include_untested]):
        return []

    tested, untested = [], []
    for i, raw in enumerate(original_lines):
        line = raw.rstrip("\n")
        if not line.startswith(EXTINF_PREFIX): continue
        url = original_lines[i+1].rstrip("\n") if i+1 < len(original_lines) else ""
        m = CUID_RE.search(line)
        if not m: continue
        uid = m.group(1)
        st = status_map.get(uid)
        if st:
            tested.append((uid, line, url, st))
        else:
            untested.append((uid, line, url))

    buckets = {'UP': [], 'BLACK_SCREEN': [], 'DOWN': []}
    for uid, ext, url, st in tested:
        key = st if st in buckets else 'DOWN'
        buckets[key].append((uid, ext, url))

    written = []
    def _write(suffix, items):
        path = os.path.join(output_dir, f"{base_name}_{suffix}.m3u")
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for uid, extinf, url in items:
                entry = entry_map.get(uid, {})
                new_ext = _build_extinf(extinf, entry, update_quality, update_fps)
                f.write(new_ext + "\n")
                f.write(url + "\n")
        written.append(path)

    if split:
        for st, items in buckets.items():
            if items: _write(WRITE_MAP[st], items)
        if include_untested:
            all_items = [(uid,ext,url) for uid,ext,url,_ in tested] + untested
            _write('all', all_items)
    else:
        items = [(uid,ext,url,_) for uid,ext,url,_ in tested]
        if include_untested:
            items += untested
        _write('all', [(u,e,u2) for u,e,u2,_ in [(i[0],i[1],i[2],i[3] if len(i)>3 else '') for i in items]])

    return written
