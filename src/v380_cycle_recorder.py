#!/usr/bin/env python3
"""V380 Pro (4G) occasional clip archiver for OpenWrt.

Requires the already working local files relay_capture.py, v380_hevc_decode.py,
and hevc_to_mp4.py in the same directory. Captures one ~25-second HEVC MP4 (with audio when supported) per invocation,
with fail-safe rotation on /mnt/usb2.

Schedule with cron every 15 minutes. Credential in root-only /etc/v380_camera_password.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen

BASE = Path('/mnt/usb2/V380')
MOUNT = Path('/mnt/usb2')
WORK = BASE / 'work'
ARCHIVE = BASE / 'archive'
SOURCE = BASE / 'relay_capture.py'
CONVERTER = BASE / 'hevc_to_mp4.py'
PASSWORD_FILE = Path('/etc/v380_camera_password')
LOG_FILE = BASE / 'cycle.log'
CONFIG_FILE = Path("/etc/v380_recorder.json")
CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
DEVICE_ID = int(CONFIG["device_id"])
FPS = int(CONFIG.get("fps", 12))
MAX_ARCHIVE_BYTES = int(CONFIG.get("max_archive_gib", 20)) * 1024**3
MIN_FREE_BYTES = int(CONFIG.get("min_free_gib", 3)) * 1024**3
MAX_LOG_BYTES = 512 * 1024
# Explicit allowlist: don't send camera authentication to an arbitrary relay
# delivered by an unauthenticated HTTP response.
KNOWN_RELAYS = tuple(CONFIG.get("relay_allowlist", []))
def log(message: str) -> None:
    line = f'[{dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")}] {message}'
    print(line, flush=True)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
            LOG_FILE.replace(LOG_FILE.with_suffix('.log.1'))
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def relay_candidates() -> list[str]:
    """Prefer dispatcher's current ordering, limited to previously checked relays."""
    stamp = int(time.time())
    body = {
        'dev_id': DEVICE_ID,
        'platform': 10001,
        'timestamp': stamp,
    }
    to_sign = f'dev_id={DEVICE_ID}&platform=10001&timestamp={stamp}hsdata2022'
    body['sign'] = hashlib.sha1(to_sign.encode('ascii')).hexdigest()
    url = 'http://dispa1.av380.net:8001/api/v1/get_stream_server'
    try:
        req = Request(url, data=json.dumps(body).encode('utf-8'),
                      headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=8) as response:
            answer = json.load(response)
        if answer.get('code') != 2000:
            log(f'Dispatcher returned code {answer.get("code")!r}; using saved relays')
            return list(KNOWN_RELAYS)
        rows = answer.get('data') or []
        if isinstance(rows, dict):
            rows = [rows]
        ips = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            ip = item.get('ip', '')
            try:
                if ip in KNOWN_RELAYS and ipaddress.ip_address(ip).is_global and ip not in ips:
                    ips.append(ip)
            except ValueError:
                pass
        if not ips:
            log('Dispatcher returned no allowed relays; using saved addresses')
            return list(KNOWN_RELAYS)
        return ips
    except Exception as e:
        log(f'Dispatcher unavailable ({type(e).__name__}: {e}); using saved relays')
        return list(KNOWN_RELAYS)


def cleanup_temp() -> None:
    """Only remove our intermediate capture files from the dedicated work dir."""
    for p in list(WORK.glob('capture_*')) + [WORK / 'new_video.mp4', WORK / 'new_av.mp4']:
        if p.is_file() and p.suffix in ('.bin', '.h265', '.mp4', '.alaw', '.aac'):
            p.unlink(missing_ok=True)


def prune_archive() -> None:
    """Keep archive within configured limits and reserve space on the flash drive."""
    files = []
    archive_bytes = 0
    for p in ARCHIVE.glob('*.mp4'):
        if p.is_file():
            try:
                st = p.stat()
                files.append((st.st_mtime, p, st.st_size))
                archive_bytes += st.st_size
            except OSError:
                continue
    files.sort(key=lambda x: x[0])
    free_bytes = shutil.disk_usage(MOUNT).free
    for _, p, n in files:
        if archive_bytes <= MAX_ARCHIVE_BYTES and free_bytes >= MIN_FREE_BYTES:
            break
        try:
            p.unlink()
            log(f'Removed oldest video: {p.name}')
            archive_bytes -= n
            free_bytes += n
        except OSError as e:
            log(f'Cannot remove {p.name}: {e}')
    if archive_bytes > MAX_ARCHIVE_BYTES or free_bytes < MIN_FREE_BYTES:
        log('Not enough free space; archive exhausted or non-archive files fill the disk')


