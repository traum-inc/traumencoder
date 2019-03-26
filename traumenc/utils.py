import logging


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
    if color:
        import colorlog
        formatter = colorlog.ColoredFormatter(
            '%(asctime)s %(log_color)s%(levelname)-8s%(reset)s '
            '%(blue)s%(name)-25.25s%(reset)s %(white)s%(message)s%(reset)s',
            datefmt=datefmt,
            reset=True,
            log_colors={ 'DEBUG': 'cyan', 'INFO': 'green', 'WARNING': 'yellow', 'ERROR': 'red', 'CRITICAL': 'red' })
    else:
        formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(name)-25.25s %(message)s', datefmt=datefmt)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return logging
