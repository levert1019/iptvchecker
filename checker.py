import subprocess
from typing import Tuple


def check_stream(name: str, url: str, timeout: float = 10.0) -> Tuple[str, str, str, str]:
    """
    Probe the given IPTV URL:
      1) Use ffmpeg's blackdetect filter over first 2 seconds to detect a full black screen.
      2) If not black, use ffprobe to get width×height, bitrate, and avg_frame_rate (FPS).

    Returns:
      status: 'UP', 'DOWN', or 'BLACK_SCREEN'
      resolution: 'WIDTH×HEIGHT' or '–'
      bitrate: raw bitrate string or '–'
      fps: numeric FPS string or '–'
    """
    # 1) Black screen detection via ffmpeg over 2 seconds
    try:
        black_cmd = [
            'ffmpeg', '-hide_banner', '-v', 'error',
            '-t', '2', '-i', url,
            '-vf', 'blackdetect=d=2:pix_th=0.98',
            '-an', '-f', 'null', '-'
        ]
        proc_black = subprocess.run(
            black_cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        stderr = proc_black.stderr or ''
        # If blackdetect finds a black segment spanning full 2s, treat as BLACK_SCREEN
        if 'blackdetect' in stderr:
            # check if it covers from 0 to ~2s
            # simplest: any blackdetect message => black screen
            return 'BLACK_SCREEN', '–', '–', '–'
    except subprocess.TimeoutExpired:
        # assume black screen on ffmpeg timeout
        return 'BLACK_SCREEN', '–', '–', '–'
    except Exception:
        # on ffmpeg failure, fall through to DOWN
        return 'DOWN', '–', '–', '–'

    # 2) Stream info via ffprobe
    probe_cmd = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,bit_rate,avg_frame_rate',
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
        lines = proc.stdout.strip().splitlines()
    except subprocess.TimeoutExpired:
        return 'DOWN', '–', '–', '–'
    except Exception:
        return 'DOWN', '–', '–', '–'

    # Expect at least four lines
    if len(lines) < 4:
        return 'DOWN', '–', '–', '–'

    width, height, bitrate, avg_frame_rate = lines[:4]

    # Build resolution
    res = f"{width}×{height}" if width and height and width.isdigit() and height.isdigit() else '–'
    # Clean bitrate
    br = bitrate if bitrate and bitrate.isdigit() else '–'

    # Parse FPS from avg_frame_rate, which may be '25/1' or '29.97' or similar
    fps = '–'
    if avg_frame_rate:
        if '/' in avg_frame_rate:
            num, den = avg_frame_rate.split('/', 1)
            try:
                fps_val = float(num) / float(den)
                fps = str(round(fps_val, 2))
            except Exception:
                fps = avg_frame_rate
        else:
            fps = avg_frame_rate

    return 'UP', res, br, fps