# Run the existing, user-verified capture code in a separate bounded process.
# We only substitute the IP address and destination in memory, so the working
# source files are not modified. getpass() reads the root-only credentials file.
CAPTURE_PROCESS_CODE = r'''
import getpass
from pathlib import Path
import sys

base = Path('/mnt/usb2/V380')
source = base / 'relay_capture.py'
password_file = Path('/etc/v380_camera_password')
password = password_file.read_text(encoding='utf-8').rstrip('\r\n')
if not password:
    raise SystemExit('The password file is empty')
getpass.getpass = lambda prompt='': password
script = source.read_text(encoding='utf-8')
old_ip = 'RELAY_IP = "127.0.0.1"'
old_dir = '"/mnt/usb2/V380/recordings/"'
if old_ip not in script or old_dir not in script:
    raise SystemExit('Existing relay_capture.py is not in the expected format')
script = script.replace(old_ip, 'RELAY_IP = ' + repr(sys.argv[1]), 1)
script = script.replace(old_dir, '"/mnt/usb2/V380/work/"', 1)
# Insert audio extraction at the point when the auth ticket is still in memory.
marker = 'decode_capture(filename, ticket)'
if marker not in script:
    raise SystemExit('Cannot locate decode_capture() in relay_capture.py')
script = script.replace(marker, marker + '\n                            decode_audio(filename, ticket)', 1)

import struct
from Crypto.Cipher import AES

def decode_audio(raw_filename, auth_ticket):
    # V380 device version 32: decrypt every complete 16-byte audio block.
    # Unlike video, audio does not use the 64-decrypted / 16-plain pattern.
    key = struct.pack('<IQI', auth_ticket, 0x618123462C14795C, 0x82800DF0)
    cipher = AES.new(key, AES.MODE_ECB)
    raw_path = Path(raw_filename)
    data = raw_path.read_bytes()
    position = 0
    buffer = bytearray()
    expected = 0
    next_index = 0
    chunks = []
    malformed = 0

    while position + 12 <= len(data):
        if data[position] != 0x7f:
            position += 1
            continue
        typ = data[position + 1]
        count, index, size = struct.unpack_from('<HHH', data, position + 3)
        if not (1 <= count <= 4096 and index < count and 1 <= size <= 20000):
            position += 1
            continue
        end = position + 12 + size
        if end > len(data):
            break
        part = data[position + 12:end]
        position = end
        if typ != 0x1a:
            continue
        if index == 0:
            buffer.clear()
            expected = count
            next_index = 0
        if not expected or count != expected or index != next_index:
            malformed += 1
            buffer.clear()
            expected = 0
            continue
        buffer.extend(part)
        next_index += 1
        if next_index != count:
            continue
        full = bytes(buffer)
        buffer.clear()
        expected = 0
        if len(full) <= 16:
            continue
        payload = bytearray(full[16:])
        aligned = (len(payload) // 16) * 16
        if aligned:
            payload[:aligned] = cipher.decrypt(bytes(payload[:aligned]))
        chunks.append(bytes(payload))

    if not chunks:
        print('[AUDIO] No complete audio frames')
        return
    adts = sum(len(c) >= 7 and c[0] == 0xff and (c[1] & 0xf0) == 0xf0
               for c in chunks)
    # ADTS sync is present in nearly every frame if camera uses AAC-ADTS.
    is_aac = adts >= max(2, len(chunks) * 9 // 10)
    fmt = '.aac' if is_aac else '.alaw'
    output = raw_path.with_suffix(fmt)
    output.write_bytes(b''.join(chunks))
    print(f'[AUDIO] Frames: {len(chunks)}; size: {output.stat().st_size}; '
          f'codec: {"AAC-ADTS" if is_aac else "G.711 A-law (assumed)"}; '
          f'fragment errors: {malformed}')

sys.path.insert(0, str(base))
sys.argv = [str(source)]
exec(compile(script, str(source), 'exec'), {
    '__name__': '__main__', '__file__': str(source), 'decode_audio': decode_audio
})
'''


def capture(relay: str) -> Path | None:
    cleanup_temp()
    try:
        result = subprocess.run(
            [sys.executable, '-c', CAPTURE_PROCESS_CODE, relay],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=90, cwd=str(BASE),
            env={**os.environ, "V380_DEVICE_ID": str(DEVICE_ID)},
        )
    except subprocess.TimeoutExpired:
        log(f'Capture via {relay}: 90-second timeout')
        return None
    except OSError as e:
        log(f'Could not launch capture: {e}')
        return None

    # Do not log the complete output: future versions of the source might print
    # a secret. Only show short, explicitly recognized status messages.
    for line in result.stdout.splitlines():
        if line.startswith(('[!] ', '[STREAM] Получено байт:', '[DECODE] Video frames:',
                            '[DECODE] Fragment errors:', '[DECODE] Rejected frames:', '[AUDIO]')):
            log(line[:250])

    hevc = sorted(WORK.glob('capture_*.h265'), key=lambda p: p.stat().st_mtime)
    if not hevc or hevc[-1].stat().st_size < 4096:
        log(f'No usable video from {relay} (return code {result.returncode})')
        return None
    return hevc[-1]


