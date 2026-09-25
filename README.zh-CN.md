# iqdrop

[English](README.md) · **简体中文**

及时发现编程助手"偷偷降智"。iqdrop 以钩子的方式接入 **Codex** 和 **Claude Code**，把每一条回答交给独立的评审模型（Typesafe 的 [Jev](https://docs.typesafe.ai)）打分，结果直接显示在回答下方：

```
🟢 回答智商分：74.2/100 · 理解度：95.8/100 · 速度正常 · Jev 检查：未发现明显问题。
🔴 回答智商分：47.8/100 · 理解度：84.8/100 · 速度正常 · Jev 检查：缺少验证证据(84%)；事实或推理错误(69%)。
⏸ 待你确认 · 理解度：79.5/100 · 速度正常 · Jev 检查：未发现明显问题。
```

它评的是你手头的真实工作，每一轮都评，而不是跑一套固定的测试题。回答质量一旦开始下滑，你当场就能看到，不用等到几天后才察觉。

## 评什么

每条回答，Jev 会给出：

| 项目 | 含义 |
|---|---|
| **回答智商分**（0–100） | 交付结果的质量：是否正确、完整、可用、有验证 |
| **理解度**（0–100） | 是否准确把握了目标、范围、约束和隐含意图 |
| **速度** | 耗时与任务复杂度是否相称 |
| **回复类型** | 最终回答、进度汇报，或待你确认（继续之前先问你） |
| **检查项** | 是/否诊断：事实或推理错误、缺少验证证据、交付不完整、违反明确约束、偏离目标、不必要的停顿 |

Jev 判断某项为"是"的概率达到门槛（默认 50%）时才会显示。"不必要的停顿"带有主观成分，门槛单独设为 70%。进度汇报和"待你确认"的回复不给回答智商分：这个分数的评分标准针对的是交付结果，而动手前先确认往往本来就是对的做法。

最终回答的智商分低于 60 时亮红灯。

## 安装

需要 Python 3.9+ 和 Typesafe 的 API 密钥（[docs.typesafe.ai](https://docs.typesafe.ai)），不依赖任何第三方包。

```bash
pipx install git+https://github.com/cyw6130/iqdrop
iqdrop set-key          # 密钥存到 ~/.config/iqdrop/config.env（权限 600）
iqdrop set-lang zh      # 评分行显示中文
iqdrop install all      # 或 iqdrop install codex / iqdrop install claude
```

也可以克隆仓库后运行 `python3 -m iqdrop install all`。

安装器会把两个钩子（UserPromptSubmit 和 Stop）合并进 `~/.codex/hooks.json` 和/或 `~/.claude/settings.json`，保留你原有的钩子，写入前先备份（`*.bak-iqdrop`）。重复安装不会产生重复条目。

**Codex 用户**：安装后打开 设置 → 钩子，把两个新钩子标记为可信。在此之前 Codex 不会运行它们。

`iqdrop uninstall all` 只移除 iqdrop 自己的条目。

## 配置

`~/.config/iqdrop/config.env`（同名环境变量优先）：

| 键 | 默认值 | 含义 |
|---|---|---|
| `TYPESAFE_API_KEY` | – | Jev 密钥 |
| `IQDROP_LANG` | `en` | 评分行语言：`en` 或 `zh` |
| `IQDROP_CHECK_THRESHOLD` | `0.5` | 检查项的显示门槛 |
| `IQDROP_ALERT_BELOW` | `60` | 智商分低于此值亮红灯 |
| `IQDROP_NOTIFY` | `0` | 设为 `1` 时同时弹出 macOS 通知 |
| `IQDROP_DATA_DIR` | `~/.iqdrop` | 评分记录的存放位置 |

## 查看评分依据

每次评分都以 JSON 保存在 `~/.iqdrop/<codex|claude>/scores/<会话>/` 下，包含 Jev 的完整概率分布、各检查项概率、token 用量、提问和回答。

```bash
iqdrop explain --client claude --list     # 最近一个会话里评过的回答
iqdrop explain --client codex <id>        # 查看某一条的完整记录
```

## Jev 能看到什么、花多少钱

每次请求只发送文本：你的提问、助手的回答（Claude Code 取这一轮所有文字段）、前两轮问答作为上下文，以及耗时。Jev **看不到**文件改动、工具调用及其输出、模型的思考过程和图片。所以回答里只写"测试通过"而没贴出结果时，可能会被判"缺少验证证据"。

Jev 按输入 token 计费，每条回答约 2000 token。按官方价格每百万 token 0.042 美元计算，约合 0.0001 美元。

**隐私**：你的提问和助手的回答会离开本机，发送到 Typesafe 的接口。不能与第三方共享的对话，请不要启用 iqdrop。

## 局限

- 分数是另一个模型给出的代理指标，不是在测量智力。单次分数只能当作信号，长期趋势更有意义。
- 分数受任务难度影响，一次低分不能证明模型变差了。
- 每条回答结束后，钩子要等 Jev 返回，最多多等约 25 秒。Jev 出错或超时不会影响回答本身，评分行会说明原因（⚪ 未评分）。

## 计划

- 趋势报警：按模型保存基线，分数持续下滑时提醒。
- 可选地附上工具调用摘要，让 Jev 看到回答文字之外的验证过程。

## 相关项目

[NerfWatch](https://github.com/tendaigomo/NerfWatch) 和 [nerfwatch](https://github.com/lukejacobsen7/nerfwatch) 通过反复探测和统计报警来追踪模型退化。iqdrop 则是在你的真实对话发生时就逐条评分，并指出每一条具体哪里出了问题。

## 许可证

MIT。与 OpenAI、Anthropic、Typesafe 均无关联。
