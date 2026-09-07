#!/usr/bin/env python3
"""Validate decoded video dimensions, rational frame rate, frame count and duration."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path)
    p.add_argument('--width', type=int, required=True)
    p.add_argument('--height', type=int, required=True)
    p.add_argument('--fps', required=True, help='24 or a rational such as 30000/1001')
    p.add_argument('--seconds', required=True)
    p.add_argument('--require-audio', action='store_true')
    p.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    p.add_argument('--json-output', type=Path)
    args = p.parse_args()
    if not args.ffprobe:
        p.error('ffprobe was not found; pass --ffprobe /path/to/ffprobe')
    if not args.video.is_file():
        p.error('Video file does not exist')
    try:
        fps, seconds = Fraction(args.fps), Fraction(args.seconds)
        if min(args.width, args.height, fps, seconds) <= 0:
            raise ValueError('Expected dimensions, fps and seconds must be positive')
        expected_frames = fps * seconds
        if expected_frames.denominator != 1:
            raise ValueError('Requested duration is not an integer count of native frames')
        raw = subprocess.run(
            [args.ffprobe, '-v', 'error', '-count_frames', '-show_streams',
             '-show_format', '-of', 'json', str(args.video)],
            check=True, capture_output=True, text=True,
        )
        data = json.loads(raw.stdout)
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        actual_fps = Fraction(video['avg_frame_rate'])
        actual_frames = int(video['nb_read_frames'])
        duration = float(video.get('duration', data['format']['duration']))
        has_audio = any(s['codec_type'] == 'audio' for s in data['streams'])
        checks = {
            'dimensions': (video['width'], video['height']) == (args.width, args.height),
            'fps': actual_fps == fps,
            'decoded_frame_count': actual_frames == expected_frames,
            'duration': abs(duration - float(seconds)) <= .5 / float(fps) + .001,
            'audio': has_audio or not args.require_audio,
        }
        result = {
            'status': 'PASS' if all(checks.values()) else 'FAIL',
            'file': args.video.name,
            'width': video['width'], 'height': video['height'],
            'fps': str(actual_fps), 'frames': actual_frames,
            'duration_seconds': duration, 'has_audio': has_audio, 'checks': checks,
        }
    except (ValueError, KeyError, StopIteration, subprocess.CalledProcessError, OSError) as exc:
        result = {'status': 'FAIL', 'file': args.video.name, 'error': str(exc)}
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(output + '\n', encoding='utf-8')
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
