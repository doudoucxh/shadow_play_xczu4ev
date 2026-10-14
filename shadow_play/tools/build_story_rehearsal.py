"""Build an audio-clock rehearsal score; intentionally contains no hardware transport.

Recorded command anchors are evidence, not an inverse-kinematic calibration.
New sequencing, speed, combinations and poses require attended stage rehearsal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import wave

ROOT = Path(__file__).resolve().parents[1]
TITLES = ['虎现', '巡视领地', '昂首威吓', '伏低警觉', '收势潜伏', '武松入场',
          '环顾山林', '察觉停步', '对白亮相', '行进戒备', '腾跃扑咬与闪避',
          '对峙蓄势', '两次试探', '交锋格挡', '压制占位', '连续重拳',
          '受击倒伏', '喘息收势', '拖虎意象', '终场定格']
# Each line is a deliberate phase sequence, not a sinusoidal idle animation.
HUMAN = [
 '低手待场', '身体稳住；双手低位', '侧头察觉；近侧手收胸', '目光朝虎；短暂停顿',
 '低位准备', '身体先挺起；双手随后展开', '看左；看向虎；举手遮目；收手',
 '头杆停止；双手回身前', '单手示意；收回；双手亮相；放下；一手指虎',
 '身体朝虎前倾；双手交替小摆；逐渐转为格挡',
 '看虎蓄势；身体后让；双手护胸；虎头落下后回正',
 '一手前探；另一手收胸；身体朝虎压近',
 '第一次短探收回；第二次换手探出收回；头杆随出手朝虎',
 '近侧手格挡；对侧手短击；身体跟进；收手再蓄力',
 '站姿前压；两手前后错开；保留胸前格挡空间',
 '交替出拳；每拳前短蓄力、快速伸出、短停、收回；另一手胸前格挡；头杆向虎跟进并轻回弹',
 '最后一拳收回；身体仍朝虎；双手逐步放低',
 '身体轻起伏一次；低手观察；做抓尾意象',
 '头杆略后倾；双手低位牵引、放松、再牵引；原地表现拖拽',
 '保持末姿，不自动回中']
TIGER = [
 'Sony右侧贴幕亮相；头低而后端更低',
 '头先探；后端追随；抬头巡视；停顿；再次前探，避免等幅机械摆动',
 '虎头快抬；后端短留；头轻落，形成吼叫重音',
 '虎头压低；后端留后；两次幅度递减的警觉探头',
 '收成低伏姿；保留可见轮廓，不假装已退场',
 '低伏静候', '头部缓慢转向武松；后端保持低位', '短探头后停住',
 '对白时少动；末尾低伏注视武松', '后端降低留后；虎头蓄势',
 '后端先压低留后；虎头猛向左上；后端延迟追高；虎头猛向左下扑；低位落地',
 '低伏收束；头先起；后端拉开；一次呼吸式起伏',
 '36.2秒短扑试探；回收蓄势；38.6秒较强试探；回到低伏',
 '头前探威胁；遭格挡后回撤；再前压；受反击时头先回、后端迟随',
 '压低头部配合站姿压制；不承担人物重量',
 '逐拳受击：头先短退、后端迟随；前几拳仍有反扑意图，后几拳反应渐弱、姿态降低',
 '头部先沉；后端随后降低；58.36秒附近开始塌落；停止反扑',
 '低伏保留一次微弱余动，随后静止',
 '低位整体随牵引短动；没有滑轨时不做真实退场',
 '保持倒伏末姿']


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def validate(score):
    assert score['motor_ready'] is False
    end = score['audio']['sample_frames']
    previous = 0
    for scene in score['scenes']:
        assert scene['start_sample'] == previous
        assert scene['end_sample'] > previous
        previous = scene['end_sample']
        assert scene['execution_status'] == 'planned_not_executed'
    assert previous == end
    for cue in score['impact_cues']:
        assert 0 <= cue['sample'] < end
        assert cue['hardware_lead_s'] is None
    for motif in score['recorded_motifs'].values():
        assert motif['automatic_replay_allowed'] is False
        for anchor in motif['anchors']:
            assert len(anchor['command_pulse_us']) == 10
            assert anchor['actual_shaft_angles_deg'] is None
    assert score['end_policy']['automatic_center'] is False


def build(handoff):
    source = load(handoff / '03_action_plan.json')
    audio = source['audio']
    wav = handoff / audio['file']
    with wave.open(str(wav), 'rb') as w:
        assert (w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()) == (
            audio['sample_rate_hz'], audio['sample_frames'], audio['channels'], audio['pcm_bits']//8)
    assert hashlib.sha256(wav.read_bytes()).hexdigest() == audio['sha256'], 'Wrong audio version'
    rate = audio['sample_rate_hz']
    scenes = []
    for index, item in enumerate(source['scenes']):
        scenes.append(dict(id=item['id'], title=TITLES[index],
            start_sample=round(item['start_s']*rate), end_sample=round(item['end_s']*rate),
            start_s=item['start_s'], end_s=item['end_s'],
            human=HUMAN[index], tiger=TIGER[index], execution_status='planned_not_executed',
            coordination=('同一时钟编排；控制点不是独立关节，头杆承担身体跟进；'
                          '虎头与后端错时，检查两杆距离、贴幕及人物杆件交叉。')))
    motifs = {}
    for key, rel, field in [
        ('human_guard_punch', 'config/gesture_poses/operator_arc_ag_20261014.json', 'command_pulse_us'),
        ('tiger_leap_bite', 'config/tiger_operator_arc_at_result.20261014.json', 'command_pulses_us')]:
        data = load(ROOT / rel)
        motifs[key] = dict(source=rel, source_sha256=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(),
            status='recorded_attended_trial_not_whole_show_approval', automatic_replay_allowed=False,
            anchors=[dict(stage=p['stage'], command_pulse_us=p[field],
                          actual_shaft_angles_deg=None, evidence_views=p.get('views', {}))
                     for p in data['poses']])
    cues = []
    for index, c in enumerate(source['impact_cues']):
        t = c['time_s']
        # These are visual rhythm targets, NOT measured motor start deadlines.
        cues.append(dict(id=c['id'], time_s=t, sample=round(t*rate), arm=c['arm'],
            priority=c['priority'], confirmed_by_human=False, hardware_lead_s=None,
            phases=[dict(time_s=round(t-.30,3), action='蓄力，另一手格挡'),
                    dict(time_s=round(t-.16,3), action='出拳，头杆朝虎跟进'),
                    dict(time_s=t, action='视觉击中候选；虎头开始受击'),
                    dict(time_s=round(t+.06,3), action='虎后端延迟跟随'),
                    dict(time_s=round(t+.20,3), action='收拳，保留胸前格挡')],
            strength='短击' if c['priority']=='optional' else '重击',
            tiger_response_scale=round(1-index*.07,2)))
    score = dict(schema='wusong_audio_rehearsal_score_v1', title='武松打虎 · 67秒完整剧情排练',
        motor_ready=False, automatic_replay_allowed=False, audio=audio, scenes=scenes,
        impact_cues=cues, recorded_motifs=motifs,
        source_plan_sha256=hashlib.sha256((handoff/'03_action_plan.json').read_bytes()).hexdigest(),
        coordinate_policy='只有来源记录中的可见像素点可作证据；新场景坐标未采集，不套旧机位毫米矩阵。',
        slide_rails_enabled=False, new_combined_motion_verified=False,
        end_policy=dict(preview='freeze_at_audio_end', automatic_center=False,
            hardware='未接入；未来实机末姿保持受看门狗和人工停止约束，不无限保持'),
        rehearsal_order=['29–32秒：腾跃扑咬与人物闪避', '46–50秒：两拳与虎头/后端受击联动',
                         '50–58秒：重拳加速与受击递减', '58–60秒：倒伏',
                         '0–29秒及32–46秒：对白、巡视和试探', '60秒至终场', '完整音频连续排练'],
        limitations=['新组合、倒伏、站姿压制和拖拽仅规划，未获实机效果验证。',
                     '已执行素材的脉宽并非反馈角度，独立路线的组合也不保证不碰杆。',
                     '先用已记录大幅腾跃作为幅度基准；扩大幅度另存新版本，不能直接乘倍率。',
                     '音效候选未听审；视觉阶段时间是编舞目标，不代表电机实测提前量。',
                     '不加入未完成的越头交叉，不做真实骑乘承重；无滑轨版不宣称换位退场。'])
    validate(score)
    return score, wav


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', type=Path, required=True)
    parser.add_argument('--score', type=Path, required=True)
    parser.add_argument('--preview', type=Path, required=True)
    args = parser.parse_args()
    score, wav = build(args.handoff)
    args.score.parent.mkdir(parents=True, exist_ok=True)
    args.score.write_text(json.dumps(score, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    args.preview.mkdir(parents=True, exist_ok=True)
    shutil.copy2(wav, args.preview/'task1.wav')
    template = (Path(__file__).with_name('story_rehearsal.html')).read_text(encoding='utf-8')
    (args.preview/'index.html').write_text(template.replace('__SCORE_JSON__',
        json.dumps(score, ensure_ascii=False).replace('<', '\\u003c')), encoding='utf-8')
    print(json.dumps(dict(scenes=len(score['scenes']), impacts=len(score['impact_cues']),
        duration_seconds=score['audio']['duration_s'], motor_ready=False,
        preview=str(args.preview/'index.html')), ensure_ascii=False))


if __name__ == '__main__':
    main()
