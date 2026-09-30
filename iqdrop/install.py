"""Add or remove the iqdrop hooks in Codex and Claude Code configuration files."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from iqdrop.hook import CONFIG_FILE, TEXT

HOOK_SCRIPT = Path(__file__).resolve().with_name('hook.py')
STATS_SCRIPT = HOOK_SCRIPT.with_name('stats.py')
LEGACY_SKILLS = ('iqdrop-stats', 'iqdrop-now')
SKILLS = {
    'iqdrop-recently': '''---
name: iqdrop-recently
description: >-
  Report the current coding agent's average iqdrop score over the last few hours: how many
  answers Jev scored and their average Answer IQ and Understanding, for the model this session
  is using. Use when the user asks how smart the agent is right now or has been in the last few
  hours, e.g. "最近 3 小时智商怎么样" "你现在状态如何" "刚才表现怎么样". For per-model history or
  comparisons between models, use iqdrop-history instead.
---

# iqdrop recently

Run this and show its one-line output to the user as is:

```bash
{command} recently --client {client} --hours 3
```

- Change `--hours` when the user names another window ("today" is `--hours 24`).
- Add `--model <id>` only when the user asks about a specific model.

Add nothing beyond that line, except one short sentence when it is marked as a small sample.
''',
    'iqdrop-history': '''---
name: iqdrop-history
description: >-
  Show long-term iqdrop scores per model: each model's average Answer IQ and Understanding over
  its history, split by day or by hours to show how it varied, with Codex and Claude Code models
  ranked together. Use when the user asks for a score per model, how models compare, a model's
  long-term or historical performance, or whether a model swings over time, e.g. "各个模型分数怎么样"
  "astra 按 6 小时看一下" "长期表现如何". For just the current agent's recent average, use iqdrop-recently.
---

# iqdrop history

Run this and show the output to the user as is:

```bash
{command} models --client all --days 30 --period day
```

- `--period` can be `day`, `6h`, `3h` or `hour`; use a shorter period when the user suspects a
  model swings within a day. Change `--days` for a longer or shorter history.
- `--client codex` or `--client claude` limits it to one side.

After the output, add at most two sentences. Scores are a plain average of all replies. Periods
marked as a small sample (fewer than 5 answers) should not be read as a change, and differences
between Codex and Claude Code models partly reflect different tasks. Do not claim a model was
degraded on this evidence alone.
''',
}
MARKER = 'iqdrop'


def config_path(client: str) -> Path:
    if client == 'codex':
        return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'hooks.json'
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'settings.json'


def interpreter() -> str:
    # sys.executable is often a versioned path that a package-manager upgrade removes;
    # the python3 on PATH survives upgrades, so use it when it is the same interpreter.
    found = shutil.which('python3')
    if found and os.path.realpath(found) == os.path.realpath(sys.executable):
        return found
    return sys.executable


def command(action: str, client: str) -> str:
    return ' '.join(shlex.quote(part) for part in
                    (interpreter(), str(HOOK_SCRIPT), action, '--client', client))


def ours(group: object) -> bool:
    hooks = group.get('hooks', []) if isinstance(group, dict) else []
    return any(MARKER in str(hook.get('command', '')) and HOOK_SCRIPT.name in str(hook.get('command', ''))
               for hook in hooks if isinstance(hook, dict))


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit(f'{path} is not a JSON object; leaving it untouched')
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + '.bak-iqdrop'))
    temp = path.with_name(path.name + '.tmp-iqdrop')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def strip(data: dict) -> dict:
    hooks = data.get('hooks')
    if not isinstance(hooks, dict):
        return data
    for event in ('UserPromptSubmit', 'Stop'):
        groups = hooks.get(event)
        if isinstance(groups, list):
            kept = [group for group in groups if not ours(group)]
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event)
    if not hooks:
        data.pop('hooks')
    return data


def install(client: str) -> Path:
    path = config_path(client)
    data = strip(load(path))
    hooks = data.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise SystemExit(f'"hooks" in {path} is not an object; leaving it untouched')
    if client == 'codex':
        data.setdefault('description', 'Score every answer with Jev (iqdrop).')
    hooks.setdefault('UserPromptSubmit', []).append(
        {'hooks': [{'type': 'command', 'command': command('capture', client), 'timeout': 5}]})
    hooks.setdefault('Stop', []).append(
        {'hooks': [{'type': 'command', 'command': command('score', client), 'timeout': 35,
                    'statusMessage': 'iqdrop: Jev is scoring the answer'}]})
    save(path, data)
    return path


def uninstall(client: str) -> Path:
    path = config_path(client)
    if path.exists():
        save(path, strip(load(path)))
    return path


def skills_root(client: str) -> Path:
    if client == 'codex':
        return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills'
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'skills'


def install_skills(client: str) -> list[Path]:
    root = skills_root(client)
    for name in LEGACY_SKILLS:  # replaced by the skills below; only remove what iqdrop wrote
        old = root / name / 'SKILL.md'
        if old.exists() and 'iqdrop' in old.read_text(encoding='utf-8'):
            shutil.rmtree(old.parent)
    command = ' '.join(shlex.quote(part) for part in (interpreter(), str(STATS_SCRIPT)))
    written = []
    for name, template in SKILLS.items():
        path = root / name / 'SKILL.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template.replace('{command}', command).replace('{client}', client), encoding='utf-8')
        written.append(path)
    return written


def set_config(updates: dict) -> None:
    lines = CONFIG_FILE.read_text(encoding='utf-8').splitlines() if CONFIG_FILE.exists() else []
    lines = [line for line in lines if line.partition('=')[0].strip().removeprefix('export ').strip()
             not in updates]
    lines += [f'{key}={value}' for key, value in updates.items()]
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    CONFIG_FILE.chmod(0o600)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='iqdrop')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'uninstall'):
        sub = commands.add_parser(name, help=f'{name} the hooks')
        sub.add_argument('client', choices=('codex', 'claude', 'all'))
    skill = commands.add_parser('install-skill', help='install the iqdrop-recently and iqdrop-history skills')
    skill.add_argument('client', choices=('codex', 'claude', 'all'))
    commands.add_parser('set-key', help='store your Typesafe (Jev) API key')
    lang = commands.add_parser('set-lang', help='language of the score line')
    lang.add_argument('lang', choices=sorted(TEXT))
    args = parser.parse_args(argv)

    clients = ('codex', 'claude') if getattr(args, 'client', None) == 'all' else (getattr(args, 'client', None),)
    if args.command == 'install':
        for client in clients:
            print(f'installed {client} hooks in {install(client)}')
        if 'codex' in clients:
            print('Codex: open Settings > Hooks and trust the two new iqdrop hooks.')
        print(f'Next: run `iqdrop set-key` if you have not stored a Jev key yet ({CONFIG_FILE}).')
    elif args.command == 'install-skill':
        for client in clients:
            for path in install_skills(client):
                print(f'installed {path.parent.name} for {client} at {path}')
    elif args.command == 'uninstall':
        for client in clients:
            print(f'removed {client} hooks from {uninstall(client)}')
    elif args.command == 'set-key':
        key = getpass.getpass('Typesafe API key (input hidden): ').strip()
        if not key:
            raise SystemExit('no key entered; nothing changed')
        set_config({'TYPESAFE_API_KEY': key})
        print(f'saved to {CONFIG_FILE} (mode 600)')
    elif args.command == 'set-lang':
        set_config({'IQDROP_LANG': args.lang})
        print(f'score line language set to {args.lang}')
