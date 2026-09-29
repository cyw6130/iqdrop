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


if __name__ == '__main__':
    unittest.main()
