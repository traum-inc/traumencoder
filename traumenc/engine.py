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
import platform
import subprocess
import multiprocessing
from fractions import Fraction

import logging
from utils import setup_logging
log = logging.getLogger('engine.proxy')

import config
from encodingprofiles import encoding_profiles, framerates


# connection to client
engine_conn = None

def send_to_client(*args):
    if engine_conn:
        engine_conn.send(args)

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
    #log.debug(f'media_update: cached {id} ({keys})')

    # send out
    send_to_client('media_update', id, kwargs)

def media_delete(id):
    del media_items[id]
    send_to_client('media_delete', id)


def media_lookup(id):
    return media_items.get(id)

def get_color_spec(item):
    if not item.get('colorspace'):
        # enforce bt.709
        return '''
            -color_primaries bt709
            -color_trc bt709
            -colorspace bt709
        '''

def get_ff_input_spec(item, framerate=None, color_spec=True):
    if item['type'] == 'sequence':
        seq = clique.parse(item['path'])
        seqpath = seq.format('{head}{padding}{tail}')
        start = list(seq.indexes)[0]
        if not framerate:
            framerate = item['framerate']
        sequence_framerate = ':'.join(str(x) for x in framerate)

        if color_spec == True:
            color_spec = get_color_spec(item) or ''
        elif color_spec == False:
            color_spec = ''

        inputspec = f'-framerate {sequence_framerate} {color_spec} -start_number {start} -i "{seqpath}"'
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
    # XXX this is gonna fail if filenames have multiple spaces. necessary?
    #cmd = re.sub('\s+', ' ', cmd)

    cmd = cmd.strip()
    args = shlex.split(cmd)
    log.debug(f'exec: {" ".join(args)}')
    proc = subprocess.run(args, capture_output=True, encoding=encoding)
    proc.check_returncode()
    return proc.stdout

def get_ffmpeg_bin(name):
    if platform.system() == 'Windows':
        bin_dir = os.path.abspath(os.path.join(os.curdir, 'bin'))
        bin_path = os.path.join(bin_dir, f'{name}.exe')
        # return quoted path or shlex will destroy it
        return f'"{bin_path}"'
    else:
        # assume in user's path
        return name

scan_paths_queue = []
scan_cancelled = False

def cancel_scan():
    global scan_cancelled
    scan_cancelled = True

def scan_paths(paths=[], sequence_framerate=(30,1)):
    scan_in_progress = len(scan_paths_queue) > 0
    scan_paths_queue.extend(paths)
    if scan_in_progress:
        # called from a poll_client()
        return

    # reset the cancel event
    global scan_cancelled
    scan_cancelled = False

    video_exts = {'avi', 'mov', 'mp4', 'm4v', 'mkv', 'webm'}
    image_exts = {'png', 'tif', 'tiff', 'jpg', 'jpeg', 'dpx', 'exr'}

    videos = []
    images = []
    sequences = []

    last_update_time = time.time()
    update_interval = 0.3
    scan_totals = [0, 0]

    def scan_update(dirs, files):
        scan_totals[0] += dirs
        scan_totals[1] += files

        nonlocal last_update_time
        now = time.time()
        if now - last_update_time < update_interval:
            return

        send_to_client('scan_update', scan_totals[0], scan_totals[1])
        last_update_time = now

        add_videos_and_sequences()

        # poll for cancel etc...
        poll_client()

        if scan_cancelled:
            # remove all queued paths
            scan_paths_queue.clear()

    def add_file(filepath):
        scan_update(0, 1)

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
            log.debug(f'scan dir: {dirpath}')
            scan_update(1, 0)
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                add_file(filepath)

                # check for cancellation
                if scan_cancelled:
                    return

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

        #log.info(f'SCAN_CANCELLED={scan_cancelled}')
        if not scan_cancelled:
            if probe_item(id) and thumbnail_item(id):
                media_update(id, state='ready')
            else:
                # broken... delete it
                media_delete(id)
            poll_client()

    def add_videos_and_sequences():
        nonlocal videos
        nonlocal sequences

        for path in videos:
            if matches_default_outpath(path):
                log.info(f'scan ignoring: {path}')
                continue
            add_item('video', path)
        videos = []

        # XXX framerate set on scan
        for seq in sequences:
            path = str(seq)
            add_item('sequence', path)
        sequences = []

    def assemble_sequences():
        if images:
            start_time = time.time()
            log.debug(f'assembling sequences from {len(images)} images...')
            seqs, _ = clique.assemble(images, minimum_items=config.CLIQUE_MINIMUM_ITEMS)
            if config.CLIQUE_CONTIGUOUS_ONLY:
                seqs = [s for s in seqs if s.is_contiguous()]
            sequences.extend(seqs)
            elapsed = time.time() - start_time
            log.debug(f'assembling sequences done ({elapsed:.2f} seconds)')

    # scan paths
    while scan_paths_queue:
        path = scan_paths_queue.pop(0)
        if os.path.isfile(path):
            add_file(path)
        elif os.path.isdir(path):
            add_dir(path)
            assemble_sequences()

    # add remaining videos and sequences
    add_videos_and_sequences()

    # clean up and cancellation mess
    if scan_cancelled:
        send_to_client('scan_cancelled')
        scan_cancelled = False

        # find and remove unprocessed media items
        remove_ids = []
        for id, item in media_items.items():
            if item['state'] == 'new':
                remove_ids.append(id)

        for id in remove_ids:
            log.info(f'REMOVING NEW ITEM: {id}')
            media_delete(id)
    else:
        send_to_client('scan_complete')

