# services/playlist_sorter.py
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
import re
import aiohttp

from services.parser import parse_groups, clean_entries, Entry
from tmdb_client import TMDBClient
from config import SortConfig

# Regex to extract key="value" pairs
_ATTR_REGEX = re.compile(r'(\w+?)="([^"]*)"')
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

class PlaylistSorter:
    """
    Sorts M3U playlists using TMDB lookups. Ensures single EXTINF output with controlled attributes.
    """
    def __init__(self, cfg: SortConfig, logger):
        self.cfg = cfg
        self.logger = logger
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_event = asyncio.Event()

    def _parse_extinf(self, line: str) -> (Dict[str,str], str):
        # Remove leading tag
        body = line[len("#EXTINF:"):].strip()
        # Split into attrs and name
        if ',' in body:
            attr_part, name = body.split(',', 1)
        else:
            attr_part, name = body, ''
        attrs = {m.group(1): m.group(2) for m in _ATTR_REGEX.finditer(attr_part)}
        return attrs, name.strip()

    async def _lookup_all(self, titles: List[str], client: TMDBClient):
        sem = asyncio.Semaphore(self.cfg.max_workers)
        async def lookup(title: str):
            await self._pause_event.wait()
            if self._stop_event.is_set(): return
            async with sem:
                self.logger('info', f"Looking up '{title}' …")
                detail = await client.search_and_fetch(title)
                if detail:
                    self.logger('found', f"Found '{title}'")
                else:
                    self.logger('error', f"No result for '{title}'")
        await asyncio.gather(*(lookup(t) for t in titles))

    async def _sort_async(self):
        # Read and parse
        groups, _ = parse_groups(str(self.cfg.m3u_file))
        entries = [e for grp in groups.values() for e in grp]

        # Mark processing
        selected = set(self.cfg.selected_groups) or set(groups.keys())
        for e in entries: e.processed = (e.group in selected)

        clean_entries(entries)
        titles = [e.base for e in entries if e.processed]

        # TMDB client
        async with aiohttp.ClientSession() as session:
            client = TMDBClient(self.cfg.tmdb_api_key, self.cfg.genre_map)
            client.session = session
            await self._lookup_all(titles, client)
            client.save_cache()

        # Write output
        out_file = Path(self.cfg.output_dir) / f"{self.cfg.m3u_file.stem}_sorted.m3u"
        with open(out_file, 'w', encoding='utf-8') as fw:
            fw.write("#EXTM3U\n")
            for e in entries:
                attrs, orig_name = self._parse_extinf(e.raw_inf)
                # Skip unprocessed if only sorted
                if not e.processed:
                    if self.cfg.export_only_sorted: continue
                    fw.write(f"{e.raw_inf}\n{e.url}\n")
                    continue
                # Build new
                detail = client._cache.get(e.base, {}) or {}
                # Display name
                if self.cfg.update_name and detail:
                    name = detail.get('title') or detail.get('name') or e.base
                    if self.cfg.add_year and 'release_date' in detail:
                        name += f" ({detail['release_date'][:4]})"
                    if e.ep_suffix: name += f" {e.ep_suffix}"
                else:
                    name = orig_name
                # Attributes
                new_attrs = {}
                new_attrs['tvg-id'] = attrs.get('tvg-id', '')
                new_attrs['tvg-name'] = name
                # Logo
                if self.cfg.update_banner and detail.get('poster_path'):
                    new_attrs['tvg-logo'] = TMDB_IMAGE_BASE + detail['poster_path']
                else:
                    new_attrs['tvg-logo'] = attrs.get('tvg-logo', attrs.get('logo', ''))
                # Group
                genre = client.genre_for(detail)
                new_attrs['group-title'] = f"{e.prefix}{genre}"
                # Build line
                attr_str = ' '.join(f'{k}="{v}"' for k,v in new_attrs.items())
                fw.write(f"#EXTINF:-1 {attr_str},{name}\n{e.url}\n")
        self.logger('info', f"Wrote sorted playlist to {out_file}")

    def start(self):
        asyncio.run(self._sort_async())
    def pause(self): self._pause_event.clear(); self.logger('info', 'Paused')
    def resume(self): self._pause_event.set(); self.logger('info', 'Resumed')
    def stop(self): self._stop_event.set(); self.logger('info', 'Stopped')
