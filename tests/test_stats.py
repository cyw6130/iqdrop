import unittest

from iqdrop import stats

NOW = 1_000_000.0


def rec(hours_ago, iq, kind='final', model='m1', understanding=80.0, checks=None, alert=False):
    return {'status': 'scored', 'time_unix': NOW - hours_ago * 3600, 'assistant_model': model,
            'answer_kind': kind, 'iq_alert': alert, 'checks': checks or {}, 'user_prompt': f'prompt {iq}',
            'scores_100': {'answer_iq': iq, 'intent_understanding': understanding}}


class SummarizeTest(unittest.TestCase):
    def test_window_baseline_and_default_model(self):
        records = [rec(1, 70), rec(2, 50, alert=True), rec(30, 99, model='other'),
                   rec(10, 60), rec(20, 60), rec(40, 60), rec(24 * 8, 10)]
        summary = stats.summarize(records, None, 3, 7, 0.5, now=NOW)
        self.assertEqual(summary['model'], 'm1')
        self.assertEqual(summary['window']['n'], 2)
        self.assertEqual(summary['window']['iq'], 60.0)
        self.assertEqual(summary['window']['red'], 1)
        self.assertEqual(summary['baseline']['n'], 3)  # the 8-day-old record is outside the baseline
        self.assertEqual(summary['delta']['iq'], 0.0)

    def test_delta_compares_like_with_like(self):
        # Many high-scoring checkpoints in the window must not read as an improvement.
        base = [rec(10 + i, 50) for i in range(3)] + [rec(20 + i, 85, kind='checkpoint') for i in range(3)]
        window = [rec(1, 50)] + [rec(1, 85, kind='checkpoint') for _ in range(4)]
        summary = stats.summarize(base + window, 'm1', 3, 7, 0.5, now=NOW)
        self.assertEqual(summary['window']['iq'], 78.0)
        self.assertEqual(summary['delta']['iq'], 0.0)

    def test_problems_follow_the_display_rules(self):
        window = [rec(1, 40, checks={'missing_deliverable': 0.9, 'needless_pause': 0.9}),
                  rec(1, 80, kind='checkpoint', checks={'missing_deliverable': 0.9, 'needless_pause': 0.75}),
                  rec(1, 80, kind='interim', checks={'needless_pause': 0.6})]
        summary = stats.summarize(window, 'm1', 3, 7, 0.5, now=NOW)
        self.assertEqual(dict(summary['problems']), {'missing_deliverable': 1, 'needless_pause': 1})
        self.assertEqual(summary['lowest'][0]['answer_iq'], 40)

    def test_render_without_data_or_baseline(self):
        empty = stats.summarize([], None, 3, 7, 0.5, now=NOW)
        self.assertIn('No scored answers', stats.render(empty, 'codex', 'en'))
        one = stats.summarize([rec(1, 70)], None, 3, 7, 0.5, now=NOW)
        text = stats.render(one, 'codex', 'zh')
        self.assertIn('暂无基线', text)
        self.assertIn('样本较少', text)


class CurrentTest(unittest.TestCase):
    def test_current_model_comes_from_this_session(self):
        records = [dict(rec(1, 80, model='a'), session='s1'), dict(rec(2, 60, model='a'), session='s2'),
                   dict(rec(0.5, 30, model='b'), session='s2'), dict(rec(5, 10, model='a'), session='s1')]
        summary = stats.current(records, 3, session='s1', now=NOW)
        self.assertEqual((summary['model'], summary['n'], summary['iq']), ('a', 2, 70.0))
        self.assertEqual(stats.current(records, 3, now=NOW)['model'], 'b')

    def test_render_current(self):
        line = stats.render_current({'model': 'a', 'hours': 3, 'n': 7, 'iq': 64.7, 'understanding': 90.5}, 'zh')
        self.assertEqual(line, 'a · 最近 3 小时 · 共 7 条 · 平均回答智商分 64.7 · 平均理解度 90.5')
        self.assertIn('样本少', stats.render_current({'model': 'a', 'hours': 3, 'n': 2, 'iq': 1, 'understanding': 1}, 'zh'))
        self.assertEqual(stats.render_current({'model': None, 'hours': 3, 'n': 0}, 'en'),
                         'No scored answers in the last 3 h.')


class ByModelTest(unittest.TestCase):
    def test_plain_average_per_model_and_period(self):
        day = 86400
        records = [rec(1, 80, kind='checkpoint'), rec(2, 40), rec(30, 60),
                   rec(1, 50, model='m2'), rec(24 * 10, 0)]
        models = stats.by_model(records, 7, 'day', now=NOW)
        self.assertEqual([m['model'] for m in models], ['m1', 'm2'])
        first = models[0]
        self.assertEqual((first['n'], first['iq']), (3, 60.0))  # kinds are not separated
        self.assertEqual(sum(p['n'] for p in first['periods']), 3)
        self.assertTrue(all(0 <= NOW - p['start'] < 8 * day for p in first['periods']))

    def test_periods_align_to_local_clock(self):
        import time
        stamp = time.mktime((2026, 9, 30, 14, 25, 0, 0, 0, -1))
        self.assertEqual(time.localtime(stats.period_start(stamp, '6h'))[3:5], (12, 0))
        self.assertEqual(time.localtime(stats.period_start(stamp, 'hour'))[3:5], (14, 0))
        self.assertEqual(time.localtime(stats.period_start(stamp, 'day'))[3:5], (0, 0))

    def test_render_marks_small_samples(self):
        text = stats.render_models(stats.by_model([rec(1, 70)], 7, 'day', now=NOW), 'codex', 7, 'day', 'zh')
        self.assertIn('m1  共 1 条 · 回答智商分 70', text)
        self.assertIn('样本少', text)


if __name__ == '__main__':
    unittest.main()
