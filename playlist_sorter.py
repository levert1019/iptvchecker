# playlist_sorter.py

"""
playlist_sorter.py

Utilities for sorting a parsed IPTV playlist (group_entries) into
new genre-based language-prefixed groups using TMDB metadata.
"""

import re
import requests
from typing import Dict, List, Tuple, Any

# Regex to detect two-letter language prefix at start of title
PREFIX_RE = re.compile(r'^[\|\[]?([A-Za-z]{2})[\]\|\-\s]+(.+)$')

# Map two-letter prefixes to TMDB language codes
LANG_MAP = {
    'EN': 'en-US', 'DE': 'de-DE', 'FR': 'fr-FR', 'ES': 'es-ES', 'IT': 'it-IT',
    'PT': 'pt-PT', 'RU': 'ru-RU', 'PL': 'pl-PL', 'NL': 'nl-NL', 'SV': 'sv-SE',
    'NO': 'no-NO', 'DA': 'da-DK', 'FI': 'fi-FI', 'CS': 'cs-CZ', 'HU': 'hu-HU',
    'JA': 'ja-JP', 'KO': 'ko-KR', 'ZH': 'zh-CN', 'AR': 'ar-SA'
}

TMDB_API_URL   = 'https://api.themoviedb.org/3'
IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/original'

# Regex for Season/Episode suffix
EP_RE = re.compile(r'(S\d{1,2}E\d{1,3})', re.IGNORECASE)

def _detect_prefix(name: str) -> Tuple[str, str]:
    m = PREFIX_RE.match(name)
    if m:
        code = m.group(1).upper()
        remainder = m.group(2).strip()
        return code, remainder
    return 'EN', name

def _fetch_genre_map(api_key: str, media_type: str) -> Dict[int, str]:
    url = f"{TMDB_API_URL}/genre/{media_type}/list"
    resp = requests.get(url, params={'api_key': api_key, 'language': 'en-US'})
    resp.raise_for_status()
    return {g['id']: g['name'] for g in resp.json().get('genres', [])}

def _tmdb_search(query: str, media_type: str, language: str, api_key: str) -> Any:
    endpoint = 'search/movie' if media_type == 'movie' else 'search/tv'
    url = f"{TMDB_API_URL}/{endpoint}"
    resp = requests.get(url, params={'api_key': api_key, 'language': language, 'query': query})
    resp.raise_for_status()
    results = resp.json().get('results', [])
    return results[0] if results else None

def sort_playlist(
    group_entries: Dict[str, List[Dict]],
    categories: Dict[str, List[str]],
    api_key: str
) -> Tuple[Dict[str, List[Dict]], Dict[str, List[str]]]:
    """
    Sorts entries from the 'Movie' and 'Series' categories into new groups
    named "<LANG> - <Genre>" based on TMDB metadata.
    Caches TV searches so we only hit TMDB once per series, and preserves
    the Season/Episode suffix in the entry['name'].
    """
    movie_genres = _fetch_genre_map(api_key, 'movie')
    tv_genres    = _fetch_genre_map(api_key, 'tv')

    new_group_entries: Dict[str, List[Dict]] = {}
    series_cache: Dict[Tuple[str,str], Any] = {}

    for cat, media in (('Movie','movie'), ('Series','tv')):
        for grp in categories.get(cat, []):
            for entry in group_entries.get(grp, []):
                original = entry.get('name','')
                code, remainder = _detect_prefix(original)
                lang = LANG_MAP.get(code, 'en-US')

                # Extract and preserve SxxExx suffix for TV
                suffix = ''
                query = remainder
                if media == 'tv':
                    m = EP_RE.search(remainder)
                    if m:
                        suffix = m.group(1)
                        query  = remainder[:m.start()].strip()

                cache_key = (query.lower(), lang)
                if media == 'tv' and cache_key in series_cache:
                    result = series_cache[cache_key]
                else:
                    result = _tmdb_search(query, media, lang, api_key)
                    if media == 'tv':
                        series_cache[cache_key] = result

                if not result:
                    continue

                tmdb_title = result.get('title') or result.get('name')
                poster     = result.get('poster_path') or result.get('backdrop_path')
                banner_url = f"{IMAGE_BASE_URL}{poster}" if poster else ''

                for gid in result.get('genre_ids', []):
                    genre = (movie_genres if media=='movie' else tv_genres).get(gid)
                    if not genre:
                        continue

                    new_grp = f"{code} - {genre}"
                    new_entry = entry.copy()
                    # Rename to TMDB title + suffix
                    new_entry['name']       = f"{tmdb_title}{(' ' + suffix) if suffix else ''}"
                    new_entry['tmdb_title'] = tmdb_title
                    new_entry['banner_url'] = banner_url
                    new_entry['genres']     = [genre]

                    new_group_entries.setdefault(new_grp, []).append(new_entry)

    new_categories = dict(categories)
    new_categories['Sorted'] = list(new_group_entries.keys())
    return new_group_entries, new_categories
