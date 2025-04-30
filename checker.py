import subprocess
import time
from typing import Tuple
from urllib.request import urlopen

def check_stream(name: str, url: str, timeout: float = 10.0) -> Tuple[str, str, str, str]:
    """
    1) Test basic connectivity via HTTP
    2) Detect full-black streams with ffmpeg over 2s
    3) Probe resolution, bitrate, and FPS with ffprobe

    Uses per-channel timeout: if a channel is DOWN, waits remaining timeout;
    UP or BLACK_SCREEN returns immediately.
    """
    start = time.monotonic()

    def _finish(status: str, res: str, br: str, fps: str) -> Tuple[str,str,str,str]:
        # Only delay if channel is DOWN
        if status == 'DOWN':
            elapsed = time.monotonic() - start
            if elapsed < timeout:
                time.sleep(timeout - elapsed)
        return status, res, br, fps

    # 1) Connectivity check
    try:
        resp = urlopen(url, timeout=timeout)
        resp.close()
    except Exception:
        return _finish('DOWN', '–', '–', '–')

    # 2) Black screen detection via ffmpeg
    try:
        proc = subprocess.run(
            [
                'ffmpeg', '-hide_banner', '-v', 'error',
                '-t', '2', '-i', url,
                '-vf', 'blackdetect=d=2:pix_th=0.98',
                '-an', '-f', 'null', '-'
            ],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=timeout
        )
        stderr = proc.stderr or ''
    except subprocess.TimeoutExpired:
        return _finish('DOWN', '–', '–', '–')
    except Exception:
        return _finish('DOWN', '–', '–', '–')

    if 'blackdetect' in stderr:
        return 'BLACK_SCREEN', '–', '–', '–'

    # 3) ffprobe info
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate,bit_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        url
    ]
    try:
        proc2 = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        lines = proc2.stdout.strip().splitlines()
    except subprocess.TimeoutExpired:
        return _finish('DOWN', '–', '–', '–')
    except Exception:
        return _finish('DOWN', '–', '–', '–')

    if len(lines) < 4:
        return _finish('DOWN', '–', '–', '–')

    width_s, height_s, rfr, bitrate_s = lines[:4]
    res = f"{width_s}×{height_s}" if width_s.isdigit() and height_s.isdigit() else '–'
    br = bitrate_s if bitrate_s.isdigit() else '–'

    # parse FPS
    fps_value = '–'
    if rfr:
        try:
            if '/' in rfr:
                num, den = rfr.split('/', 1)
                fps_calc = float(num) / float(den)
            else:
                fps_calc = float(rfr)
            fps_value = str(round(fps_calc, 2))
        except:
            fps_value = '–'

    # Successful streams return immediately
    return 'UP', res, br, fps_value