def probe_item(id):
    item = media_lookup(id)
    program = get_ffmpeg_bin('ffprobe')
    inspec = get_ff_input_spec(item, color_spec=False)

    try:
        out = subprocess_exec(f'''
            {program}
                -v 0
                -show_streams
                -print_format json
                {inspec}
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
            colorspace=st.get('color_space'),
            )

    except subprocess.CalledProcessError as e:
        log.warn(f'ffprobe failed: {inspec}')
        log.warn(e.cmd)
        log.warn(e.output)
        return False

    # filesize
    if item['type'] == 'video':
        filesize = os.path.getsize(item['path'])
    elif item['type'] == 'sequence':
        seq = clique.parse(item['path'])
        filesize = 0
        for filepath in seq:
            filesize += os.path.getsize(filepath)
    media_update(id, filesize=filesize)
    return True


def thumbnail_item(id, size=(-1, 256)):
    item = media_lookup(id)
    inspec = get_ff_input_spec(item)
    outpath = '-'   # stdout
    program = get_ffmpeg_bin('ffmpeg')

    cmd = f'''
        {program}
            -v 0
            -ss 0
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
        return True

    except subprocess.CalledProcessError as e:
        log.warn('thumbnail failed:', inspec)
        log.warn(e.cmd)
        log.warn(e.output)
        return False


def remove_items(ids):
    # XXX some things that should happen here..
    # is the item in the encode queue?

    for id in ids:
        item = media_lookup(id)
        state = item['state']
        if state in ('new', 'encoding'):
            # ignore
            continue

        media_delete(id)


def preview_item(id, framerate=None):
    item = media_lookup(id)
    if not item:
        return

    if item['state'] == 'done' and 'outpath' in item:
        outpath = item['outpath']
        inspec = f'-i "{outpath}"'
    else:
        if framerate:
            framerate = framerates[framerate]['rate']
        inspec = get_ff_input_spec(item, framerate)

    program = get_ffmpeg_bin('ffplay')
    cmd = f'{program} {inspec}'
    args = shlex.split(cmd)

    # spawn, don't wait
    log.info(f'spawning: {cmd}')
    proc = subprocess.Popen(args)
    log.info(f'pid={proc.pid}')


encode_cancelled = False

def cancel_encode():
    log.debug('cancel_encode')
    global encode_cancelled
    encode_cancelled = True

def encode_items(ids, profile, framerate):
    global encode_cancelled
    if encode_cancelled:
        # don't add more to the queue on re-entry
        return

    encode_queue = []

    if not ids:
        # no selection provided: add anything that's ready
        ids = [id for id in media_items.keys() if media_lookup(id)['state'] == 'ready']

    for id in ids:
        media_update(id, state='queued')
        encode_queue.append((id, profile, framerate))

    while encode_queue:
        if encode_cancelled:
            break

        id, profile, framerate = encode_queue.pop(0)
        encode_item(id, profile, framerate)

    if encode_cancelled:
        # queue -> ready
        for id, profile, framerate in encode_queue:
            media_update(id, state='ready')

        send_to_client('encode_cancelled')
        encode_cancelled = False    # reset
    else:
        send_to_client('encode_complete')


def encode_item(id, profile, framerate=None, outpath=None):
    item = media_lookup(id)
    if not item:
        log.warn(f'encode_item: can\'t find item {id}')
        return

    if outpath is None:
        outpath = get_item_default_outpath(item)

    if framerate:
        framerate = framerates[framerate]['rate']

    inspec = get_ff_input_spec(item, framerate)

    # TODO force input framerate??

    ffargs = encoding_profiles[profile]['ffargs']
    codec_args = f'''
        -codec:v {ffargs['codec']}
        -profile:v {ffargs['profile']}
        -vendor {ffargs['vendor']}
        -pix_fmt {ffargs['pix_fmt']}
    '''

    #audio_args = '-an'
    audio_args = '-codec:a copy'

    program = get_ffmpeg_bin('ffmpeg')

    cmd = f'''
        {program}
            {inspec}
            {codec_args}
            {audio_args}
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

                    # poll client here too...
                    poll_client()

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

        if encode_cancelled:
            break

        ch = str(ch, encoding='utf8')
        on_stderr(ch)
        dt = time.time() - t0

    if encode_cancelled:
        log.warn(f'encode cancelled: killing proc {proc.pid}')
        proc.kill()

    rc = proc.wait()
    if rc == 0:
        media_update(id, progress=1.0, state='done', outpath=outpath)
    elif encode_cancelled:
        media_update(id, progress=0.0, state='ready')
    else:
        log.error(f'bad returncode: {rc}')
        log.error('\n'.join(output)) # last line
        media_update(id, progress=0.0, state='error')

client_wants_to_join = False

def dispatch_client_request(cmd, args):
    global join_requested

    if cmd == 'scan_paths':
        scan_paths(**args)
    elif cmd == 'encode_items':
        encode_items(**args)
    elif cmd == 'cancel_encode':
        cancel_encode()
    elif cmd == 'remove_items':
        remove_items(**args)
    elif cmd == 'cancel_scan':
        cancel_scan()
    elif cmd == 'preview_item':
        preview_item(**args)
    elif cmd == 'join':
        cancel_scan()
        cancel_encode()

        global client_wants_to_join
        client_wants_to_join = True

def receive_and_dispatch_next_client_request(block=True):
    if not (block or engine_conn.poll()):
        return False

    msg = engine_conn.recv()
    cmd = msg['command']
    args = msg['kwargs']

    def format_kwargs(kwargs):
        return ' '.join(
            f'{k}={v}' for k,v in kwargs.items())

    log.debug(f'received: {cmd} {format_kwargs(args)}')
    dispatch_client_request(cmd, args)
    return True

def poll_client():
    while receive_and_dispatch_next_client_request(False):
        pass

def start_engine(conn):
    global engine_conn
    engine_conn = conn

    global log
    log = logging.getLogger('engine.child')
    setup_logging(color=True)

    log.debug('start_engine')
    while not client_wants_to_join:
        receive_and_dispatch_next_client_request()

    log.debug('start_engine: exit')

# client
class EngineProxy(object):
    def __init__(self, proc, conn):
        self._proc = proc
        self._conn = conn

    def scan_paths(self, paths, sequence_framerate=(30,1)):
        self._send_command('scan_paths', paths=paths, sequence_framerate=sequence_framerate)

    def cancel_scan(self):
        self._send_command('cancel_scan')

    def encode_items(self, ids, profile='prores_422', framerate='fps_30'):
        self._send_command('encode_items', ids=ids, profile=profile, framerate=framerate)

    def cancel_encode(self):
        self._send_command('cancel_encode')

    def remove_items(self, ids):
        self._send_command('remove_items', ids=ids)

    def preview_item(self, id, framerate):
        self._send_command('preview_item', id=id, framerate=framerate)

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
