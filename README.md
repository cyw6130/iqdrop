# iqdrop

**English** · [简体中文](README.zh-CN.md)

Catch silent quality drops in your coding agent. iqdrop hooks into **Codex** and **Claude Code**, sends every answer to an independent judge model ([Jev](https://docs.typesafe.ai) by Typesafe), and shows the verdict right under the answer:

```
🟢 Answer IQ: 74.2/100 · Understanding: 95.8/100 · Speed normal · Jev checks: no clear problems.
🔴 Answer IQ: 47.8/100 · Understanding: 84.8/100 · Speed normal · Jev checks: unverified claims (84%); factual or reasoning error (69%).
```

It grades the work you are actually doing, turn by turn, instead of a fixed benchmark. When the answers you get start scoring lower, you see it as it happens, not days later.

## What it checks

For every answer, Jev returns:

| Item | Meaning |
|---|---|
| **Answer IQ** (0–100) | Graded with the rubric that fits the reply (see below) |
| **Understanding** (0–100) | How well the answer grasped the goal, scope, constraints and implied intent |
| **Speed** | Whether the wall-clock time was reasonable for the task |
| **Checks** | Yes/no diagnostics: factual or reasoning error, unverified claims, incomplete delivery, broke an explicit constraint, off target, stopped needlessly |

Jev first classifies each reply, and Answer IQ uses the rubric that fits it. All three scores are kept in the record.

| Reply kind | What Answer IQ grades |
|---|---|
| Final answer | The delivered result: correct, complete, usable, verified |
| Mid-task progress report | Orchestration: sensible split, suitable workers (sub-agents, other models, background jobs), parallel where independent, waiting time used, clear instructions and acceptance checks for delegated work, accurate status, a plan to verify results |
| Checkpoint (asks you before continuing) | Whether the question or plan is well posed, comes with a clear recommendation, and whether pausing was the right call |

Asking before acting is often correct, and a progress report is not a failed delivery, so neither is graded against the final result. Jev only sees text, so orchestration is judged from what the report says was dispatched.

A check is shown when Jev puts its probability at or above the threshold (50% by default; 70% for "stopped needlessly", which is partly a matter of taste). "Incomplete delivery" and "unverified claims" are only shown for final answers; "stopped needlessly" only for the others.

A red light means Answer IQ is below 60.

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
| `IQDROP_NOTIFY` | `0` | `1` also posts a macOS notification; `codex` or `claude` limits it to one client |
| `IQDROP_DATA_DIR` | `~/.iqdrop` | Where score records are kept |

## How has the model been doing lately?

```bash
iqdrop stats --client codex --hours 3
```

```
gpt-6-astra · last 3 h · 19 scored answers (final 5 / checkpoint 14)

Answer IQ: 78.1 (+4.1 vs baseline, same reply kinds)
  final answers only: 55.7 (+0.8 vs baseline, same reply kinds)
Understanding: 88.2 (+0.9 vs baseline, same reply kinds)
red lights: 3/19
Baseline, previous 7 days: Answer IQ 61.7 · Understanding 86.4 · n=326
```

It reports the model behind the latest answer (`--model` to pick another), compares it with the same model's previous 7 days (`--baseline-days`), and lists the most frequent problems and the lowest-scored answers. The comparison is made reply kind by reply kind, so a stretch with more checkpoints, which score higher, does not look like an improvement. `--json` gives raw numbers.

To ask the agent directly ("how smart have you been in the last 3 hours?"), install the skill:

```bash
iqdrop install-skill codex     # or claude / all
```

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

- Trend alerts: warn automatically when a model drifts below its baseline (`iqdrop stats` already computes the comparison on demand).
- Optional tool-call summaries so Jev can see verification that happened outside the answer text.

## Related projects

[NerfWatch](https://github.com/tendaigomo/NerfWatch) and [nerfwatch](https://github.com/lukejacobsen7/nerfwatch) track model degradation with repeated probes and statistical alarms. iqdrop instead grades your real conversations as they happen, and says what went wrong in each one.

## License

MIT. Not affiliated with OpenAI, Anthropic or Typesafe.
