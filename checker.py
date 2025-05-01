import subprocess
import time
from typing import Tuple
from urllib.request import urlopen

def check_stream(name: str, url: str, timeout: float = 10.0) -> Tuple[str, str, str, str]:
    """
    1) Probe via ffprobe (connectivity + resolution/bitrate/fps) with network timeout.
    2) If probe succeeds, run ffmpeg blackdetect over 2s to detect full-black.
    3) DOWN results wait out the full timeout; UP/BLACK_SCREEN return immediately.
    """
    start = time.monotonic()

    def _finish(status: str, res: str, br: str, fps: str) -> Tuple[str, str, str, str]:
        # If DOWN, block until the full timeout has elapsed
        if status == 'DOWN':
            elapsed = time.monotonic() - start
            if elapsed < timeout:
                time.sleep(timeout - elapsed)
        return status, res, br, fps

    # --- 1) ffprobe check + metadata ---
    probe_cmd = [
        'ffprobe',
        '-v', 'error',
        '-timeout', str(int(timeout * 1_000_000)),  # microseconds
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate,bit_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        url
    ]
    try:
        proc = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return _finish('DOWN', '–', '–', '–')
    except Exception:
        return _finish('DOWN', '–', '–', '–')

    if proc.returncode != 0:
        return _finish('DOWN', '–', '–', '–')

    lines = proc.stdout.strip().splitlines()
    if len(lines) < 4:
        return _finish('DOWN', '–', '–', '–')

    width_s, height_s, rfr, bitrate_s = lines[:4]
    res = f"{width_s}×{height_s}" if width_s.isdigit() and height_s.isdigit() else '–'
    br = bitrate_s if bitrate_s.isdigit() else '–'

    # parse and round FPS to nearest integer
    fps_val = '–'
    try:
        if '/' in rfr:
            num, den = rfr.split('/', 1)
            fps_calc = float(num) / float(den)
        else:
            fps_calc = float(rfr)
        fps_val = str(int(round(fps_calc)))
    except Exception:
        fps_val = rfr or '–'

    # --- 2) Black-screen detection ---
    try:
        ff_cmd = [
            'ffmpeg', '-hide_banner', '-v', 'error',
            '-t', '2', '-i', url,
            '-vf', 'blackdetect=d=2:pix_th=0.98',
            '-an', '-f', 'null', '-'
        ]
        p2 = subprocess.run(
            ff_cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=min(2, timeout)
        )
        stderr = p2.stderr or ''
        if 'blackdetect' in stderr:
            return 'BLACK_SCREEN', '–', '–', '–'
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    # --- 3) UP: return immediately ---
    return 'UP', res, br, fps_val
