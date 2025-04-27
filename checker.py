# checker.py
import requests
import subprocess

def check_stream(url: str, timeout: int = 10) -> tuple[str, str, str]:
    """
    Probe a stream URL within a total timeout (seconds).
    First does a HEAD request to verify reachability,
    then runs ffprobe with the same timeout to get video info.
    Returns (status, resolution, bitrate), where status is
    'UP' if successful, otherwise 'DOWN'.
    """
    # 1) Quick HTTP HEAD check
    try:
        resp = requests.head(url, timeout=timeout)
        if resp.status_code != 200:
            return 'DOWN', '–', '–'
    except Exception:
        return 'DOWN', '–', '–'

    # 2) ffprobe to extract width, height, bit_rate
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,bit_rate',
        '-of', 'default=noprint_wrappers=1',
        url
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        width = None
        height = None
        bitrate = None
        for line in proc.stdout.splitlines():
            if line.startswith('width='):
                width = line.split('=', 1)[1]
            elif line.startswith('height='):
                height = line.split('=', 1)[1]
            elif line.startswith('bit_rate='):
                bitrate = line.split('=', 1)[1]
        res = f"{width}×{height}" if width and height else '–'
        br  = bitrate or '–'
        return 'UP', res, br

    except subprocess.TimeoutExpired:
        # ffprobe took too long
        return 'DOWN', '–', '–'
    except Exception:
        return 'DOWN', '–', '–'
