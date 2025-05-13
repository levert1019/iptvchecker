# services/parser.py
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from services.utils import RegexRules

@dataclass
class Entry:
    raw_inf: str
    url: str
    group: str
    original_name: str
    processed: bool = False
    base: str = ""
    ep_suffix: str = ""
    prefix: str = ""

def parse_groups(m3u_path: str) -> Tuple[dict, List[str]]:
    rules = RegexRules()
    lines = Path(m3u_path).read_text(encoding='utf-8').splitlines()
    groups = {}
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            m = rules.GROUP_RE.search(line)
            grp_name = m.group(1) if m else ""
            url = lines[i+1].strip() if i+1 < len(lines) else ""
            name = line.split(",", 1)[1].strip() if "," in line else ""
            e = Entry(raw_inf=line, url=url, group=grp_name, original_name=name)
            groups.setdefault(grp_name, []).append(e)
    return groups, lines

def clean_entries(entries: List[Entry]) -> None:
    rules = RegexRules()
    for e in entries:
        # prefix
        parts = re.split(r" – |\|", e.group, 1)
        e.prefix = parts[0] + " – " if len(parts) > 1 else ""
        # episode suffix
        m = rules.EPISODE_RE.search(e.original_name)
        e.ep_suffix = m.group(0) if m else ""
        # strip codes, years, multi, episode
        name = rules.PREFIX_RE.sub("", e.original_name)
        name = rules.YEAR_RE.sub("", name)
        name = rules.MULTI_RE.sub("", name)
        name = rules.EPISODE_RE.sub("", name)
        e.base = name.strip()
