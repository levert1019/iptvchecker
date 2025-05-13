# config.py
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class SortConfig:
    m3u_file: Path
    output_dir: Path
    selected_groups: List[str]
    tmdb_api_key: str
    max_workers: int = 10
    add_year: bool = False
    update_name: bool = False
    update_banner: bool = False
    export_only_sorted: bool = False
    genre_map: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def load_genre_map(path: Optional[Path]) -> Dict[str, str]:
        if path and path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

def load_config_from_args(args) -> SortConfig:
    cfg = SortConfig(
        m3u_file=Path(args.input),
        output_dir=Path(args.output),
        selected_groups=args.groups or [],
        tmdb_api_key=args.tmdb_key,
        max_workers=args.workers,
        add_year=args.add_year,
        update_name=args.update_name,
        update_banner=args.update_banner,
        export_only_sorted=args.export_only_sorted,
        genre_map=SortConfig.load_genre_map(Path(args.genre_map)) if args.genre_map else {}
    )
    return cfg
