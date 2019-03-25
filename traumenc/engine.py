import os
import re
import io
import sys
import time
import json
import shlex
import clique
import pickle
import hashlib
import subprocess
import multiprocessing
from fractions import Fraction

import logging
log = logging.getLogger('engine.proxy')

import config


# connection to client
engine_conn = None

# the media database: all active media objects
media_items = {}

media_item_template = {
    'type': '',
    'path': '',
    'dirpath': '',
    'filename': '',
    'displayname': '',
    'duration': 0.0,
    'framerate': (30, 1),
    'resolution': (0, 0),
    'codec': '',
    'pixfmt': '',
    'thumbnail': None,
    'progress': 0.0,
}

def media_update(id, **kwargs):
    item = media_lookup(id)
    cached = False

    if not item:
        item = dict(id=id, **kwargs)
        media_items[id] = item
    else:
        cached = True
        item.update(**kwargs)

    keys = ",".join(kwargs.keys())
    log.debug(f'media_update: cached {id} ({keys})')

    # send out
    if engine_conn:
        engine_conn.send((
            'media_update', id, kwargs))

def media_delete(id):
    del media_items[id]

    if engine_conn:
        engine_conn.send((
            'media_delete', id))


def media_lookup(id):
    return media_items.get(id)

def get_ff_input_spec(item):
    if item['type'] == 'sequence':
        seq = clique.parse(item['path'])
        seqpath = seq.format('{head}{padding}{tail}')
        start = list(seq.indexes)[0]
        sequence_framerate = ':'.join(str(x) for x in item['framerate'])
        inputspec = f'-i "{seqpath}" -framerate {sequence_framerate} -start_number {start}'
    elif item['type'] == 'video':
        filepath = item['path']
        inputspec = f'-i "{filepath}"'
    return inputspec

def calc_media_id(ob):
    data = str(ob).encode('utf8')
    m = hashlib.sha1()
    m.update(data)
    return m.hexdigest()[:8]

def get_sequence_displayname(path):
    seq = clique.parse(path)
    num = '#' * seq.padding
    ranges = seq.format('{ranges}')
    displaypath = f'{seq.head}{num}{seq.tail} ({ranges})'
    displayname = os.path.basename(displaypath)
    return displayname

def get_item_default_outpath(item):
    path = item['path']
    if item['type'] == 'video':
        basepath = os.path.splitext(path)[0]
        outpath = f'{basepath}_prores.mov'
    elif item['type'] == 'sequence':
        seq = clique.parse(path)
        num = '0' * seq.padding
        outpath = f'{seq.head}{num}{seq.tail}'
        basepath = os.path.splitext(outpath)[0]
        outpath = f'{basepath}{config.DEFAULT_OUTPUT_SUFFIX}'
    return outpath

def matches_default_outpath(path):
    return path.endswith(config.DEFAULT_OUTPUT_SUFFIX)

def save_media_items(filepath=None):
    if not filepath:
        filepath = 'media-items.pickle'
    log.info(f'saving media items to {filepath}')
    with open(filepath, 'wb') as f:
        pickle.dump(media_items, f, pickle.HIGHEST_PROTOCOL)

def subprocess_exec(cmd, encoding='utf8'):
    cmd = re.sub('\s+', ' ', cmd)
    cmd = cmd.strip()
    args = shlex.split(cmd)
    proc = subprocess.run(args, capture_output=True, encoding=encoding)
    proc.check_returncode()
    return proc.stdout


