# services/playlist_sorter.py

import os
import re
import threading
import time
import queue
import requests
from typing import List, Dict, Optional, Tuple

# Regex patterns
EXTINF_RE    = re.compile(r'#EXTINF:.*?(?P<attrs>\s.*?)\s*,(?P<name>.*)$')
GROUP_RE     = re.compile(r'group-title="(?P<group>[^\"]*)"', re.IGNORECASE)
CUID_RE      = re.compile(r'CUID="(?P<uid>[^\"]*)"', re.IGNORECASE)

# Cleaning regexes
_PREFIX_RE   = re.compile(r'^[A-Z]{2,3}(?:\s*[-|]\s*|\s+)')
_YEAR_RE     = re.compile(r'\s*(?:\(\d{4}\)|\d{4})$')
_MULTI_RE    = re.compile(r'[\(\[]?(?:MULTI(?: SUB| AUDIO))[)\]]?', re.IGNORECASE)
_EPISODE_RE  = re.compile(r'\s+[sS]\d{1,2}\s+[eE]\d{1,3}$')

class PlaylistSorter:
    """
    Sorts an M3U playlist by fetching TMDB data in two phases:
      1. Parsing & cleaning base titles
      2. Batch TMDB lookups
      3. Rebuilding EXTINF with proper prefixes, genres, banners, etc.
    """
    def __init__(self):
        self.api_key            = ""
        self.max_workers        = 4
        self.add_year           = False
        self.update_name        = False
        self.update_banner      = False
        self.export_only_sorted = False

        # Default logger (overridden by controller)
        self.logger = lambda lvl, msg: print(f"[{lvl.upper()}] {msg}")

        # Internal events & caches
        self._stop_event   = threading.Event()
        self._pause_event  = threading.Event()
        self._series_cache = {}  # base_title -> (media_type, id)
        self._name_counts  = {}  # display_name -> count

    def start(self,
              m3u_path: str,
              output_dir: Optional[str],
              selected_groups: Optional[List[str]] = None):
        # Reset state
        self._stop_event.clear()
        self._pause_event.clear()
        self._series_cache.clear()
        self._name_counts.clear()

        outd = output_dir or os.getcwd()
        base = os.path.splitext(os.path.basename(m3u_path))[0]
        out_file = os.path.join(outd, f"{base}_sorted.m3u")

        # Phase 1: parse and clean entries
        with open(m3u_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]

        self.logger('info', f"Loaded {len(lines)} lines from {m3u_path}")

        entries = []  # list of dicts for each EXTINF entry
        for idx, line in enumerate(lines):
            if not line.startswith("#EXTINF"):
                continue
            url = lines[idx+1] if idx+1 < len(lines) else ""
            m = EXTINF_RE.match(line)
            if not m:
                continue
            attrs_str = m.group("attrs")
            name = m.group("name")
            attrs = dict(re.findall(r'([\w-]+)="([^" ]*)"', attrs_str))
            group = attrs.get("group-title", "")

            # Extract season/episode suffix
            ep_match = _EPISODE_RE.search(name)
            ep_suffix = ep_match.group(0) if ep_match else ""

            # Strip cleaning tokens for base title
            clean = name
            clean = _PREFIX_RE.sub("", clean)
            clean = _YEAR_RE.sub("", clean)
            clean = _MULTI_RE.sub("", clean)
            clean = clean.strip()
            # Remove episode suffix
            clean = _EPISODE_RE.sub("", clean).strip()

            entries.append({
                "idx": idx,
                "raw_extinf": line,
                "url": url,
                "attrs": attrs,
                "group": group,
                "prefix": group[:group.find(clean)] if clean in group else "",
                "base_title": clean,
                "ep_suffix": ep_suffix
            })

        # Filter and unique titles
        filtered = [e for e in entries if not selected_groups or e["group"] in selected_groups]
        unique_titles = {e["base_title"] for e in filtered}
        self.logger('info', f"TMDB lookup for {len(unique_titles)} unique titles")

        # Phase 2: batch TMDB lookup
        for title in unique_titles:
            if self._stop_event.is_set():
                break
            while self._pause_event.is_set():
                time.sleep(0.1)
            tmdb = self._search_tmdb(title)
            if tmdb:
                self._series_cache[title] = tmdb

        # Phase 3: rebuild EXTINF lines
        out_lines = ["#EXTM3U"]
        for e in entries:
            if self._stop_event.is_set():
                break
            while self._pause_event.is_set():
                time.sleep(0.1)

            if selected_groups and e["group"] not in selected_groups:
                if not self.export_only_sorted:
                    out_lines.append(e["raw_extinf"])
                    out_lines.append(e["url"])
                continue

            tmdb = self._series_cache.get(e["base_title"])
            if not tmdb:
                self.logger('error', f"No TMDB result for '{e['base_title']}'")
                if not self.export_only_sorted:
                    out_lines.append(e["raw_extinf"])
                    out_lines.append(e["url"])
                continue

            media_type, tmdb_id = tmdb
            detail = self._get_tmdb_details(media_type, tmdb_id)
            if not detail:
                self.logger('error', f"Failed TMDB details for '{e['base_title']}'")
                if not self.export_only_sorted:
                    out_lines.append(e["raw_extinf"])
                    out_lines.append(e["url"])
                continue

            # Build new attributes
            genres = detail.get("genres", [])
            genre = genres[0]["name"] if genres else "Uncategorized"
            grp = f"{e['prefix']}{genre}"
            attrs = e["attrs"].copy()
            attrs["group-title"] = grp

            if self.update_banner and detail.get("poster_path"):
                attrs["tvg-logo"] = f"https://image.tmdb.org/t/p/w500{detail['poster_path']}"

            # Display name
            new_name = detail.get("title") or detail.get("name") or e["base_title"]
            if self.add_year:
                y = (detail.get("release_date") or detail.get("first_air_date") or "")[:4]
                if y:
                    new_name += f" ({y})"

            # Handle duplicates
            count = self._name_counts.get(new_name, 0) + 1
            self._name_counts[new_name] = count
            suffix = f" #{count}" if count > 1 else ""
            disp_name = new_name + suffix + e["ep_suffix"]

            if self.update_name:
                attrs["tvg-name"] = disp_name

            # Serialize EXTINF
            attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
            new_ext = f"#EXTINF:0 {attr_str},{disp_name}"
            out_lines.append(new_ext)
            out_lines.append(e["url"])

            self.logger('working', f"{disp_name} → {grp}")

        # Write out file
        with open(out_file, "w", encoding="utf-8") as f:
            for line in out_lines:
                f.write(line + "\n")

        self.logger('info', f"Written sorted playlist to {out_file}")

    def _search_tmdb(self, query: str) -> Optional[Tuple[str,int]]:
        url = "https://api.themoviedb.org/3/search/multi"
        params = {"api_key": self.api_key, "query": query}
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                return None
            first = results[0]
            return first.get("media_type"), first.get("id")
        except Exception as e:
            self.logger('error', f"TMDB search error '{query}': {e}")
            return None

    def _get_tmdb_details(self, media_type: str, tmdb_id: int) -> Optional[dict]:
        if media_type == "movie":
            path = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        elif media_type == "tv":
            path = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
        else:
            return {}
        try:
            r = requests.get(path, params={"api_key": self.api_key}, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            self.logger('error', f"TMDB details error for '{query}': {e}")
            return {}
