import subprocess
from typing import Tuple


def check_stream(name: str, url: str, timeout: float = 10.0) -> Tuple[str, str, str, str]:
    """
    1) Detect full-black streams using ffmpeg blackdetect over 2s
    2) Probe resolution, bitrate, and FPS using ffprobe r_frame_rate

    Returns:
      status: 'UP', 'BLACK_SCREEN', or 'DOWN'
      resolution: 'WIDTH×HEIGHT' or '–'
      bitrate: raw bitrate (kbps) or '–'
      fps: numeric fps string or '–'
    """
    # 1) Black screen detection
    try:
        black_cmd = [
            'ffmpeg', '-hide_banner', '-v', 'error',
            '-t', '2', '-i', url,
            '-vf', 'blackdetect=d=2:pix_th=0.98',
            '-an', '-f', 'null', '-'
        ]
        p = subprocess.run(
            black_cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=timeout
        )
        if 'blackdetect' in (p.stderr or ''):
            return 'BLACK_SCREEN', '–', '–', '–'
    except subprocess.TimeoutExpired:
        return 'BLACK_SCREEN', '–', '–', '–'
    except Exception:
        return 'DOWN', '–', '–', '–'

    # 2) ffprobe for video stream info
    cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate,bit_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        lines = proc.stdout.strip().splitlines()
    except subprocess.TimeoutExpired:
        return 'DOWN', '–', '–', '–'
    except Exception:
        return 'DOWN', '–', '–', '–'

    # Expect at least 4 lines: width, height, r_frame_rate, bit_rate
    if len(lines) < 4:
        return 'DOWN', '–', '–', '–'

    width_s, height_s, rfr, bitrate_s = lines[:4]
    # resolution
    if width_s.isdigit() and height_s.isdigit():
        res = f"{width_s}×{height_s}"
    else:
        res = '–'
    # bitrate (as-is)
    br = bitrate_s if bitrate_s and bitrate_s.isdigit() else '–'

    # parse fps from r_frame_rate
    fps = '–'
    if rfr:
        if '/' in rfr:
            num, den = rfr.split('/', 1)
            try:
                fps_val = float(num) / float(den)
                fps = str(round(fps_val, 2))
            except:
                fps = '–'
        else:
            try:
                fps = str(round(float(rfr), 2))
            except:
                fps = '–'

    return 'UP', res, br, fps
