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
SKILL_NAME = 'iqdrop-stats'
SKILL = '''---
name: iqdrop-stats
description: >-
  Report how smart the current coding agent has been recently, from the iqdrop scores that
  Jev gave its answers: average Answer IQ and Understanding over the last few hours, compared
  with the same model's own baseline, plus the most frequent problems and the lowest-scored
  answers. Use when the user asks how the agent or model has been doing, whether it got
  dumber or was nerfed, for its IQ over the last N hours, or for iqdrop stats. 用户问“最近 3
  小时智商怎么样”“是不是降智了”“这个模型最近表现如何”时使用。
---

# iqdrop stats

Run this and show the output to the user as is:

```bash
{command} --client {client} --hours 3
```

- Change `--hours` when the user names another window ("today" is `--hours 24`).
- Add `--model <id>` to look at a specific model; by default it reports the model behind the
  most recent scored answer, which is normally the one you are running as.
- Add `--json` if you need the raw numbers.

After the output, add at most two sentences of reading:

- The baseline comparison is by reply kind, so a mix with more checkpoints does not look like
  an improvement. A drop of 10 points or more against the baseline, over at least 5 answers,
  is worth pointing out; smaller moves are noise.
- Say plainly when the sample is small or there is no baseline yet. Do not claim the model was
  degraded on this evidence alone: scores depend on task difficulty and come from another
  model.

Scores live in `~/.iqdrop/{client}/scores/`. Do not edit or delete them.
'''
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


def skill_dir(client: str) -> Path:
    if client == 'codex':
        return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills' / SKILL_NAME
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'skills' / SKILL_NAME


def install_skill(client: str) -> Path:
    command = ' '.join(shlex.quote(part) for part in (interpreter(), str(STATS_SCRIPT)))
    path = skill_dir(client) / 'SKILL.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SKILL.replace('{command}', command).replace('{client}', client), encoding='utf-8')
    return path


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
    skill = commands.add_parser('install-skill', help='install the iqdrop-stats skill')
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
            print(f'installed the {SKILL_NAME} skill for {client} at {install_skill(client)}')
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
