# CCB 5 分钟上手

从零到「发出第一个跨 agent 任务并看到回复」的最短线性路径。命令与配置键保持英文，叙述为中文。
深入用法见完整[用户手册](manuals/user-guide/)。

---

## 1. 安装

推荐用 npm 包安装，之后用 CCB 自带的 updater 升级：

```bash
npm install -g @seemseam/ccb
ccb update          # 安装后用它升级
```

> npm 不可用时，从 [Releases](https://github.com/SeemSeam/claude_codex_bridge/releases) 下载包
> 解压后 `./install.sh install`；或源码安装（开发/临时）：
> `git clone … && cd claude_codex_bridge && ./install.sh install`。

## 2. 进入项目，建 anchor

CCB 以项目为单位运行，项目由根目录下的 `.ccb` 标识：

```bash
cd /path/to/your-project
mkdir -p .ccb          # 若 ccb 启动时提示无法自动创建 anchor，手动建一次即可
```

## 3. 写最小配置 `.ccb/ccb.config`

一个能跑起来的最小团队 —— 一个主 agent（codex）+ 一个 reviewer（claude）：

```toml
version = 2
entry_window = "main"

[windows]
main = "main:codex, reviewer:claude"
```

要点：`[windows]` 定义 tmux 窗口与 agent 分组；`agent:provider` 决定每个 agent 用哪个 CLI；
给 agent 加 `(worktree)` 可让它独占一个 git worktree。
**不想手写？** 直接问内置自助 agent：`ccb ask ccb_self "帮我设计一个 Python 库的团队配置"`，
它会用 `ccb-config` skill 提案并在你确认后才写入 `.ccb/ccb.config`。

## 4. 校验配置

```bash
ccb config validate     # 看 config_source_kind 是否为你预期的那一层（项目级最高优先）
```

## 5. 启动工作台

```bash
ccb                     # daemon 未起会自动拉起、挂载 agents、铺好 tmux 前台
```

进入后：鼠标点击切换窗口/agent/pane；`Ctrl-b h/j/k/l` 切相邻 pane，`Ctrl-b z` 放大/还原当前 pane。

## 6. 发出第一个任务

在某个 agent 的 pane 里直接输入：

```text
/ask reviewer review the latest changes and list blocking issues.
```

或在任意终端用命令行路由：

```bash
ccb ask reviewer review latest diff
ccb ask --compact reviewer review latest diff   # 请求精简回复
```

> 在一个 active CCB 任务内部再发 ask（嵌套），必须带 `--callback` 或 `--silence`。

## 7. 看回复 / 排查

```bash
ccb watch reviewer        # 轮询该 agent/job 事件直到结束或超时
ccb inbox reviewer        # 看 inbox head 和待处理项
ccb trace <id>            # 用任意 submission/message/attempt/reply/job id 重建整条链路
ccb ack reviewer          # 确认 inbox head 上的 reply
```

## 8. 改了配置怎么热更

```bash
ccb reload --dry-run      # 先预览变更计划（不执行）
ccb reload                # 应用：可动态加 agent/窗口、卸载空闲 agent；不安全的改动会被拒绝且不杀现有 pane
```

## 9. 停止 / 卸载

```bash
ccb kill                  # 停后台 backend 和所有 configured agents
ccb uninstall             # 卸载 CCB
```

---

## 卡住了？

- `ccb doctor` —— 常规诊断；`ccb doctor --output` 导出诊断 bundle。
- `ccb ask ccb_self "…"` —— CCB 的自助 agent，能解释当前布局、设计/迁移配置、诊断运行态、修复工作流。
- 完整命令表、配置语法、协作工作流、FAQ、recipes：[用户手册](manuals/user-guide/)（`cd manuals/user-guide && make` 出 PDF）。
