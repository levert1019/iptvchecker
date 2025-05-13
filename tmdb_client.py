# tmdb_client.py
import pickle
from pathlib import Path
from typing import Dict, Optional

import aiohttp

CACHE_FILE = Path(".tmdb_cache.pkl")

class TMDBClient:
    def __init__(self, api_key: str, genre_map: Dict[str,str]):
        self.api_key = api_key
        self.genre_map = genre_map
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, dict] = self._load_cache()

    def _load_cache(self) -> Dict[str, dict]:
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "rb") as f:
                    return pickle.load(f)
            except Exception:
                return {}
        return {}

    def save_cache(self):
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(self._cache, f)

    async def search_and_fetch(self, title: str) -> Optional[dict]:
        if title in self._cache:
            return self._cache[title]

        # 1) Search multi
        url_search = "https://api.themoviedb.org/3/search/multi"
        params = {"api_key": self.api_key, "query": title}
        async with self.session.get(url_search, params=params) as resp:
            data = await resp.json()
        results = data.get("results", [])
        detail = None
        if results:
            first = results[0]
            media = first["media_type"]
            _id = first["id"]
            detail = await self._fetch_details(media, _id)

        self._cache[title] = detail or {}
        return detail

    async def _fetch_details(self, media: str, _id: int) -> dict:
        kind = "movie" if media == "movie" else "tv"
        url = f"https://api.themoviedb.org/3/{kind}/{_id}"
        params = {"api_key": self.api_key}
        async with self.session.get(url, params=params) as resp:
            return await resp.json()

    def genre_for(self, detail: dict) -> str:
        if not detail:
            return "Uncategorized"
        genres = detail.get("genres", [])
        name = genres[0]["name"] if genres else "Uncategorized"
        return self.genre_map.get(name, name)
