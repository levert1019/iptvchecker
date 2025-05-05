#!/usr/bin/env python3
"""
playlist_sorter.py

Reads an M3U playlist, searches TMDB for each entry's movie/series,
updates group-title to "PREFIX - Genre" and optionally updates the displayed
name (localized and/or with year), then writes out a new M3U file.
"""

import os
import re
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

CONFIG_FILE = "config.json"

# Regex to extract the existing group-title attribute
GROUP_TITLE_RE = re.compile(r'group-title="([^"]*)"')
# Strip two-letter uppercase country prefixes in names
PREFIX_NAME_RE = re.compile(r'^[A-Z]{2}\s*-\s*')
# Capture a four-digit year in parentheses
YEAR_RE = re.compile(r'\((\d{4})\)')

class PlaylistSorter:
    def __init__(self):
        # Load config.json
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
        self.api_key     = cfg.get("tmdb_api_key", "").strip()
        self.max_workers = cfg.get("playlist_workers", 4)
        self.add_year    = cfg.get("add_year_to_name", False)
        self.update_name = cfg.get("update_name", False)

        # Thread control flags
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()

    def start(self, m3u_path: str, output_path: str = None):
        """
        Begin processing. 
        m3u_path: path to input .m3u file.
        output_path: optional path for output; defaults to "<input>_sorted.m3u".
        """
        if not os.path.isfile(m3u_path):
            print(f"[ERROR] M3U file not found: {m3u_path}")
            return
        if not self.api_key:
            print("[ERROR] No TMDB API key set in config.json")
            return

        self._stop_event.clear()
        self._pause_event.clear()

        # Determine output filename
        if output_path:
            self.output_path = output_path
        else:
            base, ext = os.path.splitext(m3u_path)
            self.output_path = f"{base}_sorted{ext}"

        # Read all lines
        with open(m3u_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.rstrip("\n") for line in f]

        # Collect indices of EXTINF + URL pairs
        entries = []
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF"):
                if i + 1 < len(lines):
                    entries.append((i, line, lines[i + 1]))

        print(f"[INFO] {len(entries)} entries found.")

        # Concurrently process entries
        results = [None] * len(entries)
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {
                pool.submit(self._process_entry, idx, extinf, url): idx
                for idx, (_, extinf, url) in enumerate(entries)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    new_extinf, new_url = future.result()
                    results[idx] = (new_extinf, new_url)
                except Exception as e:
                    print(f"[ERROR] Entry #{idx} failed: {e}")
                    # Fall back to original
                    results[idx] = (entries[idx][1], entries[idx][2])

        # Reconstruct the playlist
        out_lines = []
        # Map original extinf/url → new
        extinf_map = {entries[i][1]: results[i][0] for i in range(len(entries))}
        url_map    = {entries[i][2]: results[i][1] for i in range(len(entries))}

        skip_next = False
        for line in lines:
            if skip_next:
                # write the URL for the last EXTINF
                out_lines.append(url_map.get(prev_url, prev_url))
                skip_next = False
                continue
            if line.startswith("#EXTINF"):
                new_ext = extinf_map.get(line, line)
                out_lines.append(new_ext)
                prev_url = lines[lines.index(line) + 1]
                skip_next = True
            else:
                # preserve comments or other metadata lines
                out_lines.append(line)

        # Write out the new file
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines) + "\n")

        print(f"[INFO] Sorted playlist written to {self.output_path}")

    def pause(self):
        """
        Toggle pause/resume.
        """
        if self._pause_event.is_set():
            print("[INFO] Resuming")
            self._pause_event.clear()
        else:
            print("[INFO] Pausing")
            self._pause_event.set()

    def stop(self):
        """
        Signal all threads to stop ASAP.
        """
        print("[INFO] Stopping")
        self._stop_event.set()

    def _process_entry(self, idx, extinf, url):
        """
        Internal: process a single entry.
        Returns (new_extinf_line, url).
        """
        # allow stop
        if self._stop_event.is_set():
            raise InterruptedError("Stopped by user")

        # handle pause
        while self._pause_event.is_set():
            time.sleep(0.1)

        # split EXTINF into attributes + displayed name
        parts = extinf.split(",", 1)
        attrs     = parts[0]
        orig_name = parts[1] if len(parts) > 1 else ""

        # extract original group-title
        m = GROUP_TITLE_RE.search(attrs)
        orig_group = m.group(1) if m else ""
        # get prefix (e.g. "EN" from "EN - Something")
        prefix = orig_group.split(" - ")[0].strip() if " - " in orig_group else ""

        # clean the displayed name for TMDB search
        search_name = orig_name
        # strip country-code prefix in name itself
        if prefix and search_name.upper().startswith(prefix.upper()):
            search_name = re.sub(rf'^{re.escape(prefix)}\s*-\s*', "", search_name)
        # strip any two-letter uppercase prefix
        search_name = PREFIX_NAME_RE.sub("", search_name)
        # extract year if present
        ymatch = YEAR_RE.search(search_name)
        year   = ymatch.group(1) if ymatch else ""
        search_name = YEAR_RE.sub("", search_name).strip()

        print(f"[WORKING] #{idx} searching TMDB for \"{search_name}\"")
        res = self._search_tmdb(search_name)
        if not res:
            print(f"[ERROR] No TMDB match for \"{search_name}\"")
            return extinf, url

        mtype  = res.get("media_type") or ("movie" if "title" in res else "tv")
        tmdb_id = res["id"]
        detail = self._get_tmdb_details(mtype, tmdb_id)
        if not detail:
            print(f"[ERROR] Failed to fetch details for ID {tmdb_id}")
            return extinf, url

        # pick the first genre
        genres = [g["name"] for g in detail.get("genres", [])]
        genre  = genres[0] if genres else "Unknown"
        new_group = f"{prefix} - {genre}" if prefix else genre

        # build the new displayed name
        if self.update_name:
            localized = self._get_localized_name(mtype, tmdb_id, prefix)
            base_name = localized or detail.get("title" if mtype=="movie" else "name", orig_name)
        else:
            base_name = orig_name

        if self.add_year and year:
            new_name = f"{base_name.strip()} ({year})"
        else:
            new_name = base_name

        # replace or inject group-title in attrs
        if GROUP_TITLE_RE.search(attrs):
            new_attrs = GROUP_TITLE_RE.sub(f'group-title="{new_group}"', attrs)
        else:
            new_attrs = attrs + f' group-title="{new_group}"'

        new_extinf = f"{new_attrs},{new_name}"
        print(f"[INFO] #{idx} → group: \"{new_group}\", name: \"{new_name}\"")
        return new_extinf, url

    def _search_tmdb(self, query: str):
        """
        Use TMDB's multi-search endpoint.
        """
        url = "https://api.themoviedb.org/3/search/multi"
        params = {"api_key": self.api_key, "query": query, "include_adult": False}
        r = requests.get(url, params=params)
        if r.status_code != 200:
            return None
        data = r.json().get("results", [])
        return data[0] if data else None

    def _get_tmdb_details(self, media_type: str, tmdb_id: int):
        """
        Fetch the full details endpoint to retrieve genres & dates.
        """
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
        r = requests.get(url, params={"api_key": self.api_key})
        if r.status_code != 200:
            return None
        return r.json()

    def _get_localized_name(self, media_type: str, tmdb_id: int, prefix: str):
        """
        Fetch translations and pick the title/name matching the two-letter prefix
        (ISO 639-1 code).
        """
        iso = prefix.lower()
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/translations"
        r = requests.get(url, params={"api_key": self.api_key})
        if r.status_code != 200:
            return None
        for t in r.json().get("translations", []):
            if t.get("iso_639_1") == iso:
                d = t.get("data", {})
                return d.get("title") or d.get("name")
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python playlist_sorter.py <input.m3u> [output.m3u]")
        sys.exit(1)
    sorter = PlaylistSorter()
    in_file  = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else None
    sorter.start(in_file, out_file)
