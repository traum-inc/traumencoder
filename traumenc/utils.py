import re
import logging
from config import config


# https://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
def format_size(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def setup_logging(color=False):

    root = logging.root
    if root.hasHandlers():
        # already setup
        return

    datefmt = '%H:%M:%S'
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-25.25s %(message)s', datefmt=datefmt)

    cfg = config['log']

    if cfg.getboolean('stderr'):
        if cfg.getboolean('color'):
            import colorlog
            stream_formatter = colorlog.ColoredFormatter(
                '%(asctime)s %(log_color)s%(levelname)-8s%(reset)s '
                '%(blue)s%(name)-25.25s%(reset)s %(white)s%(message)s%(reset)s',
                datefmt=datefmt,
                reset=True,
                log_colors={ 'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'red' })
        else:
            stream_formatter = formatter

        handler = logging.StreamHandler()
        handler.setFormatter(stream_formatter)
        root.addHandler(handler)

    filename = cfg.get('file')
    if filename:
        mode = 'a' if cfg.getboolean('append') else 'w'
        handler = logging.FileHandler(filename, mode=mode)
        handler.setFormatter(formatter)
        root.addHandler(handler)

    level = getattr(logging, cfg.get('level', 'debug').upper())
    root.setLevel(level)

    return logging


def sanitize_timecode(text):
    def format(hh, mm, ss, ff):
        return f'{hh:02}:{mm:02}:{ss:02}:{ff:02}'

    m = re.match('([0-9][0-9]?)(?::([0-9]{2})(?::([0-9]{2})(?::([0-9]{2}))?)?)?', text)
    if not m:
        return ''

    d = m.groups()

    hh = int(d[0])
    if hh > 23:
        return ''

    mm = int(d[1]) if d[1] else 0
    if mm > 59:
        return ''

    ss = int(d[2]) if d[2] else 0
    if ss > 59:
        return ''

    ff = int(d[3]) if d[3] else 0

    return format(hh, mm, ss, ff)

