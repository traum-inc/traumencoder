from configparser import ConfigParser

config = ConfigParser()

config['ui'] = {
    'engine_poll_interval': 200,
    'details_style': 'long',
    }

config['engine'] = {
    'output_suffix': '_prores.mov',
    }

config['clique'] = {
    'minimum_items': 2,
    'contiguous_only': True,
    }

config.read('config.ini')
