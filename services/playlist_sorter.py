# services/playlist_sorter.py
import asyncio
import re
from pathlib import Path
from typing import Set, Optional, Dict

import aiohttp

from services.parser import parse_groups, clean_entries, Entry
from tmdb_client import TMDBClient
from config import SortConfig

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
_ATTR_RE = re.compile(r'(\w+?)="([^"]*)"')

class PlaylistSorter:
    """
    Handles sorting of M3U playlists using TMDB for genre lookups,
    supports pause/resume/stop, and updates tvg attributes and banner.
    """
    def __init__(self, cfg: SortConfig, logger):
        self.cfg = cfg
        self.logger = logger
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_event = asyncio.Event()

    async def _sort(self):
        # Parse and flatten all entries
        groups, _ = parse_groups(str(self.cfg.m3u_file))
        entries = [e for grp in groups.values() for e in grp]

        # Mark which entries to process
        selected: Set[str] = set(self.cfg.selected_groups) or set(groups.keys())
        for e in entries:
            e.processed = e.group in selected

        # Clean titles for TMDB lookup
        clean_entries(entries)
        titles = {e.base for e in entries if e.processed}

        # Async TMDB lookups
        async with aiohttp.ClientSession() as session:
            client = TMDBClient(self.cfg.tmdb_api_key, self.cfg.genre_map)
            client.session = session
            sem = asyncio.Semaphore(self.cfg.max_workers)

            async def lookup(title: str) -> Optional[dict]:
                await self._pause_event.wait()
                if self._stop_event.is_set():
                    return None
                async with sem:
                    self.logger('info', f"Looking up '{title}' …")
                    detail = await client.search_and_fetch(title)
                    if detail:
                        self.logger('found', f"Found '{title}'")
                    else:
                        self.logger('error', f"No result for '{title}'")
                    return detail

            tasks = [asyncio.create_task(lookup(t)) for t in titles]
            await asyncio.gather(*tasks)
            client.save_cache()

        # Write output M3U
        out_path = Path(self.cfg.output_dir) / f"{Path(self.cfg.m3u_file).stem}_sorted.m3u"
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            for e in entries:
                # Parse original attributes and name
                raw_inf = e.raw_inf
                attrs_text = raw_inf[len("#EXTINF:"):].split(",", 1)[0]
                orig_attrs = {m.group(1): m.group(2) for m in _ATTR_RE.finditer(attrs_text)}

                if not e.processed:
                    if self.cfg.export_only_sorted:
                        continue
                    # write original entry
                    f.write(f"{raw_inf}\n{e.url}\n")
                else:
                    # Determine TMDB detail and genre
                    detail = client._cache.get(e.base, {})
                    genre = client.genre_for(detail)
                    prefix = e.prefix

                    # Build attributes dict
                    new_attrs: Dict[str, str] = {}
                    # Preserve tvg-id if exists
                    new_attrs['tvg-id'] = orig_attrs.get('tvg-id', '')
                    # tvg-name
                    if self.cfg.update_name and detail:
                        name = detail.get('title') or detail.get('name') or e.base
                        if self.cfg.add_year and detail.get('release_date'):
                            name += f" ({detail['release_date'][:4]})"
                        if e.ep_suffix:
                            name += f" {e.ep_suffix}"
                        new_attrs['tvg-name'] = name
                        display = name
                    else:
                        display = orig_attrs.get('tvg-name', e.original_name)
                        new_attrs['tvg-name'] = display
                    # tvg-logo
                    if self.cfg.update_banner and detail.get('poster_path'):
                        new_attrs['tvg-logo'] = TMDB_IMAGE_BASE + detail['poster_path']
                    else:
                        # fallback to original tvg-logo or logo
                        new_attrs['tvg-logo'] = orig_attrs.get('tvg-logo', orig_attrs.get('logo', ''))
                    # group-title: prefix + genre
                    new_attrs['group-title'] = f"{prefix}{genre}"

                    # Reconstruct EXTINF line
                    attr_str = ' '.join(f'{k}="{v}"' for k, v in new_attrs.items())
                    f.write(f"#EXTINF:-1 {attr_str},{display}\n{e.url}\n")

        self.logger('info', f"Wrote sorted playlist to {out_path}")

    def start(self):
        asyncio.run(self._sort())

    def pause(self):
        self._pause_event.clear()
        self.logger('info', "Sorting paused.")

    def resume(self):
        self._pause_event.set()
        self.logger('info', "Sorting resumed.")

    def stop(self):
        self._stop_event.set()
        self.logger('info', "Sorting stopped.")
