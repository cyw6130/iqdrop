# iqdrop

**English** · [简体中文](README.zh-CN.md)

Catch silent quality drops in your coding agent. iqdrop hooks into **Codex** and **Claude Code**, sends every answer to an independent judge model ([Jev](https://docs.typesafe.ai) by Typesafe), and shows the verdict right under the answer:

```
🟢 Answer IQ: 74.2/100 · Understanding: 95.8/100 · Speed normal · Jev checks: no clear problems.
🔴 Answer IQ: 47.8/100 · Understanding: 84.8/100 · Speed normal · Jev checks: unverified claims (84%); factual or reasoning error (69%).
⏸ waiting on you · Understanding: 79.5/100 · Speed normal · Jev checks: no clear problems.
```

It grades the work you are actually doing, turn by turn, instead of a fixed benchmark. When the answers you get start scoring lower, you see it as it happens, not days later.

## What it checks

For every answer, Jev returns:

| Item | Meaning |
|---|---|
| **Answer IQ** (0–100) | Quality of the delivered result: correct, complete, usable, verified |
| **Understanding** (0–100) | How well the answer grasped the goal, scope, constraints and implied intent |
| **Speed** | Whether the wall-clock time was reasonable for the task |
| **Reply kind** | Final answer, progress update, or checkpoint (asking you before continuing) |
| **Checks** | Yes/no diagnostics: factual or reasoning error, unverified claims, incomplete delivery, broke an explicit constraint, off target, stopped needlessly |

A check is shown when Jev puts its probability at or above the threshold (50% by default; 70% for "stopped needlessly", which is partly a matter of taste). Progress updates and checkpoints are not given an Answer IQ, because the IQ rubric grades delivered results, and asking before acting is often the right call.

A red light means Answer IQ is below 60 on a final answer.

## Install

Requires Python 3.9+ and a Typesafe API key ([docs.typesafe.ai](https://docs.typesafe.ai)). No third-party packages.

```bash
pipx install git+https://github.com/cyw6130/iqdrop
iqdrop set-key          # stores the key in ~/.config/iqdrop/config.env (mode 600)
iqdrop install all      # or: iqdrop install codex / iqdrop install claude
```

Or from a clone: `python3 -m iqdrop install all`.

The installer merges its two hooks (UserPromptSubmit and Stop) into `~/.codex/hooks.json` and/or `~/.claude/settings.json`, keeps your other hooks, and backs up the file first (`*.bak-iqdrop`). Running it again does not create duplicates.

**Codex:** open Settings → Hooks and trust the two new hooks; Codex does not run new hooks until you do.

`iqdrop uninstall all` removes only iqdrop's entries.

## Configuration

`~/.config/iqdrop/config.env` (environment variables of the same name override it):

| Key | Default | Meaning |
|---|---|---|
| `TYPESAFE_API_KEY` | – | Your Jev key |
| `IQDROP_LANG` | `en` | Score line language: `en` or `zh` (`iqdrop set-lang zh`) |
| `IQDROP_CHECK_THRESHOLD` | `0.5` | Show a check at or above this probability |
| `IQDROP_ALERT_BELOW` | `60` | Red light below this Answer IQ |
| `IQDROP_NOTIFY` | `0` | `1` also posts a macOS notification |
| `IQDROP_DATA_DIR` | `~/.iqdrop` | Where score records are kept |

## Where to see the evidence

Every score is saved as JSON under `~/.iqdrop/<codex|claude>/scores/<session>/`, with Jev's full probability distributions, check probabilities, token usage, the prompt and the answer.

```bash
iqdrop explain --client claude --list     # scored answers in the latest session
iqdrop explain --client codex <id>        # one record in full
```

## What Jev sees, and what it costs

Each request sends only text: your prompt, the assistant's answer (for Claude Code, all text blocks of the turn), the previous two exchanges as context, and the elapsed time. Jev does **not** see file changes, tool calls or their output, the model's reasoning, or images. So a claim like "tests pass" without the output pasted in may be flagged as unverified.

Jev charges per input token, about 2,000 tokens per answer, which is roughly US$0.0001 at the published rate of $0.042 per million.

**Privacy:** your prompts and the assistant's answers leave your machine and go to Typesafe's API. Do not use iqdrop on conversations you are not allowed to share with a third party.

## Limits

- The scores are proxies from another model, not a measurement of intelligence. Treat single scores as signals; trends matter more.
- Scores depend on task difficulty, so one low score does not prove the model got worse.
- Scoring adds up to ~25 s after each answer while the hook waits for Jev. If Jev fails or times out, the answer is left alone and the line says why (⚪ not scored).

## Roadmap

- Trend alerts: keep a per-model baseline and warn when scores drift down over time.
- Optional tool-call summaries so Jev can see verification that happened outside the answer text.

## Related projects

[NerfWatch](https://github.com/tendaigomo/NerfWatch) and [nerfwatch](https://github.com/lukejacobsen7/nerfwatch) track model degradation with repeated probes and statistical alarms. iqdrop instead grades your real conversations as they happen, and says what went wrong in each one.

## License

MIT. Not affiliated with OpenAI, Anthropic or Typesafe.
