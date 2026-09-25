import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from iqdrop import hook, install


def config(tmp, **overrides):
    value = {'key': 'test-key', 'lang': 'en', 'check_threshold': 0.5, 'alert_below': 60,
             'notify': False, 'data_dir': Path(tmp), 'jev_model': 'jev-test'}
    value.update(overrides)
    return value


def jev_payload(iq=2.6, understanding=3.5, checks=None, kind='final'):
    answers = {
        'answer_iq': {'score': iq, 'probabilities': {'2': 0.5, '3': 0.5}},
        'pause_iq': {'score': 3.0, 'probabilities': {'3': 1.0}},
        'answer_kind': {'choice': kind},
        'intent_understanding': {'score': understanding, 'probabilities': {'4': 0.8}},
        'response_speed': {'choice': 'normal'},
    }
    for name, value in (checks or {}).items():
        answers[name] = {'type': 'noul', 'noul': value}
    return {'model': 'jev-test', 'answers': answers, 'usage': {'input_tokens': 100}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def transcript(rows):
    handle = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    handle.close()
    return handle.name


def text(role, body, **extra):
    return {'type': role, 'message': {'content': [{'type': 'text', 'text': body}]}, **extra}


class GradeTest(unittest.TestCase):
    def test_parses_scores_and_checks(self):
        payload = jev_payload(checks={'unverified_claim': 0.77, 'off_target': 0.1})
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch('urllib.request.urlopen',
                           return_value=FakeResponse(json.dumps(payload).encode())) as urlopen:
            scores, evidence = hook.grade(config(tmp), 'do x', 'did x', [], 12.0)
        sent = json.loads(urlopen.call_args[0][0].data)
        self.assertEqual(set(hook.CHECKS) <= set(sent['questions']), True)
        self.assertEqual(sent['state']['elapsed_seconds'], 12.0)
        self.assertEqual(scores, {'answer_iq': 65.0, 'intent_understanding': 87.5,
                                  'result_iq': 65.0, 'pause_iq': 75.0})
        self.assertEqual(evidence['checks'], {'unverified_claim': 0.77, 'off_target': 0.1})

    def test_checkpoint_is_shown_with_the_pause_rubric_score(self):
        payload = jev_payload(iq=1.0, kind='checkpoint')
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch('urllib.request.urlopen', return_value=FakeResponse(json.dumps(payload).encode())):
            scores, evidence = hook.grade(config(tmp), 'name it', 'Pick one: a or b?', [], None)
        self.assertEqual(evidence['answer_kind'], 'checkpoint')
        self.assertEqual((scores['answer_iq'], scores['result_iq']), (75.0, 25.0))

    def test_missing_key_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(hook.MissingKey):
                hook.grade(config(tmp, key=''), 'p', 'a', [], None)


class LabelTest(unittest.TestCase):
    record = {'status': 'scored', 'scores_100': {'answer_iq': 52.8, 'intent_understanding': 90.8},
              'iq_alert': True, 'elapsed_seconds': 30.0, 'speed_judgment': {'choice': 'slow'},
              'checks': {'unverified_claim': 0.84, 'factual_error': 0.69, 'off_target': 0.14}}

    def test_flags_only_checks_over_threshold_highest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            line = hook.label(config(tmp), self.record)
        self.assertEqual(line, '🔴 Answer IQ: 52.8/100 · Understanding: 90.8/100 · 🚧 Slow · '
                               'Jev checks: unverified claims (84%); factual or reasoning error (69%).')

    def test_chinese_and_custom_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            line = hook.label(config(tmp, lang='zh', check_threshold=0.8), self.record)
        self.assertEqual(line, '🔴 回答智商分：52.8/100 · 理解度：90.8/100 · 🚧 偏慢 · Jev 检查：缺少验证证据(84%)。')

    def test_no_flags(self):
        record = {**self.record, 'checks': {'off_target': 0.1}, 'iq_alert': False}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(hook.label(config(tmp), record).endswith('Jev checks: no clear problems.'))

    def test_progress_update_skips_final_only_checks(self):
        record = {**self.record, 'answer_kind': 'interim', 'iq_alert': False,
                  'checks': {'missing_deliverable': 0.9, 'unverified_claim': 0.9,
                             'factual_error': 0.6, 'needless_pause': 0.65}}
        with tempfile.TemporaryDirectory() as tmp:
            line = hook.label(config(tmp), record)
        self.assertEqual(line, '🟢 Answer IQ: 52.8/100 · Understanding: 90.8/100 · 🚧 Slow · '
                               'Jev checks: factual or reasoning error (60%).')

    def test_confident_needless_pause_is_shown(self):
        record = {**self.record, 'answer_kind': 'checkpoint', 'checks': {'needless_pause': 0.8}}
        with tempfile.TemporaryDirectory() as tmp:
            line = hook.label(config(tmp, lang='zh'), record)
        self.assertEqual(line, '🔴 回答智商分：52.8/100 · 理解度：90.8/100 · 🚧 偏慢 · Jev 检查：不必要的停顿(80%)。')

    def test_unscored_explains_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            line = hook.label(config(tmp), {'status': 'unscored', 'error_type': 'MissingKey'})
        self.assertIn('no Jev API key configured', line)


class HandleTest(unittest.TestCase):
    def run_turn(self, tmp, client, stop_event, prompt='Explain TCP handshake'):
        conf = config(tmp)
        base = {'session_id': 's1', 'turn_id': 't1'} if client == 'codex' else {'session_id': 's1'}
        hook.handle({**base, 'hook_event_name': 'UserPromptSubmit', 'prompt': prompt}, client, conf)
        with mock.patch.object(hook, 'grade', return_value=(
                {'answer_iq': 80.0, 'intent_understanding': 90.0},
                {'speed_judgment': {'choice': 'normal'}, 'checks': {'unverified_claim': 0.2}})) as grade:
            output = hook.handle({**base, 'hook_event_name': 'Stop', 'stop_hook_active': False,
                                  **stop_event}, client, conf)
        return output, grade

    def test_codex_turn_is_scored_and_shown_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, grade = self.run_turn(tmp, 'codex', {'last_assistant_message': 'SYN, SYN-ACK, ACK'})
            self.assertEqual(output['continue'], True)
            self.assertNotIn('decision', output)
            self.assertTrue(output['systemMessage'].startswith('🟢 Answer IQ: 80/100'))
            self.assertEqual(grade.call_args[0][1:3], ('Explain TCP handshake', 'SYN, SYN-ACK, ACK'))
            root = Path(tmp) / 'codex'
            self.assertTrue((root / 'scores' / 's1' / 't1.json').exists())
            self.assertFalse((root / 'prompts' / 's1' / 't1.json').exists())

    def test_claude_scores_the_whole_turn_not_just_the_last_block(self):
        path = transcript([
            text('user', 'Q5: agree', origin={'kind': 'human'}, timestamp='2026-09-25T10:00:00Z'),
            text('assistant', 'Understood: part one.'),
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit'}]}},
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'ok'}]}},
            text('assistant', 'Recorded: part two.'),
        ])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                _, grade = self.run_turn(tmp, 'claude', {'last_assistant_message': 'Recorded: part two.',
                                                         'transcript_path': path}, prompt='Q5: agree')
            self.assertEqual(grade.call_args[0][2], 'Understood: part one.\n\nRecorded: part two.')
        finally:
            os.unlink(path)

    def test_claude_background_task_wakeup_is_not_scored(self):
        path = transcript([
            text('user', 'real question', origin={'kind': 'human'}),
            text('assistant', 'working on it'),
            text('user', '<task-notification>done</task-notification>', origin={'kind': 'task-notification'}),
            text('assistant', 'the task finished'),
        ])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                output, grade = self.run_turn(tmp, 'claude', {'last_assistant_message': 'the task finished',
                                                              'transcript_path': path})
            self.assertEqual(output, {'continue': True})
            grade.assert_not_called()
        finally:
            os.unlink(path)

    def test_forced_continuation_is_not_scored_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = hook.handle({'session_id': 's1', 'turn_id': 't1', 'hook_event_name': 'Stop',
                                  'stop_hook_active': True, 'last_assistant_message': 'x'},
                                 'codex', config(tmp))
        self.assertEqual(output, {'continue': True})

    def test_scoring_failure_never_blocks_the_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = hook.handle({'session_id': 's1', 'turn_id': 't1', 'hook_event_name': 'Stop',
                                  'last_assistant_message': 'answer'}, 'codex', config(tmp))
        self.assertEqual(output['continue'], True)
        self.assertIn('prompt not captured', output['systemMessage'])


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {'CODEX_HOME': self.tmp.name, 'CLAUDE_CONFIG_DIR': self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_install_keeps_other_hooks_and_is_idempotent(self):
        path = Path(self.tmp.name) / 'settings.json'
        other = {'hooks': [{'type': 'command', 'command': 'echo other'}]}
        path.write_text(json.dumps({'theme': 'dark', 'hooks': {'Stop': [other]}}))
        install.install('claude')
        install.install('claude')
        data = json.loads(path.read_text())
        self.assertEqual(data['theme'], 'dark')
        self.assertEqual(data['hooks']['Stop'][0], other)
        self.assertEqual(len(data['hooks']['Stop']), 2)
        self.assertEqual(len(data['hooks']['UserPromptSubmit']), 1)
        self.assertIn('--client claude', data['hooks']['Stop'][1]['hooks'][0]['command'])
        self.assertTrue((Path(self.tmp.name) / 'settings.json.bak-iqdrop').exists())

    def test_uninstall_removes_only_iqdrop(self):
        path = Path(self.tmp.name) / 'hooks.json'
        other = {'hooks': [{'type': 'command', 'command': 'echo other'}]}
        path.write_text(json.dumps({'hooks': {'Stop': [other]}}))
        install.install('codex')
        install.uninstall('codex')
        self.assertEqual(json.loads(path.read_text())['hooks'], {'Stop': [other]})

    def test_set_config_replaces_existing_value(self):
        conf = Path(self.tmp.name) / 'config.env'
        conf.write_text('export TYPESAFE_API_KEY=old\nIQDROP_LANG=en\n')
        with mock.patch.object(install, 'CONFIG_FILE', conf):
            install.set_config({'TYPESAFE_API_KEY': 'new'})
        self.assertEqual(conf.read_text(), 'IQDROP_LANG=en\nTYPESAFE_API_KEY=new\n')
        self.assertEqual(oct(conf.stat().st_mode & 0o777), '0o600')


if __name__ == '__main__':
    unittest.main()
