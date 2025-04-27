import requests
import ffmpeg

def check_stream(url: str, timeout: int = 10) -> tuple:
    """
    Return (status, resolution, bitrate) for a stream URL.
    Status is 'UP', 'DOWN', or 'ERROR'.
    """
    try:
        resp = requests.head(url, timeout=timeout)
        if resp.status_code != 200:
            return 'DOWN', '–', '–'
        info = ffmpeg.probe(url, select_streams='v', show_streams=True)
        stream = info['streams'][0]
        res = f"{stream['width']}×{stream['height']}"
        br = stream.get('bit_rate', '–')
        return 'UP', res, br
    except Exception:
        return 'ERROR', '–', '–'
