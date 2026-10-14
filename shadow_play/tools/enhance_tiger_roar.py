"""Enhance the documented 4–7 s roar while preserving every other PCM sample.

Requires NumPy and FFmpeg. Outputs a new PCM16 WAV and a verification report.
No board, motor, camera, or playback operations are performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

import numpy as np


SOURCE_SHA256 = '950e52cc19d84877327e2a399ec5e078ed76daece6e358a61c0679af2114db5e'
START_S, END_S, FADE_S = 4.0, 7.0, 0.1
FILTER = (
    'equalizer=f=180:t=q:w=0.8:g=2.5:precision=f64,'
    'equalizer=f=1300:t=q:w=1:g=1.5:precision=f64,'
    'acompressor=threshold=0.2:ratio=4:attack=0.2:release=25:makeup=3.2:'
    'knee=2.828:link=maximum:detection=peak,'
    'alimiter=limit=0.891250938:attack=3:release=20:level=false:latency=true'
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def levels(samples):
    data = samples.astype(np.float64) / 32768
    return dict(
        rms_dbfs=float(20 * np.log10(np.sqrt(np.mean(data * data)))),
        peak_dbfs=float(20 * np.log10(np.max(np.abs(data)))),
        full_scale_samples=int(np.sum((samples == 32767) | (samples == -32768))),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        parser.error('Output/report already exists; choose new names.')
    if sha256(args.source) != SOURCE_SHA256:
        parser.error('Source does not match the documented 67-second recording.')
    with wave.open(str(args.source), 'rb') as src:
        params = src.getparams()
        if (params.framerate, params.nchannels, params.sampwidth) != (44100, 2, 2):
            parser.error('Expected 44.1 kHz stereo PCM16.')
        original = np.frombuffer(src.readframes(params.nframes), dtype='<i2').reshape(-1, 2)
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(args.source),
               '-af', FILTER, '-f', 'f64le', '-acodec', 'pcm_f64le', 'pipe:1']
    processed = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    wet = np.frombuffer(processed, dtype='<f8').reshape(-1, 2)
    if wet.shape != original.shape or not np.isfinite(wet).all():
        raise RuntimeError('Processing changed frame count or produced invalid samples.')
    first, last = round(START_S * params.framerate), round(END_S * params.framerate)
    fade = round(FADE_S * params.framerate)
    weight = np.ones(last - first)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
    weight[:fade], weight[-fade:] = ramp, ramp[::-1]
    dry = original[first:last].astype(np.float64) / 32768
    blended = dry + weight[:, None] * (wet[first:last] - dry)
    quantized = np.rint(blended * 32768)
    if quantized.min() < -32768 or quantized.max() > 32767:
        raise RuntimeError('Enhanced segment would clip; refusing output.')
    output = original.copy()
    output[first:last] = quantized.astype('<i2')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        with wave.open(stream, 'wb') as dst:
            dst.setparams(params)
            dst.writeframes(output.tobytes())
    with wave.open(str(args.output), 'rb') as dst:
        verified = np.frombuffer(dst.readframes(dst.getnframes()), dtype='<i2').reshape(-1, 2)
        same_format = dst.getparams() == params
    outside_equal = (np.array_equal(original[:first], verified[:first])
                     and np.array_equal(original[last:], verified[last:]))
    if not same_format or not outside_equal or not np.array_equal(output, verified):
        raise RuntimeError('Output verification failed.')
    before, after = levels(original[first:last]), levels(verified[first:last])
    report = dict(
        source_name=args.source.name, source_sha256=SOURCE_SHA256,
        output_name=args.output.name, output_sha256=sha256(args.output),
        interval_s=[START_S, END_S], boundary_fade_s=FADE_S, filter=FILTER,
        location_evidence=['planning/wusong_complete_20261014/score.json',
                           'integrations/calibration/tiger_shadow_roar.py'],
        sample_rate_hz=params.framerate, channels=params.nchannels, pcm_bits=16,
        sample_frames=params.nframes, duration_s=params.nframes / params.framerate,
        before=before, after=after, rms_gain_db=after['rms_dbfs'] - before['rms_dbfs'],
        samples_outside_interval_identical=outside_equal,
        source_preserved=sha256(args.source) == SOURCE_SHA256,
        notes=['Region-based enhancement of the existing mix; no source separation.',
               'Original timeline and all samples outside 4–7 seconds are preserved.',
               'No controller audio, motion configuration or board file is replaced.'],
    )
    with args.report.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
