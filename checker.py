import requests
import ffmpeg

def check_stream(url: str, timeout: int = 10) -> tuple[str, str, str]:
    """
    Return (status, resolution, bitrate) for a stream URL.
    Possible statuses: 'UP', 'BLACK_SCREEN', 'DOWN', 'ERROR'.
    """
    try:
        resp = requests.head(url, timeout=timeout)
        if resp.status_code != 200:
            return 'DOWN', '–', '–'
        try:
            info = ffmpeg.probe(url, select_streams='v', show_streams=True)
            stream = info['streams'][0]
            res = f"{stream['width']}×{stream['height']}"
            br = stream.get('bit_rate', '–')
            return 'UP', res, br
        except Exception:
            return 'BLACK_SCREEN', '–', '–'
    except Exception:
        return 'ERROR', '–', '–'