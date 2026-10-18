"""Join existing V20 reference movies for local viewing; no hardware interfaces."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
GROUPS = [('main_A02_A10', range(2, 11)), ('drills_A11_A14', range(11, 15))]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode or result.stderr.strip():
        raise RuntimeError(result.stderr[-4000:])
    return result.stdout


def probe(path):
    return json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def frame_hashes(path):
    output = command(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0',
                      '-fps_mode', 'passthrough', '-f', 'framemd5', '-'])
    return [line.rsplit(',', 1)[-1].strip() for line in output.splitlines() if line and not line.startswith('#')]


def build(source, output):
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=True)
    actions = json.loads((source / 'actions.json').read_text(encoding='utf-8-sig'))
    result = dict(schema='v20_other_reference_previews_v1', source=str(source),
                  source_actions_sha256=sha(source / 'actions.json'), hardware_used=False,
                  full_show=False, motor_ready=False, files=[])
    work_root = ROOT / '.review_work/v20-preview-builds'
    work_root.mkdir(parents=True, exist_ok=True)
    work_root.resolve().relative_to(ROOT.resolve())
    with tempfile.TemporaryDirectory(prefix='v20-preview-', dir=work_root) as temporary:
        work = Path(temporary)
        work.resolve().relative_to(work_root.resolve())
        for name, numbers in GROUPS:
            destination = output / (name + '.mp4')
            if destination.exists():
                raise FileExistsError('Preserve the existing preview: ' + str(destination))
            chapters = []
            movies = []
            expected_hashes = []
            offset = 0.
            signature = None
            for number in numbers:
                action = next(a for a in actions if a['id'] == 'A%02d' % number)
                movie = source / (action['id'] + '_' + action['title']) / 'animation.mp4'
                info = probe(movie)
                video = next(s for s in info['streams'] if s['codec_type'] == 'video')
                audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
                current = [video[k] for k in ('codec_name', 'width', 'height', 'pix_fmt', 'r_frame_rate')]
                current += [audio[k] for k in ('codec_name', 'sample_rate', 'channels')]
                if signature is not None and current != signature:
                    raise ValueError('Incompatible source streams; do not silently re-encode')
                signature = current
                duration = float(info['format']['duration'])
                hashes = frame_hashes(movie)
                expected_hashes += hashes
                chapters.append(dict(id=action['id'], title=action['title'], start_s=offset,
                    end_s=offset + duration, original_audio_range_s=[action['start'], action['end']],
                    source=movie.relative_to(ROOT).as_posix(), source_sha256=sha(movie), frames=len(hashes)))
                offset += duration
                movies.append(movie)
            listing = work / (name + '.txt')
            def escape(path):
                return path.as_posix().replace("'", "'\\''")
            listing.write_text(''.join("file '" + escape(p) + "'\n" for p in movies), encoding='utf-8')
            metadata = work / (name + '.ffmetadata')
            lines = [';FFMETADATA1', 'title=V20 ' + name, 'comment=Independent reference previews; no hardware commands']
            for chapter in chapters:
                lines += ['[CHAPTER]', 'TIMEBASE=1/1000', 'START=' + str(round(chapter['start_s'] * 1000)),
                          'END=' + str(round(chapter['end_s'] * 1000)), 'title=' + chapter['id'] + ' ' + chapter['title']]
            metadata.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            command(['ffmpeg', '-v', 'error', '-n', '-f', 'concat', '-safe', '0', '-i', str(listing),
                     '-f', 'ffmetadata', '-i', str(metadata), '-map', '0:v:0', '-map', '0:a:0',
                     '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
                     '-movflags', '+faststart', str(destination)])
            actual_hashes = frame_hashes(destination)
            if actual_hashes != expected_hashes:
                raise RuntimeError('Joined video frames differ from the ordered source movies')
            # Decode both streams, so an intact container alone cannot pass QA.
            command(['ffmpeg', '-v', 'error', '-err_detect', 'explode', '-i', str(destination),
                     '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'])
            info = probe(destination)
            entry = dict(file=destination.name, bytes=destination.stat().st_size, sha256=sha(destination),
                         duration_s=float(info['format']['duration']), frames=len(actual_hashes),
                         decoded_frames_match_sources=True, audio_video_decode_passed=True,
                         video_audio_stream_copy=True, chapters=chapters)
            result['files'].append(entry)
            print(json.dumps(dict(file=str(destination), duration_s=entry['duration_s'], frames=entry['frames']), ensure_ascii=False), flush=True)
    (output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=ROOT / '\u4efb\u52a1\u4e00_V20_\u56fa\u5b9a\u6ed1\u8f68\u72ec\u7acb\u52a8\u4f5c')
    p.add_argument('--output', type=Path, default=ROOT / 'shadow_play/planning/wusong_v20_20261018/other_previews')
    a = p.parse_args()
    build(a.source, a.output)
