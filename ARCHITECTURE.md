# hdagent Architecture Blueprint

## 1. Core Thesis: Self-Concurrency

When daily engineering, operations, and research happen through conversations with AI agents, execution hands are no longer the bottleneck. The bottleneck is the single-threaded human operator reading state, weighing trade-offs, and issuing instructions one window at a time.

`hdagent` extracts and continuously updates that operator layer ("Digital Self Kernel") from cross-agent traces so multiple instances of the digital self can run in parallel on top of headless `Pi` sessions.

## 2. Four-Layer System Design

```text
[Claude Code]   [Antigravity]   [Pi Sessions]   [Codex CLI]   [Thought Diaries]
      \               \               |               /               /
       +---------------+--------------+--------------+---------------+
                                      |
                        (0-Token Local Collector + PrivacyGate)
                                      v
+-----------------------------------------------------------------------------+
| Layer 1: Digital Self Kernel (`loop_engineer/self_core.py`)                 |
|  - Incremental cursor (`learned_signal_ids`) — never re-learns old chats    |
|  - `decision_principles` & `redlines` (Decision Function)                   |
|  - `active_intents` & `workspace_focus` (Attention Graph)                   |
|  - `playbooks` (Repeatable workflows + L1/L2/L3 tier)                       |
|  - `voice_notes` & `authentic_utterances` (Natural phrasing reservoir)      |
+-----------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
| Layer 2: Autonomy & Permission Gate                                         |
|  - L1_sandbox : Build/verify in isolated workspace first (0 external risk)  |
|  - L2_confirm : Draft cloud/external/GUI proposal -> wait for 1-click OK    |
|  - L3_auto    : Pre-verified repeatable playbook -> autonomous + audit log  |
+-----------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
| Layer 3: Parallel Clone Dispatcher (`loop_engineer/daemon.py` on Pi CLI)    |
|  - Hidden Clone #0 (`--no-session`): Infers intent & speaks as Digital Self |
|  - Visible Clone #1..N (`--session-dir`): Clean natural dialog + delivery   |
+-----------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
| Layer 4: Progressive Execution Hands                                        |
|  - Stage 1 (v0.1 Live): Local isolated code/tool synthesis + pytest + Git   |
|  - Stage 2 (Next)     : 24/7 Linux VPS daemon (mail, gateway, cron, APIs)   |
|  - Stage 3 (Future)   : Computer Use (browser/desktop GUI mouse & keyboard) |
+-----------------------------------------------------------------------------+
```

## 3. Privacy & Safety Invariants

1. `.state/` (`self_core.json`, `private_denylist.json`, `approval_queue.json`, `backlog.json`) is strictly gitignored and never leaves local storage.
2. Every signal and every staged file passes through `PrivacyGate` before entering prompts or Git commits.
3. Background clones are hard-blocked from mutating live production service directories or creating `.github/workflows/*` without explicit authorization.
