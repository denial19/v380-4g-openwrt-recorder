#!/usr/bin/env python3
"""Experimental multi-vehicle change detection from NanoDet JSON observations.

This does NOT establish a vehicle's identity. Email is disabled by default.
"""
import argparse
import fcntl
import json
import math
import os
import pathlib
import smtplib
import ssl
import tempfile
import time
from datetime import datetime, timezone
from email.message import EmailMessage

VEHICLES = {'car', 'truck', 'bus'}


def atomic_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def iou(a, b):
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    overlap = max(x2 - x1, 0) * max(y2 - y1, 0)
    total = a[2] * a[3] + b[2] * b[3] - overlap
    return overlap / total if total > 0 else 0


def match_score(a, b, w, h):
    overlap = iou(a, b)
    # Stable parked objects can have bounding-box jitter at night.
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    center_distance = math.hypot((ax - bx) / max(w, 1), (ay - by) / max(h, 1))
    if overlap >= .16:
        return 1.0 + overlap
    if center_distance < .07:
        return .5 - center_distance
    return -1


def in_roi(box, roi):
    if not roi:
        return True
    cx = box[0] + box[2] / 2
    cy = box[1] + box[3] / 2
    x0, y0, x1, y1 = roi
    return x0 <= cx <= x1 and y0 <= cy <= y1


def update(state, observation, source, roi=None, seen_confirm=2, missing_confirm=2):
    """Pure update; returns (state, new_events), no email or I/O."""
    if source == state.get('last_source'):
        return state, []
    if not isinstance(observation.get('objects'), list):
        raise ValueError('JSON must contain objects[]; cannot mark absence without a valid inference')
    w = observation['width']
    h = observation['height']
    if w < 32 or h < 32:
        raise ValueError('Invalid image dimensions')
    if roi:
        if len(roi) != 4 or roi[2] <= roi[0] or roi[3] <= roi[1]:
            raise ValueError('Invalid ROI')

    raw = []
    for obj in observation['objects']:
        if obj.get('label') not in VEHICLES or float(obj.get('confidence', 0)) < .35:
            continue
        b = obj['bbox']
        if len(b) != 4 or b[2] <= 0 or b[3] <= 0 or not in_roi(b, roi):
            continue
        raw.append({'label': obj['label'], 'box': list(b), 'confidence': float(obj['confidence'])})

    tracks = state.setdefault('tracks', [])
    ids = set()
    detections = set()
    pairs = []
    for i, t in enumerate(tracks):
        if t.get('misses', 0) >= missing_confirm:
            continue
        for j, det in enumerate(raw):
            score = match_score(t['box'], det['box'], w, h)
            if score >= 0:
                pairs.append((score, i, j))
    for score, i, j in sorted(pairs, reverse=True):
        if i in ids or j in detections:
            continue
        t = tracks[i]
        t['box'] = raw[j]['box']
        t['label'] = raw[j]['label']
        t['confidence'] = raw[j]['confidence']
        t['hits'] += 1
        t['misses'] = 0
        ids.add(i)
        detections.add(j)

    events = []
    for i, t in enumerate(tracks):
        if i in ids or t.get('misses', 0) >= missing_confirm:
            continue
        t['misses'] = t.get('misses', 0) + 1
        if t['misses'] == missing_confirm and t['hits'] >= seen_confirm:
            events.append({
                'event': 'vehicle_no_longer_detected',
                'track_id': t['id'],
                'previous_bbox': t['box'],
                'source': source,
                'utc': datetime.now(timezone.utc).isoformat(),
                'warning': 'Possible departure; not proof of physical vehicle identity.'
            })

    for j, det in enumerate(raw):
        if j in detections:
            continue
        next_id = state.get('next_id', 1)
        state['next_id'] = next_id + 1
        tracks.append(dict(id=next_id, label=det['label'], box=det['box'],
                           confidence=det['confidence'], hits=1, misses=0))
    # Keep only active and recent tracks. The number of tracked objects is bounded.
    state['tracks'] = [t for t in tracks if t['misses'] <= missing_confirm][:50]
    state['last_source'] = source
    state['observations'] = state.get('observations', 0) + 1
    return state, events


def send_mail(cfg_path, event):
    cfg_path = pathlib.Path(cfg_path)
    if not cfg_path.is_file():
        return 'disabled (no SMTP config)'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    if not cfg.get('enabled', False):
        return 'disabled in SMTP config'
    password_path = pathlib.Path(cfg['password_file'])
    if password_path.stat().st_mode & 0o077:
        raise PermissionError('SMTP password file must be mode 600')
    password = password_path.read_text(encoding='utf-8').rstrip('\r\n')
    msg = EmailMessage()
    msg['From'] = cfg['from']
    msg['To'] = cfg['to']
    msg['Subject'] = 'V380: автомобиль больше не обнаружен'
    msg.set_content(
        f"Камера: парковка\nОбъект #{event['track_id']} больше не обнаружен "
        f"на двух последовательных проверках.\nЗапись: {event['source']}\n"
        "Внимание: это результат компьютерного зрения, а не подтверждение "
        "фактического отъезда определённой машины.\n"
    )
    host = cfg['host']
    port = int(cfg.get('port', 465))
    with (smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20)
          if cfg.get('security', 'ssl') == 'ssl' else smtplib.SMTP(host, port, timeout=20)) as smtp:
        if cfg.get('security', 'ssl') != 'ssl':
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(cfg['username'], password)
        smtp.send_message(msg)
    return 'sent'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('detections_json', help='JSON output created by v380-nanodet')
    p.add_argument('--source', required=True, help='unique MP4 file name for this observation')
    p.add_argument('--state', default='/mnt/usb2/V380/ai/parking-state.json')
    p.add_argument('--event-log', default='/mnt/usb2/V380/ai/parking-events.jsonl')
    p.add_argument('--smtp', default='/etc/v380_ai_mail.json')
    p.add_argument('--roi', nargs=4, type=int, metavar=('X0','Y0','X1','Y1'))
    p.add_argument('--send-mail', action='store_true', help='requires enabled SMTP config')
    args = p.parse_args()
    observation = json.loads(pathlib.Path(args.detections_json).read_text(encoding='utf-8'))
    state_path = pathlib.Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(state_path) + '.lock', 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        state, events = update(state, observation, args.source, args.roi)
        atomic_json(state_path, state)
        if events:
            with open(args.event_log, 'a', encoding='utf-8') as f:
                for event in events:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
        print(json.dumps({'tracked_vehicles': len([t for t in state['tracks'] if t['misses'] == 0]),
                          'events': events}, ensure_ascii=False))
        if args.send_mail:
            for event in events:
                try:
                    print('SMTP:', send_mail(args.smtp, event))
                except Exception as exc:
                    print('SMTP ERROR:', type(exc).__name__, str(exc))
                    # Event remains on disk; do not silently send duplicates.

if __name__ == '__main__':
    main()
