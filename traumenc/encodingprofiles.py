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
