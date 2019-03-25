default_ffargs = {
    'codec': 'prores_ks',
    'vendor': 'ap10',
    'pix_fmt': 'yuv422p10',
    }

def add_prores_profile(id, label, **ffargs):
    ffargs = default_ffargs.copy()
    ffargs.update(ffargs)
    encoding_profiles[id] = {
        'label': label,
        'ffargs': ffargs,
        }

encoding_profiles = {}

add_prores_profile('prores_422_proxy', 'ProRes 422 Proxy', profile=0)
add_prores_profile('prores_422_lt', 'ProRes 422 LT', profile=1)
add_prores_profile('prores_422', 'ProRes 422', profile=2)
add_prores_profile('prores_422_hq', 'ProRes 422 HQ', profile=3)
add_prores_profile('prores_4444', 'ProRes 4444', profile=4, pix_fmt='yuva444p10')
add_prores_profile('prores_4444_xq', 'ProRes 4444 XQ', profile=5, pix_fmt='yuva444p10')


framerates = {}

def add_framerate(id, label, rate):
    framerates[id] = {
        'label': label,
        'rate': rate,
    }

add_framerate('fps_23_98', '23.98 fps', (24000, 1001))
add_framerate('fps_24', '24 fps', (24, 1))
add_framerate('fps_25', '25 fps', (25, 1))
add_framerate('fps_30', '30 fps', (30, 1))
add_framerate('fps_60', '60 fps', (60, 1))
