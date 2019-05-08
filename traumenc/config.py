from configparser import ConfigParser

config = ConfigParser()

config['ui'] = {
    'engine_poll_interval': 200,
    'details_style': 'long',
    }

config['engine'] = {
    'output_suffix': '_prores.mov',
    'ffmpeg_path': '',
    }

config['clique'] = {
    'minimum_items': 2,
    'contiguous_only': True,
    }

config['log'] = {
    'stderr': False,
    'color': False,
    'file': '',
    'append': True,
    'level': 'debug',
    }

config.read('config.ini')