def remux_video(hevc: Path, destination: Path) -> bool:
    temp_mp4 = WORK / 'new_video.mp4'
    try:
        result = subprocess.run(
            [sys.executable, str(CONVERTER), str(hevc),
             '--fps', str(FPS), '-o', str(temp_mp4)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f'MP4 conversion failed: {e}')
        return False
    if result.returncode != 0 or not temp_mp4.is_file() or temp_mp4.stat().st_size < 8192:
        log(f'Invalid MP4: {result.stdout.strip()[-250:]}')
        return False
    # Simple MP4 signature validation; complete video was verified on iPhone.
    with temp_mp4.open('rb') as f:
        first = f.read(12)
    if len(first) < 12 or first[4:8] != b'ftyp':
        log('MP4 missing expected ftyp header')
        return False
    # The OpenWrt FFmpeg lacks an HEVC decoder, but stream copy of an MP4
    # video track still works on many builds. Only audio is transcoded to AAC.
    audio = hevc.with_suffix('.aac')
    audio_type = 'aac'
    if not audio.is_file() or audio.stat().st_size < 1024:
        audio = hevc.with_suffix('.alaw')
        audio_type = 'alaw'
    if audio.is_file() and audio.stat().st_size >= 1024:
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            av_mp4 = WORK / 'new_av.mp4'
            audio_input = (['-f', 'aac'] if audio_type == 'aac'
                           else ['-f', 'alaw', '-ar', '8000', '-ac', '1'])
            cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error',
                   '-nostdin', '-y', '-i', str(temp_mp4)] + audio_input + [
                       '-i', str(audio),
                       '-map', '0:v:0', '-map', '1:a:0',
                       '-c:v', 'copy', '-c:a', 'aac',
                       '-b:a', '40k', '-ac:a', '1',
                       '-movflags', '+faststart', str(av_mp4)]
            # An AAC stream's natural rate should be preserved. For G.711 A-law
            # it is explicitly supplied as 8000 Hz above.
            try:
                mux = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     timeout=45)
                if mux.returncode == 0 and av_mp4.is_file() and av_mp4.stat().st_size > 8192:
                    with av_mp4.open('rb') as fd:
                        ok = fd.read(12)[4:8] == b'ftyp'
                    if ok:
                        os.replace(av_mp4, destination)
                        log(f'Saved with audio {destination.name} '
                            f'({destination.stat().st_size} bytes, audio={audio_type})')
                        return True
                log(f'Audio MP4 mux failed; keeping video-only MP4. '
                    f'{mux.stdout.strip()[-280:]}')
            except (OSError, subprocess.TimeoutExpired) as exc:
                log(f'Audio MP4 mux error; video-only fallback: {exc}')
        else:
            log('FFmpeg not found, saving video-only MP4')
    else:
        log('No audio frames in capture, saving video-only MP4')
    os.replace(temp_mp4, destination)  # same ext4 filesystem, atomic rename
    log(f'Saved video-only {destination.name} ({destination.stat().st_size} bytes)')
    return True


def main() -> int:
    # CRITICAL: never write files to internal flash if /mnt/usb2 isn't mounted.
    if not os.path.ismount(MOUNT):
        print('V380: /mnt/usb2 is not mounted; skipped', file=sys.stderr)
        return 2
    WORK.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    if not SOURCE.is_file() or not (BASE / 'v380_hevc_decode.py').is_file() or not CONVERTER.is_file():
        log('Missing source scripts under /mnt/usb2/V380')
        return 2
    if not PASSWORD_FILE.is_file():
        log('Missing /etc/v380_camera_password')
        return 2

    # Non-blocking lock makes cron/manual overlap harmless.
    with open('/tmp/v380_cycle.lock', 'a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('Previous run still active; skipping')
            return 0
        cleanup_temp()
        prune_archive()
        if shutil.disk_usage(MOUNT).free < MIN_FREE_BYTES:
            log('Skipped: flash drive does not have 3 GiB free')
            return 0
        started = dt.datetime.now()
        log('Starting scheduled 25-second recording')
        success = False
        for relay in relay_candidates():
            log(f'Trying relay {relay}:8800')
            raw = capture(relay)
            if raw is not None:
                dst = ARCHIVE / (started.strftime('%Y-%m-%d_%H-%M-%S') + '.mp4')
                if remux_video(raw, dst):
                    success = True
                    break
        if not success:
            log('Camera offline, stream unavailable, or MP4 conversion failed; retry at next schedule')
        cleanup_temp()
        prune_archive()
        return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
