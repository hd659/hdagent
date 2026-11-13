# hdagent

Digital Self Kernel & Parallel Clone Engine built on headless `Pi` sessions.

`hdagent` continuously learns how its operator thinks, decides, and acts across multiple coding agents (`Claude Code`, `Antigravity`, `Pi`, `Codex`) and thought diaries, enabling parallelized self-execution across progressive autonomy tiers (`L1_sandbox` -> `L2_confirm` -> `L3_auto`).

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full 4-layer design.

## Core Modules

1. **Cross-Harness Signal Collector (`loop_engineer/collector.py`)**
   Zero-token local polling across Claude Code, Antigravity, Pi, Codex, and thought diaries with noise/support-ticket/privacy filtering.
2. **Digital Self Kernel (`loop_engineer/self_core.py`)**
   Incremental cursor-based learning (`self_core.json`) capturing decision principles, redlines, active intents, repeatable playbooks (`L1 / L2 / L3`), and authentic phrasing rhythm.
3. **Zero-Leak Privacy Gate (`loop_engineer/privacy.py`)**
   Structural regexes + gitignored `.state/private_denylist.json` preventing credentials, personal identifiers, or private endpoints from entering prompts or commits.
4. **Subtext Planner & Clone Dispatcher (`loop_engineer/planner.py`, `loop_engineer/daemon.py`)**
   Infers high-leverage projects via hidden `--no-session` synthesis (`claude-opus-5-5`, `thinking=high`) and executes them in clean natural-voice Pi sessions with Super-Agent summaries.

## Quickstart

```bash
# 1. Run test suite
pytest -q

# 2. Inspect learned Digital Self Kernel
python3 hdagent.py profile

# 3. Distill newly accumulated cross-agent conversations into SelfCore
python3 hdagent.py learn --force

# 4. Poll signals & inspect status (0 LLM tokens)
python3 hdagent.py status

# 5. Start detached background daemon
python3 hdagent.py start-daemon --interval 1800
```
