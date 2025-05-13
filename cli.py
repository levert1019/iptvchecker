# cli.py
import argparse
from config import load_config_from_args
from services.playlist_sorter import PlaylistSorter

def main():
    p = argparse.ArgumentParser(description="IPTV Playlist Sorter")
    p.add_argument("-i","--input", required=True, help="Input .m3u file")
    p.add_argument("-o","--output", required=True, help="Output directory")
    p.add_argument("-g","--groups", nargs="*", help="Groups to sort (default: all)")
    p.add_argument("--tmdb-key", required=True, help="TMDB API key")
    p.add_argument("-w","--workers", type=int, default=10, help="Max concurrent lookups")
    p.add_argument("--add-year", action="store_true", help="Append year to title")
    p.add_argument("--update-name", action="store_true", help="Update tvg-name")
    p.add_argument("--update-banner", action="store_true", help="Update tvg-logo")
    p.add_argument("--export-only-sorted", action="store_true", help="Only export processed entries")
    p.add_argument("--genre-map", help="Path to JSON file with genre overrides")
    args = p.parse_args()

    cfg = load_config_from_args(args)

    def log(level, msg):
        print(f"[{level.upper():7}] {msg}")

    sorter = PlaylistSorter(cfg, logger=log)
    sorter.start()

if __name__ == "__main__":
    main()
