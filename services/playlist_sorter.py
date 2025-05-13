# services/playlist_sorter.py

import os
import re
import threading
import time
import queue
import requests
from typing import List, Dict, Optional, Tuple
from services.parser import parse_groups

# Regex patterns for cleaning names
_PREFIX_RE   = re.compile(r'^[A-Z]{2,3}(?:\s*[-|]\s*|\s+)')
_YEAR_RE     = re.compile(r'\s*(?:\(\d{4}\)|\d{4})$')
_MULTI_RE    = re.compile(r'[\(\[]?(?:MULTI(?: SUB| AUDIO))[)\]]?', re.IGNORECASE)
_EPISODE_RE  = re.compile(r'\s+[sS]\d{1,2}\s*[eE]\d{1,3}', re.IGNORECASE)

class PlaylistSorter:
    """
    Sorts an M3U playlist by fetching TMDB data in parallel:
      - Filters entries by selected_groups (or all if none specified).
      - Cleans names (prefix, year, multi-sub/audio) and extracts episode suffix.
      - Performs TMDB lookup once per unique clean title using max_workers.
      - Rebuilds EXTINF lines preserving prefix and re-appending episode suffix.
    """
    def __init__(self):
        self.api_key            = ""
        self.max_workers        = 4
        self.add_year           = False
        self.update_name        = False
        self.update_banner      = False
        self.export_only_sorted = False

        # Controller will override logger to emit GUI signals
        self.logger = lambda lvl, msg: print(f"[{lvl.upper()}] {msg}")

        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()

    def start(self,
              m3u_path: str,
              output_dir: Optional[str],
              selected_groups: Optional[List[str]] = None):
        # Reset control events
        self._stop_event.clear()
        self._pause_event.clear()

        # Parse group entries
        group_entries, _ = parse_groups(m3u_path)
        # Determine groups to process
        if selected_groups:
            groups = [g for g in selected_groups if g in group_entries]
        else:
            groups = list(group_entries.keys())
            self.logger('info', f"No groups selected: defaulting to all {len(groups)}")

        # Flatten entries preserving order
        entries = []  # Each: {'raw_extinf','url','group','name','processed'}
        with open(m3u_path, 'r', encoding='utf-8') as f:
            lines = [l.rstrip('\n') for l in f]
        for i, line in enumerate(lines):
            if not line.startswith('#EXTINF'):
                continue
            url = lines[i+1] if i+1 < len(lines) else ''
            m = re.search(r'group-title="([^"]*)"', line)
            grp = m.group(1) if m else ''
            processed = grp in groups
            name = line.split(',', 1)[1] if processed and ',' in line else ''
            entries.append({
                'raw_extinf': line,
                'url': url,
                'group': grp,
                'name': name,
                'processed': processed
            })
        total = sum(1 for e in entries if e['processed'])
        self.logger('info', f"Found {total} entries in {len(groups)} group(s)")

        # Clean names and extract unique titles
        cleaned = []  # list of tuples (base_title, ep_suffix, prefix)
        for e in entries:
            if not e['processed']:
                continue
            raw_grp = e['group']
            pref_m = re.match(r'^(.+?)(?: \- |\| )', raw_grp)
            prefix = (pref_m.group(1).strip() + ' - ') if pref_m else ''
            name = e['name']
            ep_m = _EPISODE_RE.search(name)
            ep_suffix = ep_m.group(0) if ep_m else ''
            base = name
            base = _PREFIX_RE.sub('', base)
            base = _YEAR_RE.sub('', base)
            base = _MULTI_RE.sub('', base)
            base = _EPISODE_RE.sub('', base)
            base = base.strip()
            cleaned.append((base, ep_suffix, prefix))
        unique_titles = {base for base,_,_ in cleaned}
        self.logger('info', f"TMDB lookup for {len(unique_titles)} unique titles")

        # Perform parallel TMDB lookups
        title_queue = queue.Queue()
        for title in unique_titles:
            title_queue.put(title)
        tmdb_cache: Dict[str, Optional[Tuple[str,int]]] = {}
        cache_lock = threading.Lock()

        def worker():
            while not self._stop_event.is_set():
                try:
                    title = title_queue.get(timeout=0.1)
                except queue.Empty:
                    return
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.1)
                self.logger('info', f"Looking up '{title}' on TMDB and fetching genre")
                res = self._search_tmdb(title)
                genre = 'Uncategorized'
                if res:
                    mtype, mid = res
                    detail = self._get_tmdb_details(mtype, mid)
                    if detail:
                        genres = detail.get('genres') or []
                        if genres and isinstance(genres, list) and len(genres) > 0:
                            name_val = genres[0].get('name')
                            if name_val:
                                genre = name_val
                with cache_lock:
                    tmdb_cache[title] = (res, genre)
                title_queue.task_done()

        threads = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        # Rebuild playlist
        out_lines = ['#EXTM3U']
        name_counts: Dict[str,int] = {}
        # Use iterator over cleaned for order
        clean_iter = iter(cleaned)
        for e in entries:
            if not e['processed']:
                out_lines.append(e['raw_extinf'])
                out_lines.append(e['url'])
                continue
            base, ep_suffix, prefix = next(clean_iter)
            cache_entry = tmdb_cache.get(base)
            if not cache_entry:
                self.logger('error', f"No TMDB data for '{base}'")
                if not self.export_only_sorted:
                    out_lines.append(e['raw_extinf'])
                    out_lines.append(e['url'])
                continue
            res, genre = cache_entry
            if not res:
                self.logger('error', f"No TMDB result for '{base}'")
                if not self.export_only_sorted:
                    out_lines.append(e['raw_extinf'])
                    out_lines.append(e['url'])
                continue
            mtype, mid = res
            detail = self._get_tmdb_details(mtype, mid)
            attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', e['raw_extinf'].split(' ',1)[1]))
            grp_new = prefix + genre
            attrs['group-title'] = grp_new
            if self.update_banner and detail and detail.get('poster_path'):
                attrs['tvg-logo'] = f"https://image.tmdb.org/t/p/w500{detail['poster_path']}"
            name_new = detail.get('title') or detail.get('name') or base
            if self.add_year:
                y = (detail.get('release_date') or detail.get('first_air_date') or '')[:4]
                if y:
                    name_new += f" ({y})"
            count = name_counts.get(name_new,0)+1
            name_counts[name_new] = count
            disp = name_new + (f" #{count}" if count>1 else '') + ep_suffix
            if self.update_name:
                attrs['tvg-name'] = disp
            attr_str = ' '.join(f'{k}="{v}"' for k,v in attrs.items())
            out_lines.append(f"#EXTINF:0 {attr_str},{disp}")
            out_lines.append(e['url'])
            self.logger('working', f"{disp} → {grp_new}")

        out_path = os.path.join(output_dir or os.getcwd(),
                                 os.path.splitext(os.path.basename(m3u_path))[0] + '_sorted.m3u')
        with open(out_path, 'w', encoding='utf-8') as f:
            for line in out_lines:
                f.write(line + '\n')

        self.logger('info', f"Written sorted playlist to {out_path}")

    def pause(self):
        self._pause_event.set()
        self.logger('info', "Sorter paused")

    def resume(self):
        self._pause_event.clear()
        self.logger('info', "Sorter resumed")

    def stop(self):
        self._stop_event.set()
        self.logger('info', "Stopping sorter")

    def _search_tmdb(self, query: str) -> Optional[Tuple[str,int]]:
        url = 'https://api.themoviedb.org/3/search/multi'
        try:
            r = requests.get(url, params={'api_key': self.api_key, 'query': query}, timeout=10)
            r.raise_for_status()
            results = r.json().get('results', [])
            if not results:
                return None
            first = results[0]
            return first.get('media_type'), first.get('id')
        except Exception as e:
            self.logger('error', f"TMDB search error '{query}': {e}")
            return None

    def _get_tmdb_details(self, media_type: str, tmdb_id: int) -> Optional[dict]:
        if media_type == 'movie':
            path = f'https://api.themoviedb.org/3/movie/{tmdb_id}'
        elif media_type == 'tv':
            path = f'https://api.themoviedb.org/3/tv/{tmdb_id}'
        else:
            return {}
        try:
            r = requests.get(path, params={'api_key': self.api_key}, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            self.logger('error', f"TMDB details error for '{media_type}': {e}")
            return None