def scan_paths(paths=[], sequence_framerate=(30,1)):
    video_exts = {'avi', 'mov', 'mp4', 'm4v', 'mkv', 'webm'}
    image_exts = {'png', 'tif', 'tiff', 'jpg', 'jpeg', 'dpx', 'exr'}

    videos = []
    images = []

    def add_file(filepath):
        _, ext = os.path.splitext(filepath)
        if not ext or ext[0] != '.':
            return

        ext = ext[1:].lower()
        if ext in video_exts:
            videos.append(filepath)
        elif ext in image_exts:
            images.append(filepath)

    def add_dir(dirpath):
        for dirpath, _, filenames in os.walk(path, followlinks=True):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                add_file(filepath)

    # scan paths
    for path in paths:
        if os.path.isfile(path):
            add_file(path)
        elif os.path.isdir(path):
            add_dir(path)

    # assemble image sequences
    sequences, _ = clique.assemble(images)

    def add_item(type, path):
        path = os.path.abspath(path)
        id = calc_media_id(path)

        ob = media_item_template.copy()
        ob.update(
            type=type,
            path=path,
            dirpath=os.path.dirname(path),
            filename=os.path.basename(path),
            state='new',
            )

        if type == 'sequence':
            ob['framerate'] = sequence_framerate
            ob['displayname'] = get_sequence_displayname(path)
        else:
            ob['displayname'] = ob['filename']

        media_update(id, **ob)
        probe_item(id)
        thumbnail_item(id)
        media_update(id, state='ready')

    for path in videos:
        if matches_default_outpath(path):
            log.info(f'scan ignoring: {path}')
            continue

        add_item('video', path)

    # XXX framerate set on scan
    for seq in sequences:
        path = str(seq)
        add_item('sequence', path)

    #save_media_items()
    if engine_conn:
        engine_conn.send((
            'scan_complete',))

def probe_item(id):
    item = media_lookup(id)
    out = subprocess_exec(f'''
        ffprobe
            -loglevel panic
            -show_streams
            {get_ff_input_spec(item)}
            -print_format json
            -show_streams
        ''')
    ob = json.loads(out)
    st = ob['streams'][0]

    try:
        fr = Fraction(st['r_frame_rate'])
        framerate = (fr.numerator, fr.denominator)
    except ZeroDivisionError:
        framerate = (0, 0)

    resolution = (
        st.get('width', 0),
        st.get('height', 0))

    pixfmt = st.get('pix_fmt', 'unknown')
    duration = st.get('duration', 0.0)

    media_update(id,
        codec=st['codec_name'],
        resolution=resolution,
        framerate=framerate,
        pixfmt=pixfmt,
        duration=float(duration),
        )

    # filesize
    if item['type'] == 'video':
        filesize = os.path.getsize(item['path'])
    elif item['type'] == 'sequence':
        seq = clique.parse(item['path'])
        filesize = 0
        for filepath in seq:
            filesize += os.path.getsize(filepath)
    media_update(id, filesize=filesize)


def thumbnail_item(id, size=(-1, 256)):
    item = media_lookup(id)
    inspec = get_ff_input_spec(item)
    outpath = '-'   # stdout

    cmd = f'''
        ffmpeg
            -v 0
            -ss 1
            -noaccurate_seek
            {inspec}
            -frames 1
            -vf scale={size[0]}:{size[1]}
            -f singlejpeg
            -y
            {outpath}
    '''

    try:
        out = subprocess_exec(cmd, encoding=None)
        media_update(id, thumbnail=out)

    except subprocess.CalledProcessError as e:
        log.warn('thumbnail failed:', inspec)
        #print(e.cmd)
        #print(e.output)

    #f = io.BytesIO(out)
    #img = Image.open(f)
    #print('JPEG:', len(out), img.size)

def encode_items(ids):
    encode_queue = []

    for id in ids:
        media_update(id, state='queued')
        encode_queue.append(id)

    while encode_queue:
        id = encode_queue.pop(0)
        encode_item(id)


