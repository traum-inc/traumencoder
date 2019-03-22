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


engine_conn = None

# the media database: all active media objects
media_items = {}

media_item_template = {
    'type': '',
    'path': '',
    'dirpath': '',
    'filename': '',
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
    if not item:
        print('new item', id)
        item = dict(id=id, **kwargs)
        media_items[id] = item
    else:
        print('old item', id)
        item.update(**kwargs)

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
        #print('SEQ_framerate:', item['framerate'])
        #print('SEQ_framerate:', sequence_framerate)
    elif item['type'] == 'video':
        filepath = item['path']
        inputspec = f'-i "{filepath}"'
    return inputspec

def calc_media_id(ob):
    data = str(ob).encode('utf8')
    m = hashlib.sha1()
    m.update(data)
    return m.hexdigest()[:8]

def save_media_items():
    print('SAVING MEDIA ITEMS')
    with open('media-items.pickle', 'wb') as f:
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

    # XXX should these be sets? might need to dedup after
    videos = []
    sequences = []

    for path in paths:
        for dirpath, _, filenames in os.walk(path, followlinks=True):
            images = []
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                _, ext = os.path.splitext(filename)
                if not ext or ext[0] != '.':
                    continue
                ext = ext[1:].lower()
                if ext in video_exts:
                    videos.append(filepath)
                elif ext in image_exts:
                    images.append(filepath)
            if images:
                seqs, _ = clique.assemble(images)
                sequences.extend(seqs)

    def add_item(type, path):
        path = os.path.abspath(path)
        id = calc_media_id(path)

        ob = media_item_template.copy()
        ob.update(
            type=type,
            path=path,
            dirpath=os.path.dirname(path),
            filename=os.path.basename(path)
            )

        if type == 'sequence':
            print('SF:', sequence_framerate)
            ob['framerate'] = sequence_framerate

        media_update(id, **ob)
        probe_item(id)
        thumbnail_item(id)

    for path in videos:
        add_item('video', path)

    # XXX framerate set on scan
    for seq in sequences:
        path = str(seq)
        add_item('sequence', path)

    #save_media_items()

    if engine_conn:
        engine_conn.send((
            'scan_complete'))

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

    fr = Fraction(st['r_frame_rate'])

    media_update(id,
        codec=st['codec_name'],
        resolution=(st['width'], st['height']),
        framerate=(fr.numerator, fr.denominator),
        pixfmt=st['pix_fmt'],
        duration=float(st['duration']),
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

    out = subprocess_exec(cmd, encoding=None)
    media_update(id, thumbnail=out)

    #f = io.BytesIO(out)
    #img = Image.open(f)
    #print('JPEG:', len(out), img.size)


def encode_item(id, outpath):
    item = media_lookup(id)
    inspec = get_ff_input_spec(item)
    codec_args = '-vcodec prores_ks -profile:v 3'

    cmd = f'''
        ffmpeg
            {inspec}
            {codec_args}
            -acodec none
            -y "${outpath}"
    '''

    # encode watcher
    re_duration = re.compile(r'Duration: (\d{2}):(\d{2}):(\d{2}).(\d{2})')
    re_progress = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}).(\d{2})')
    re_source = re.compile(r"from '(.*)':")
    re_framerate = re.compile(r'(\d{2}.\d{2}|\d{2}) fps')
    re_time = re.compile(r'(\d{2}.\d{2}|\d{2}) fps')

    def get_time_from_match(m):
        #print('GROUPS:', m.groups())
        bits = [float(x) for x in m.groups()]
        #print('BITS:', bits)
        secs = 3600.0*bits[0] + 60.0*bits[1] + 1.0*bits[2] + 0.01*bits[3]
        return secs

    duration_secs = 0.0
    progress_secs = 0.0
    progress_percent = 0
    #progress_bar = tqdm(total=100)

    line = []
    def on_stderr(ch):
        nonlocal line
        nonlocal duration_secs
        nonlocal progress_secs
        nonlocal progress_percent

        if ch in '\r\n':
            line = ''.join(line).strip()
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
                    progress_percent = round(100.0 * progress_secs / duration_secs)
                    #progress_bar.update(progress_percent)
                    print('PROGRESS:', progress_percent)

            line = []
        line.append(ch)

    args = shlex.split(cmd)
    print(' '.join(args))

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
        #print(ch, end='')

    proc.wait()
    #progress_bar.close()
    #print('-- END --')

    #f = io.BytesIO(out)
    #img = Image.open(f)
    #print('JPEG:', len(out), img.size)


def start_engine(conn):
    global engine_conn
    engine_conn = conn

    print('start_engine')
    while True:
        msg = conn.recv()
        cmd = msg['command']
        kwargs = msg['kwargs']
        print('GOT MSG:', msg)
        if cmd == 'scan_paths':
            scan_paths(**kwargs)
        elif cmd == 'join':
            break
    print('start_engine: exit')

# client
class EngineProxy(object):
    def __init__(self, proc, conn):
        self._proc = proc
        self._conn = conn

    def scan_paths(self, paths, sequence_framerate=(30,1)):
        self._send_command('scan_paths', paths=paths, sequence_framerate=sequence_framerate)

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
    print('create_engine')
    conn, conn_child = multiprocessing.Pipe()
    proc = multiprocessing.Process(target=start_engine, args=(conn_child,))
    proc.start()
    proxy = EngineProxy(proc, conn)
    return proxy
