"""Summarise stored scores: how one model did in a recent window versus its own baseline."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

if __package__ in (None, ''):  # allow `python3 iqdrop/stats.py` without installing the package
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iqdrop.hook import CHECK_MIN_OVERRIDE, FINAL_ONLY_CHECKS, read_json, settings

TEXT = {
    'en': {
        'none': 'No scored answers from {client} in the last {hours:g} h.',
        'head': '{model} · last {hours:g} h · {n} scored answers ({kinds})',
        'kinds': {'final': 'final', 'interim': 'progress', 'checkpoint': 'checkpoint'},
        'iq': 'Answer IQ', 'final_iq': 'final answers only', 'understanding': 'Understanding',
        'red': 'red lights', 'baseline': 'Baseline, previous {days:g} days',
        'no_baseline': 'no baseline yet (fewer than 3 scored answers in the previous {days:g} days)',
        'delta': '{sign}{delta:.1f} vs baseline, same reply kinds',
        'models_head': '{client} · last {days:g} days · Answer IQ by model (plain average of all replies)',
        'models_none': 'No scored answers from {client} in the last {days:g} days.',
        'model_line': '{model}  {n} answers · Answer IQ {iq} · Understanding {und}',
        'few': 'few', 'problems': 'Most frequent problems',
        'no_problems': 'none flagged', 'lowest': 'Lowest scored', 'small': 'Small sample: read with care.',
        'check_names': {'factual_error': 'factual or reasoning error', 'unverified_claim': 'unverified claims',
                        'missing_deliverable': 'incomplete delivery',
                        'constraint_violation': 'broke an explicit constraint',
                        'off_target': 'off target', 'needless_pause': 'stopped needlessly'},
    },
    'zh': {
        'none': '最近 {hours:g} 小时没有 {client} 的评分记录。',
        'head': '{model} · 最近 {hours:g} 小时 · 共 {n} 条（{kinds}）',
        'kinds': {'final': '最终回答', 'interim': '中间汇报', 'checkpoint': '待你确认'},
        'iq': '平均回答智商分', 'final_iq': '仅最终回答', 'understanding': '平均理解度',
        'red': '红灯', 'baseline': '基线：此前 {days:g} 天',
        'no_baseline': '暂无基线（此前 {days:g} 天的评分不足 3 条）',
        'delta': '按同类回复比基线 {sign}{delta:.1f}',
        'models_head': '{client} · 最近 {days:g} 天 · 各模型回答智商分（所有回复直接平均）',
        'models_none': '最近 {days:g} 天没有 {client} 的评分记录。',
        'model_line': '{model}  共 {n} 条 · 回答智商分 {iq} · 理解度 {und}',
        'few': '样本少', 'problems': '最常见的问题',
        'no_problems': '没有被标出的问题', 'lowest': '得分最低', 'small': '样本较少，结论仅供参考。',
        'check_names': {'factual_error': '事实或推理错误', 'unverified_claim': '缺少验证证据',
                        'missing_deliverable': '交付不完整', 'constraint_violation': '违反明确约束',
                        'off_target': '偏离目标', 'needless_pause': '不必要的停顿'},
    },
}


def load(root: Path) -> list[dict]:
    records = []
    for path in root.glob('scores/*/*.json'):
        record = read_json(path, None)
        if isinstance(record, dict) and record.get('status') == 'scored':
            records.append(record)
    return records


def flagged(record: dict, threshold: float) -> list[str]:
    final = record.get('answer_kind', 'final') == 'final'
    skipped = ('needless_pause',) if final else FINAL_ONLY_CHECKS
    return [name for name, p in (record.get('checks') or {}).items()
            if name not in skipped and p >= max(threshold, CHECK_MIN_OVERRIDE.get(name, 0))]


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 1) if values else None


def summarize(records: list[dict], model: str | None, hours: float, baseline_days: float,
              threshold: float, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    start = now - hours * 3600
    if model is None:
        recent = [r for r in records if r.get('time_unix', 0) >= start]
        latest = max(recent or records, key=lambda r: r.get('time_unix', 0), default={})
        model = latest.get('assistant_model')
    mine = [r for r in records if r.get('assistant_model') == model]
    window = sorted((r for r in mine if r.get('time_unix', 0) >= start), key=lambda r: r['time_unix'])
    base = [r for r in mine if start - baseline_days * 86400 <= r.get('time_unix', 0) < start]

    def block(rows: list[dict]) -> dict:
        finals = [r for r in rows if r.get('answer_kind', 'final') == 'final']
        return {
            'n': len(rows),
            'kinds': {k: sum(r.get('answer_kind', 'final') == k for r in rows)
                      for k in ('final', 'interim', 'checkpoint')},
            'iq': mean([r['scores_100']['answer_iq'] for r in rows]),
            'final_iq': mean([r['scores_100']['answer_iq'] for r in finals]),
            'understanding': mean([r['scores_100']['intent_understanding'] for r in rows]),
            'red': sum(bool(r.get('iq_alert')) for r in rows),
        }

    def adjusted(key: str) -> float | None:
        # Compare each reply kind with its own baseline, then weight by the window's mix, so a
        # window full of (higher-scoring) checkpoints does not look like an improvement.
        total = weight = 0.0
        for kind in ('final', 'interim', 'checkpoint'):
            now_k = [r['scores_100'][key] for r in window if r.get('answer_kind', 'final') == kind]
            then_k = [r['scores_100'][key] for r in base if r.get('answer_kind', 'final') == kind]
            if now_k and len(then_k) >= 3:
                total += len(now_k) * (statistics.mean(now_k) - statistics.mean(then_k))
                weight += len(now_k)
        return round(total / weight, 1) if weight else None

    problems: dict[str, int] = {}
    for r in window:
        for name in flagged(r, threshold):
            problems[name] = problems.get(name, 0) + 1
    lowest = sorted(window, key=lambda r: r['scores_100']['answer_iq'])[:3]
    return {
        'model': model, 'hours': hours, 'baseline_days': baseline_days,
        'window': block(window), 'baseline': block(base) if len(base) >= 3 else None,
        'delta': {'iq': adjusted('answer_iq'), 'understanding': adjusted('intent_understanding')},
        'problems': sorted(problems.items(), key=lambda item: -item[1]),
        'lowest': [{'time_unix': r['time_unix'], 'answer_iq': r['scores_100']['answer_iq'],
                    'kind': r.get('answer_kind', 'final'),
                    'prompt': ' '.join(r.get('user_prompt', '').split())[:80]} for r in lowest],
    }


def render(summary: dict, client: str, lang: str) -> str:
    text = TEXT[lang]
    w, b = summary['window'], summary['baseline']
    if not w['n']:
        return text['none'].format(client=client, hours=summary['hours'])
    kinds = ' / '.join(f'{text["kinds"][k]} {v}' for k, v in w['kinds'].items() if v)
    lines = [text['head'].format(model=summary['model'] or '?', hours=summary['hours'], n=w['n'], kinds=kinds), '']

    def delta(diff: float | None) -> str:
        if diff is None:
            return ''
        note = text['delta'].format(sign='+' if diff >= 0 else '', delta=diff)
        return f'（{note}）' if lang == 'zh' else f' ({note})'

    lines.append(f'{text["iq"]}: {w["iq"]}{delta(summary["delta"]["iq"])}')
    if w['final_iq'] is not None and w['kinds']['final'] != w['n']:
        base_final = b and b['final_iq']
        lines.append(f'  {text["final_iq"]}: {w["final_iq"]}'
                     + delta(round(w['final_iq'] - base_final, 1) if base_final is not None and b['kinds']['final'] >= 3 else None))
    lines.append(f'{text["understanding"]}: {w["understanding"]}{delta(summary["delta"]["understanding"])}')
    lines.append(f'{text["red"]}: {w["red"]}/{w["n"]}')
    if b:
        lines.append(f'{text["baseline"].format(days=summary["baseline_days"])}: '
                     f'{text["iq"]} {b["iq"]} · {text["understanding"]} {b["understanding"]} · n={b["n"]}')
    else:
        lines.append(text['no_baseline'].format(days=summary['baseline_days']))
    lines += ['', text['problems'] + ':']
    lines += [f'  {text["check_names"][name]} × {count}' for name, count in summary['problems']] \
        or ['  ' + text['no_problems']]
    lines += ['', text['lowest'] + ':']
    for item in summary['lowest']:
        stamp = time.strftime('%H:%M', time.localtime(item['time_unix']))
        lines.append(f'  {stamp}  {item["answer_iq"]:g}  [{text["kinds"][item["kind"]]}]  {item["prompt"]}')
    if w['n'] < 5:
        lines += ['', text['small']]
    return '\n'.join(lines)


PERIODS = {'day': 86400, '6h': 6 * 3600, '3h': 3 * 3600, 'hour': 3600}


def period_start(stamp: float, period: str) -> float:
    local = time.localtime(stamp)
    midnight = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, 0, 0, -1))
    size = PERIODS[period]
    return midnight + (stamp - midnight) // size * size


def by_model(records: list[dict], days: float, period: str, now: float | None = None) -> list[dict]:
    """Plain averages per model, overall and per time period, most-used model first."""
    now = time.time() if now is None else now
    rows = [r for r in records if r.get('time_unix', 0) >= now - days * 86400]
    models: dict[str, list[dict]] = {}
    for r in rows:
        models.setdefault(r.get('assistant_model') or '?', []).append(r)
    result = []
    for model, items in sorted(models.items(), key=lambda kv: -len(kv[1])):
        periods: dict[float, list[dict]] = {}
        for r in items:
            periods.setdefault(period_start(r['time_unix'], period), []).append(r)
        result.append({
            'model': model, 'n': len(items),
            'iq': mean([r['scores_100']['answer_iq'] for r in items]),
            'understanding': mean([r['scores_100']['intent_understanding'] for r in items]),
            'periods': [{'start': start, 'n': len(group),
                         'iq': mean([r['scores_100']['answer_iq'] for r in group])}
                        for start, group in sorted(periods.items())],
        })
    return result


def render_models(models: list[dict], client: str, days: float, period: str, lang: str) -> str:
    text = TEXT[lang]
    if not models:
        return text['models_none'].format(client=client, days=days)
    stamp = '%m-%d' if period == 'day' else '%m-%d %H:00'
    lines = [text['models_head'].format(client=client, days=days)]
    for m in models:
        lines += ['', text['model_line'].format(model=m['model'], n=m['n'], iq=m['iq'], und=m['understanding'])]
        for p in m['periods']:
            bar = '█' * round(p['iq'] / 10)
            few = f'  ({text["few"]})' if p['n'] < 5 else ''
            lines.append(f'  {time.strftime(stamp, time.localtime(p["start"]))}  {p["iq"]:5.1f}  '
                         f'{bar:<10}  n={p["n"]}{few}')
    return '\n'.join(lines)


def models_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='iqdrop models',
                                     description='Answer IQ per model, overall and per time period')
    parser.add_argument('--client', choices=('codex', 'claude', 'all'), default='all')
    parser.add_argument('--days', type=float, default=7)
    parser.add_argument('--period', choices=sorted(PERIODS), default='day')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    config = settings()
    clients = ('codex', 'claude') if args.client == 'all' else (args.client,)
    output = {client: by_model(load(config['data_dir'] / client), args.days, args.period)
              for client in clients}
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    blocks = [render_models(models, client, args.days, args.period, config['lang'])
              for client, models in output.items() if models or args.client != 'all']
    print('\n\n'.join(blocks) or TEXT[config['lang']]['models_none'].format(client=args.client, days=args.days))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='iqdrop stats',
                                     description='How one model scored recently, versus its own baseline')
    parser.add_argument('--client', choices=('codex', 'claude'), default='codex')
    parser.add_argument('--hours', type=float, default=3)
    parser.add_argument('--model', help='Model id; defaults to the one behind the latest scored answer')
    parser.add_argument('--baseline-days', type=float, default=7)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    config = settings()
    summary = summarize(load(config['data_dir'] / args.client), args.model, args.hours,
                        args.baseline_days, config['check_threshold'])
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json
          else render(summary, args.client, config['lang']))


if __name__ == '__main__':
    if sys.argv[1:2] == ['models']:
        models_main(sys.argv[2:])
    else:
        main()