def encode_item(id, outpath=None):
    item = media_lookup(id)
    if not item:
        log.warn(f'encode_item: can\'t find item {id}')
        return

    if outpath is None:
        outpath = get_item_default_outpath(item)

    inspec = get_ff_input_spec(item)
    codec_args = '-vcodec prores_ks -profile:v 3'

    cmd = f'''
        ffmpeg
            {inspec}
            {codec_args}
            -an
            -y "{outpath}"
    '''

    # encode watcher
    re_duration = re.compile(r'Duration: (\d{2}):(\d{2}):(\d{2}).(\d{2})')
    re_progress = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}).(\d{2})')
    re_source = re.compile(r"from '(.*)':")
    re_framerate = re.compile(r'(\d{2}.\d{2}|\d{2}) fps')
    re_time = re.compile(r'(\d{2}.\d{2}|\d{2}) fps')

    def get_time_from_match(m):
        bits = [float(x) for x in m.groups()]
        #print('BITS:', bits)
        secs = 3600.0*bits[0] + 60.0*bits[1] + 1.0*bits[2] + 0.01*bits[3]
        return secs

    duration_secs = 0.0
    progress_secs = 0.0
    progress_percent = 0
    #progress_bar = tqdm(total=100)

    line = []
    output = []
    def on_stderr(ch):
        nonlocal line
        nonlocal duration_secs
        nonlocal progress_secs
        nonlocal progress_percent

        if ch in '\r\n':
            line = ''.join(line).strip()
            output.append(line)
            #print(line)

            m = re_duration.search(line)
            if m:
                #print('duration:', m.group(0), get_time_from_match(m))
                duration_secs = get_time_from_match(m)

            m = re_source.search(line)
            if m:
                #print('source:', m.group(1))
                pass

            m = re_framerate.search(line)
            if m:
                #print('framerate:', float(m.group(1)))
                pass

            m = re_progress.search(line)
            if m:
                #print('progress:', m.group(0), get_time_from_match(m))
                progress_secs = get_time_from_match(m)
                if duration_secs > 0.0:
                    progress = progress_secs / duration_secs
                    progress_percent = round(100.0 * progress)
                    log.debug(f'encode_item: {id} {progress_percent}%')
                    media_update(id, progress=progress)

            line = []
        line.append(ch)

    args = shlex.split(cmd)
    log.info(f'encode_item: {id} {" ".join(args)}')

    # start the encoding process
    media_update(id, state='encoding')
    proc = subprocess.Popen(args, bufsize=0, stderr=subprocess.PIPE)
    t0 = time.time()
    while True:
        ch = proc.stderr.read(1)
        if not ch:
            break
        ch = str(ch, encoding='utf8')
        on_stderr(ch)
        dt = time.time() - t0
        """
        if dt > 2.0:
            print('-- KILLING --')
            proc.kill()
            break
        """

    rc = proc.wait()
    if rc != 0:
        log.error(f'bad returncode: {rc}')
        log.error('\n'.join(output)) # last line

    # FIXME catch errors
    media_update(id, progress=1.0, state='done')

def start_engine(conn):
    global engine_conn
    engine_conn = conn

    global log
    log = logging.getLogger('engine.child')

    def format_kwargs(kwargs):
        return ' '.join(
            f'{k}={v}' for k,v in kwargs.items())

    log.debug('start_engine')
    while True:
        msg = conn.recv()
        cmd = msg['command']
        kwargs = msg['kwargs']
        log.debug(f'received: {cmd} {format_kwargs(kwargs)}')
        if cmd == 'scan_paths':
            scan_paths(**kwargs)
        elif cmd == 'encode_items':
            encode_items(**kwargs)
        elif cmd == 'join':
            break
    log.debug('start_engine: exit')

# client
class EngineProxy(object):
    def __init__(self, proc, conn):
        self._proc = proc
        self._conn = conn

    def scan_paths(self, paths, sequence_framerate=(30,1)):
        self._send_command('scan_paths', paths=paths, sequence_framerate=sequence_framerate)

    def encode_items(self, ids):
        self._send_command('encode_items', ids=ids)

    def join(self):
        self._send_command('join')
        self._proc.join()

    def poll(self):
        if not self._conn.poll():
            return None
        msg = self._conn.recv()
        return msg

    def _send_command(self, name, **kwargs):
        self._conn.send({ 'command': name, 'kwargs': kwargs })

def create_engine():
    log.debug('create_engine')
    conn, conn_child = multiprocessing.Pipe()
    proc = multiprocessing.Process(target=start_engine, args=(conn_child,))
    proc.start()
    proxy = EngineProxy(proc, conn)
    return proxy
