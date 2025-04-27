# checker.py
import requests
import subprocess
from typing import Tuple

def check_stream(name: str, url: str, timeout: float = 10.0) -> Tuple[str, str, str, str]:
    """
    Returns (status, resolution, bitrate, fps)
    """
    try:
        r = requests.head(url, timeout=timeout)
        if r.status_code != 200:
            return 'DOWN', '–', '–', '–'
    except Exception:
        return 'DOWN', '–', '–', '–'

    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,bit_rate,r_frame_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        lines = proc.stdout.strip().splitlines()
        if len(lines) < 4:
            return 'BLACK_SCREEN', '–', '–', '–'
        width, height, bitrate, frame_rate = lines[:4]
        if '/' in frame_rate:
            num, den = frame_rate.split('/',1)
            try:
                fps = str(round(float(num)/float(den),2))
            except Exception:
                fps = frame_rate
        else:
            fps = frame_rate
        res = f"{width}×{height}"
        br  = bitrate or '–'
        return 'UP', res, br, fps
    except subprocess.TimeoutExpired:
        return 'BLACK_SCREEN', '–', '–', '–'
    except Exception:
        return 'BLACK_SCREEN', '–', '–', '–'
