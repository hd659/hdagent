"""
Autonomous Loop Daemon & Pi Agent (`claude-opus-5-5`, `thinking=high`) Dispatcher.

Architecture:
- Lightweight Python daemon polls cross-agent conversations & thought diaries with 0 idle token cost
  and 0 session clutter.
- When dispatching (within daily work window up to `daily_quota=2`, or immediately via `loop.py trigger`),
  if no pending project exists, silently invokes `claude-opus-5-5` (`--thinking high --no-session`)
  to infer 1 high-value, genuinely useful project from the subtext of Haodong's multi-agent chats.
- Executes the project in a clean Pi session (`--session-dir ~/.pi/agent/sessions/--<home>-Desktop-project--`)
  where:
  * Sidebar title (`--name`) = clear Chinese project title (`猜你想做 · ...`)
  * Message #1 (User) = natural first-person prompt written in Haodong's own voice
  * Hidden `--append-system-prompt` = all engineering, privacy, pytest, and GitHub push mechanics
  * Final Message (Assistant) = Super Agent style 3-part Chinese summary (what need was inferred,
    what was built & how to run it, local path + GitHub URL).
"""

import json
import os
import re
import subprocess
import time
from typing import Dict, List, Optional

from .collector import ConversationCollector, EngineeringSignal
from .github_sync import GitHubSyncManager
from .planner import CommitMilestone, PlannedProject, WeeklyPlanner

HOME_DIR = os.path.expanduser("~")
PI_BIN = f"{HOME_DIR}/.npm-global/bin/pi"
DEFAULT_PI_MODEL = "local-gateway/claude-opus-5-5"
DEFAULT_THINKING = "high"
DEFAULT_DAILY_QUOTA = 2  # 1~2 high-completeness projects/major features per day
WORK_WINDOW = (1, 6)  # Local hours [01:00, 06:00)
LAST_START_MARGIN_MIN = 30
MILESTONE_TIMEOUT_S = 3600


def in_work_window(hour: Optional[int] = None) -> bool:
    h = time.localtime().tm_hour if hour is None else hour
    return WORK_WINDOW[0] <= h < WORK_WINDOW[1]


def can_start_milestone(now: Optional[time.struct_time] = None) -> bool:
    t = now or time.localtime()
    if not in_work_window(t.tm_hour):
        return False
    minutes_left = (WORK_WINDOW[1] - t.tm_hour) * 60 - t.tm_min
    return minutes_left >= LAST_START_MARGIN_MIN


class LoopDaemon:
    def __init__(
        self,
        root_dir: str = f"{HOME_DIR}/Desktop/project",
        state_dir: str = f"{HOME_DIR}/Desktop/project/.state",
        pi_model: str = DEFAULT_PI_MODEL,
        thinking_level: str = DEFAULT_THINKING,
        daily_quota: int = DEFAULT_DAILY_QUOTA,
    ):
        self.root_dir = root_dir
        self.state_dir = state_dir
        # Normalize legacy `-high` model suffix if passed by old scripts
        if pi_model.endswith("-high"):
            pi_model = pi_model[: -len("-high")]
        self.pi_model = pi_model
        self.thinking_level = thinking_level
        self.daily_quota = max(0, int(daily_quota))
        self.pid_file = os.path.join(self.state_dir, "daemon.pid")
        self.runner_pid_file = os.path.join(self.state_dir, "runner.pid")
        self.log_file = os.path.join(self.state_dir, "daemon.log")
        self.status_file = os.path.join(self.state_dir, "daemon_status.json")
        self.dispatch_state_file = os.path.join(self.state_dir, "dispatch_state.json")
        self.pi_runs_dir = os.path.join(self.state_dir, "pi_runs")
        self.collector = ConversationCollector()
        self.planner = WeeklyPlanner(state_dir=self.state_dir)
        self.git_sync = GitHubSyncManager(root_dir=self.root_dir, state_dir=self.state_dir)

    def log(self, message: str) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def _load_dispatch_state(self) -> Dict:
        if os.path.exists(self.dispatch_state_file):
            try:
                with open(self.dispatch_state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "daily_dispatch_counts" not in data:
                    data["daily_dispatch_counts"] = {}
                return data
            except Exception:
                pass
        return {
            "engine": "pi",
            "model": self.pi_model,
            "thinking": self.thinking_level,
            "last_dispatch_date": "",
            "daily_dispatch_counts": {},
            "active_milestone": None,
            "dispatched_milestones": {},
        }

    def _save_dispatch_state(self, state: Dict) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        tmp = self.dispatch_state_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.dispatch_state_file)

    @staticmethod
    def _select_diverse_signal_digest(signals: List[EngineeringSignal]) -> str:
        """Build a balanced 3-bucket view across raw chats, non-gateway workspaces, and thought diaries."""
        chat_types = {"claude_session", "pi_session", "agy_transcript", "codex_session"}
        recent_chats = [s for s in signals if s.source_type in chat_types][:14]
        used_ids = {s.signal_id for s in recent_chats}

        cross_domain = [
            s
            for s in signals
            if s.signal_id not in used_ids
            and (
                any(tag in s.title.lower() for tag in ("colab", "convibe", "netmap", "codex", "/cs]"))
                or s.pillar != "ai-infra-harness"
            )
            and s.source_type != "thought_diary"
        ][:8]
        used_ids.update(s.signal_id for s in cross_domain)

        diaries = [s for s in signals if s.source_type == "thought_diary"][:6]

        def fmt(items: List[EngineeringSignal]) -> str:
            if not items:
                return "  (暂无)"
            return "\n".join(
                f"  - [{s.date}] ({s.source_type} | {s.pillar}) {s.title} —— {s.summary[:220]}"
                for s in items
            )

        return (
            "【A. 最近四端（Claude / Antigravity / Pi / Codex）真实用户原话】\n"
            + fmt(recent_chats)
            + "\n\n【B. 跨工作区探索（Colab 视频蒸馏 / Convibe 音频 / 课程算法 / 网络工具）】\n"
            + fmt(cross_domain)
            + "\n\n【C. 思考日记与产品/认知洞察】\n"
            + fmt(diaries)
        )

    def synthesize_milestones_via_pi(self, signals: List[EngineeringSignal]) -> List[str]:
        """
        Silently invoke Pi (`claude-opus-5-5`, `--thinking high --no-session`) to infer 1 genuinely
        useful, high-completeness project from the subtext of Haodong's cross-agent conversations.
        Never writes a session file into Pi Client's CHATS list.
        """
        if not signals:
            return []
        projects = self.planner.load_or_init_projects()
        existing_repos = [f"- {p.repo_name}: {p.tagline}" for p in projects]
        recent_repos = self.planner.recent_completed_repos(limit=3)
        signal_digest = self._select_diverse_signal_digest(signals)

        synth_prompt = (
            "你是用户的私人产品合伙人与总架构师。请仔细阅读用户在 Claude Code、Antigravity、Pi、Codex 四端与其他 Agent 的真实对话原话以及思考日记，"
            "从中**揣摩用户的潜台词，猜测他内心真正想做、用得上、或者平时反复手动折腾却还没做成独立工具的 1 个新项目**。\n\n"
            "【硬性选题铁律（违反任意一条即为失败）】\n"
            "1. 猜潜台词，绝不炒冷饭：严禁把已经修完的线上小 Bug、前端按钮删改、客户售后问题拆成无聊的 `*-linter`、`*-guard`、`*-auditor` 补丁库！\n"
            f"2. 严禁碰 `frictionlab`、`loop-engineer` 或线上生产目录 `{HOME_DIR}/Desktop/cs/api`。\n"
            f"3. 优先孵化全新独立、完整好用的实用工具或原型产品（`mode: extrapolate_new`，存放在 `{HOME_DIR}/Desktop/project/workspaces/<repo_name>`），与下方已有仓库不重复。\n"
            "4. 重质不重量：只设计 **1 个** 新项目，包含 **1 个** 一步到位、完整度高、带 CLI 命令行（或轻量本地 Web 界面）+ 核心引擎 + 完整 `README.md` + `pytest` 单元测试的 Milestone（约 4~6 个精炼文件，跑完就能直接用）。\n"
            "5. 必须同时写出：\n"
            "   - `chat_title`：显示在左侧列表的清晰中文标题，格式严格为 `猜你想做 · <8~14字直白中文名> (<repo_name>)`；\n"
            "   - `user_voice_prompt`：完全模仿用户本人平时跟 Agent 说话的**第一人称口吻**（自然平实、直奔主题，用“我最近在……发现/总要手动……帮我做一个……”的真实语气，严禁出现 Milestone 编号、JSON、pytest 命令或机器黑话，120~240 字，让人一眼看懂需求是什么）。\n\n"
            f"最近刚做过的仓库（请换新方向）：{recent_repos}\n"
            "已有历史仓库（避免撞题）：\n"
            + "\n".join(existing_repos)
            + "\n\n"
            + signal_digest
            + "\n\n请严格只输出一个 ```json ... ``` 代码块（数组内含 1 个项目对象）：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "repo_name": "short-kebab-name",\n'
            '    "pillar": "ai-infra-harness | workflow-mcp | quant-fintech-web3 | cognitive-systems",\n'
            '    "mode": "extrapolate_new",\n'
            f'    "local_target_dir": "{HOME_DIR}/Desktop/project/workspaces/short-kebab-name",\n'
            '    "tagline": "Concise English GitHub repo description (under 110 chars).",\n'
            '    "origin_context": "用中文直白说明：从哪几条真实跨端对话/思考日记推导出用户有这个潜在需求。",\n'
            '    "tech_stack": ["Python", "PyTest"],\n'
            '    "chat_title": "猜你想做 · 直白中文项目名 (short-kebab-name)",\n'
            '    "user_voice_prompt": "我最近在...每次都要手动...帮我做一个...写完测通推到我的 GitHub 上。",\n'
            '    "milestones": [\n'
            "      {\n"
            '        "milestone_id": "skn-m1",\n'
            '        "commit_type": "feat",\n'
            '        "scope": "mvp",\n'
            '        "summary": "build complete MVP engine, CLI/UI, docs, and test suite",\n'
            '        "chat_title": "猜你想做 · 直白中文项目名 (short-kebab-name)",\n'
            '        "user_voice_prompt": "我最近在...每次都要手动...帮我做一个...写完测通推到我的 GitHub 上。",\n'
            '        "deliverables": ["pkg/__init__.py", "pkg/core.py", "pkg/cli.py", "tests/test_core.py", "README.md"]\n'
            "      }\n"
            "    ]\n"
            "  }\n"
            "]\n"
            "```"
        )
        env = dict(os.environ)
        env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{HOME_DIR}/.npm-global/bin:/opt/anaconda3/bin:{env.get('PATH', '')}"
        cmd = [
            PI_BIN,
            "--print",
            "--no-session",
            "--no-context-files",
            "--model",
            self.pi_model,
            "--thinking",
            self.thinking_level,
            "--no-mcp",
            "--no-tools",
            "--",
            synth_prompt,
        ]
        try:
            self.log(
                f"Synthesizing project from {len(signals)} cross-agent signals via Pi "
                f"({self.pi_model}, thinking={self.thinking_level}, --no-session)..."
            )
            proc = subprocess.run(cmd, cwd=self.root_dir, env=env, capture_output=True, text=True, timeout=360)
            out = proc.stdout or ""
            match = re.search(r"```json\s*(\[.*?\])\s*```", out, re.DOTALL)
            raw_json = match.group(1) if match else out.strip()
            items = json.loads(raw_json)
            if isinstance(items, list):
                added = self.planner.merge_llm_synthesized_plan(items)
                self.log(f"Synthesized {len(added)} new milestone(s) via Pi: {added}")
                return added
        except Exception as exc:
            self.log(f"Pi synthesis failed ({exc}).")
        return []

    def build_milestone_user_prompt(self, project: PlannedProject, milestone: CommitMilestone) -> str:
        """
        Return ONLY the clean, natural first-person user prompt that appears as Message #1
        inside the Pi Client chat dialog.
        """
        if milestone.user_voice_prompt and milestone.user_voice_prompt.strip():
            return milestone.user_voice_prompt.strip()
        return (
            f"我最近在日常工作流里注意到：{project.origin_context} "
            f"帮我在本地 `{project.local_target_dir}` 做一个叫 `{project.repo_name}` 的工具（{project.tagline}），"
            f"把核心功能（{milestone.summary}）、命令行入口、说明文档和单元测试一次写完整，跑通测试后直接推到我的 GitHub 上，"
            f"最后用人话跟我汇报一下你猜到的需求背景、实际做出了什么功能、怎么运行体验以及仓库地址。"
        )

    def build_milestone_system_prompt(self, project: PlannedProject, milestone: CommitMilestone) -> str:
        """
        Hidden execution harness appended to system prompt (`--append-system-prompt`).
        Keeps machine mechanics out of the visible User bubble while guaranteeing deterministic
        testing, privacy checks, GitHub push, and a Super-Agent-style Chinese final summary.
        """
        return (
            "[LOOP ENGINEER HIDDEN EXECUTION HARNESS]\n"
            "你正在执行一个「根据用户跨端对话潜台词自动孵化项目」的完整交付任务。\n"
            "严禁读写 Obsidian Vault（严禁修改 `recent-conversations.md`），严禁在正文中使用任何 Emoji 或 LaTeX 公式。\n\n"
            "## 1. 目标项目与交付规格\n"
            f"- 仓库名：`{project.repo_name}`\n"
            f"- 本地工作目录：`{project.local_target_dir}`\n"
            f"- GitHub 描述：{project.tagline}\n"
            f"- 潜台词推导来源：{project.origin_context}\n"
            f"- 技术栈：{', '.join(project.tech_stack)}\n"
            f"- Milestone ID：`{milestone.milestone_id}`\n"
            f"- 交付文件清单：`{', '.join(milestone.deliverables)}`（可按需补充必要辅助文件，但严禁创建 `.github/workflows/` 文件）\n\n"
            "## 2. 编码、测试与隐私门闩硬规则\n"
            "1. **零隐私泄漏**：所有源码、测试样本与 `README.md` 严禁出现真实邮箱、学号、真实 API Key、私人域名、局域网/VPS 真实 IP 或客户标识（一律用 `example.com` / 虚拟 mock 数据）。\n"
            "2. **模块化精炼编码**：每个文件保持高内聚（控制在 `80~220` 行以内），**每轮只调用 1 次 `write` 工具写 1 个文件**，避免单次超长输出截断；项目必须真正能运行、有实际效用（含清晰的 CLI 命令或本地演示入口，不要写成空壳玩具）。\n"
            f"3. **单元测试验证**：写完代码后，在 `{project.local_target_dir}` 下通过 `bash` 运行 `/opt/anaconda3/bin/python3 -m pytest -q`，确保 100% 通过。\n"
            "4. **Git 提交与推送 GitHub (`hd659`)**：测试全绿后，通过 `bash` 运行以下 Python 脚本完成隐私扫描、提交、自动建库推送与状态标记：\n"
            "```bash\n"
            "/opt/anaconda3/bin/python3 - <<'PY'\n"
            "import os, time, sys\n"
            f"sys.path.insert(0, {self.root_dir!r})\n"
            "from loop_engineer.github_sync import GitHubSyncManager\n"
            "from loop_engineer.planner import WeeklyPlanner\n"
            f"repo_dir = {project.local_target_dir!r}\n"
            "sync = GitHubSyncManager()\n"
            "sync.ensure_git_repo(repo_dir)\n"
            "all_files = []\n"
            "for root, dirs, files in os.walk(repo_dir):\n"
            "    dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.pytest_cache', '.venv')]\n"
            "    for fn in files:\n"
            "        all_files.append(os.path.relpath(os.path.join(root, fn), repo_dir))\n"
            f"ok, rev = sync.commit_files(repo_dir, all_files, '{milestone.commit_type}({milestone.scope}): {milestone.summary}')\n"
            f"ok_push, msg = sync.push_or_create_remote(repo_dir, '{project.repo_name}', {project.tagline!r})\n"
            "if ok and ok_push:\n"
            f"    WeeklyPlanner().mark_milestone_completed('{milestone.milestone_id}', time.strftime('%Y-%m-%dT%H:%M:%S%z'))\n"
            "print('COMMIT:', ok, rev, 'PUSH:', ok_push, msg)\n"
            "PY\n"
            "```\n\n"
            "## 3. 最终回复格式（必须像 Super Agent 汇报一样清晰易读）\n"
            "完成推送后，你的**最后一条回复**是直接给用户本人看的成果总结。严禁堆砌晦涩代码术语或底层脚本输出，必须用清晰直白的简体中文严格输出以下三节（不使用 Emoji、不使用 LaTeX）：\n\n"
            "### 1. 我猜你的需求是什么\n"
            "- **灵感来源**：用人话说明从你最近哪几场对话/折腾的事情里看出了这个潜在痛点或兴趣。\n"
            "- **解决什么问题**：直白讲清楚这个工具能帮你省掉什么麻烦、有什么实际用处。\n\n"
            "### 2. 这次实际做成了什么\n"
            "- **核心功能**：分 3~4 点用大白话讲清楚已经做好的能力。\n"
            "- **一行命令直接体验**：给出一条在终端直接复制就能跑起来的命令（例如 `python3 -m ...`）以及运行后会看到的效果。\n\n"
            "### 3. 保存位置与 GitHub 仓库\n"
            f"- **本地项目路径**：`{project.local_target_dir}`\n"
            f"- **GitHub 仓库**：`https://github.com/hd659/{project.repo_name}`（附上本次 Commit 短哈希）\n"
            "- **测试与脱敏校验**：写明 `pytest` 通过用例数及隐私安全检查已通过。"
        )

    def build_milestone_prompt(self, project: PlannedProject, milestone: CommitMilestone) -> str:
        """Backward-compatible alias returning the user-facing natural prompt."""
        return self.build_milestone_user_prompt(project, milestone)

    def dispatch_next_milestone_to_model(self, force: bool = False, repo_name: Optional[str] = None) -> Dict:
        """Invoke Pi Agent (`claude-opus-5-5`, `--thinking high`) to build & ship the next inferred project."""
        today = time.strftime("%Y-%m-%d")
        dstate = self._load_dispatch_state()
        daily_counts = dstate.get("daily_dispatch_counts") or {}
        today_count = int(daily_counts.get(today, 0))
        if not force and self.daily_quota and today_count >= self.daily_quota:
            return {
                "dispatched": False,
                "reason": f"Daily quota reached ({today_count}/{self.daily_quota}) for {today}. Use --force to run now.",
            }

        next_item = self.planner.next_actionable_milestone(repo_name=repo_name)
        if not next_item:
            signals = self.collector.collect_all()
            self.synthesize_milestones_via_pi(signals)
            next_item = self.planner.next_actionable_milestone(repo_name=repo_name)
        if not next_item:
            return {"dispatched": False, "reason": "No actionable milestone synthesized or pending."}

        proj: PlannedProject = next_item["project"]
        ms: CommitMilestone = next_item["milestone"]
        os.makedirs(proj.local_target_dir, exist_ok=True)
        os.makedirs(self.pi_runs_dir, exist_ok=True)

        title = (ms.chat_title or f"猜你想做 · {proj.repo_name}").strip()
        user_prompt = self.build_milestone_user_prompt(proj, ms)
        sys_prompt = self.build_milestone_system_prompt(proj, ms)
        run_log_path = os.path.join(self.pi_runs_dir, f"{ms.milestone_id}.log")

        env = dict(os.environ)
        env["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{HOME_DIR}/.npm-global/bin:/opt/anaconda3/bin:{env.get('PATH', '')}"

        home_slug = HOME_DIR.strip("/").replace("/", "-")
        project_session_dir = os.path.join(HOME_DIR, ".pi", "agent", "sessions", f"--{home_slug}-Desktop-project--")
        os.makedirs(project_session_dir, exist_ok=True)

        cmd = [
            PI_BIN,
            "--print",
            "--no-context-files",
            "--model",
            self.pi_model,
            "--thinking",
            self.thinking_level,
            "--no-mcp",
            "--session-dir",
            project_session_dir,
            "--name",
            title,
            "--append-system-prompt",
            sys_prompt,
            "--",
            user_prompt,
        ]

        dstate["active_milestone"] = {
            "milestone_id": ms.milestone_id,
            "repo_name": proj.repo_name,
            "chat_title": title,
            "model": self.pi_model,
            "thinking": self.thinking_level,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "log_file": run_log_path,
        }
        self._save_dispatch_state(dstate)
        self.log(
            f"Launching Pi ({self.pi_model}, thinking={self.thinking_level}) "
            f"for {proj.repo_name} :: {ms.milestone_id} ({title}) -> {run_log_path}"
        )

        with open(run_log_path, "w", encoding="utf-8") as log_f:
            log_f.write(f"=== {title} | model={self.pi_model} | thinking={self.thinking_level} ===\n\n")
            log_f.flush()
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=proj.local_target_dir,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=MILESTONE_TIMEOUT_S,
                )
                return_code = proc.returncode
            except subprocess.TimeoutExpired:
                log_f.write(f"\n[LoopDaemon] Milestone {ms.milestone_id} timed out after {MILESTONE_TIMEOUT_S}s.\n")
                log_f.flush()
                return_code = 124

        after_next = self.planner.next_actionable_milestone(repo_name=proj.repo_name)
        completed_ok = return_code == 0 and (
            not after_next or after_next["milestone"].milestone_id != ms.milestone_id
        )

        dstate = self._load_dispatch_state()
        if "daily_dispatch_counts" not in dstate or not isinstance(dstate["daily_dispatch_counts"], dict):
            dstate["daily_dispatch_counts"] = {}
        if completed_ok:
            dstate["last_dispatch_date"] = today
            dstate["daily_dispatch_counts"][today] = int(dstate["daily_dispatch_counts"].get(today, 0)) + 1
        dstate["active_milestone"] = None
        dstate["dispatched_milestones"][ms.milestone_id] = {
            "repo_name": proj.repo_name,
            "chat_title": title,
            "model": self.pi_model,
            "thinking": self.thinking_level,
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "exit_code": return_code,
            "completed": completed_ok,
            "log_file": run_log_path,
        }
        self._save_dispatch_state(dstate)
        self.log(
            f"Finished Pi ({self.pi_model}, thinking={self.thinking_level}) for {ms.milestone_id} "
            f"(exit_code={return_code}, completed={completed_ok}, "
            f"today_quota={dstate['daily_dispatch_counts'].get(today, 0)}/{self.daily_quota})"
        )
        return {
            "dispatched": True,
            "engine": "pi",
            "model": self.pi_model,
            "thinking": self.thinking_level,
            "repo_name": proj.repo_name,
            "chat_title": title,
            "milestone_id": ms.milestone_id,
            "exit_code": return_code,
            "completed": completed_ok,
            "today_dispatched": dstate["daily_dispatch_counts"].get(today, 0),
            "daily_quota": self.daily_quota,
            "log_file": run_log_path,
        }

    def run_all_pending_milestones(self, max_count: int = 10) -> List[Dict]:
        """Sequentially execute pending milestones using Pi (`claude-opus-5-5`, `thinking=high`)."""
        results: List[Dict] = []
        retry_counts: Dict[str, int] = {}
        for _ in range(max_count):
            nxt = self.planner.next_actionable_milestone()
            if not nxt:
                break
            ms_id = nxt["milestone"].milestone_id
            res = self.dispatch_next_milestone_to_model(force=True)
            results.append(res)
            after = self.planner.next_actionable_milestone()
            if after and after["milestone"].milestone_id == ms_id:
                retry_counts[ms_id] = retry_counts.get(ms_id, 0) + 1
                if retry_counts[ms_id] >= 2:
                    self.log(f"Milestone {ms_id} remained pending after 2 Pi runs; stopping sequential runner.")
                    break
                time.sleep(5)
        return results

    def start_plan_runner_detached(self, max_count: int = 10) -> int:
        os.makedirs(self.state_dir, exist_ok=True)
        if os.path.exists(self.runner_pid_file):
            try:
                old_pid = int(open(self.runner_pid_file, "r", encoding="utf-8").read().strip())
                os.kill(old_pid, 0)
                return old_pid
            except Exception:
                pass

        pid1 = os.fork()
        if pid1 > 0:
            time.sleep(0.3)
            try:
                return int(open(self.runner_pid_file, "r", encoding="utf-8").read().strip())
            except Exception:
                return pid1

        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)

        devnull_fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull_fd, 0)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        if devnull_fd > 2:
            os.close(devnull_fd)

        with open(self.runner_pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        try:
            self.run_all_pending_milestones(max_count=max_count)
        except Exception as exc:
            self.log(f"Batch runner error: {exc}")
        finally:
            try:
                os.remove(self.runner_pid_file)
            except OSError:
                pass
        os._exit(0)

    def run_poll_and_sync_cycle(self, auto_dispatch: bool = False) -> Dict:
        """
        Execute one silent collection pass (0 LLM tokens during passive polling).
        Only invokes synthesis and build when `auto_dispatch=True` inside `WORK_WINDOW`
        and today's quota (`daily_quota=2`) has not been reached.
        """
        os.makedirs(self.state_dir, exist_ok=True)
        signals = self.collector.collect_all()
        ingested = self.planner.ingest_signals(signals)

        dispatch_res = None
        if auto_dispatch and not can_start_milestone():
            dispatch_res = {
                "dispatched": False,
                "reason": f"Outside work window {WORK_WINDOW[0]:02d}:00-{WORK_WINDOW[1]:02d}:00",
            }
        elif auto_dispatch:
            try:
                today = time.strftime("%Y-%m-%d")
                fails = 0
                synth_attempts = 0
                while can_start_milestone():
                    dstate = self._load_dispatch_state()
                    today_done = int((dstate.get("daily_dispatch_counts") or {}).get(today, 0))
                    if self.daily_quota and today_done >= self.daily_quota:
                        dispatch_res = {
                            "dispatched": False,
                            "reason": f"Daily quota satisfied ({today_done}/{self.daily_quota}) for {today}.",
                        }
                        break
                    nxt = self.planner.next_actionable_milestone()
                    if not nxt:
                        if synth_attempts >= 2:
                            break
                        synth_attempts += 1
                        added = self.synthesize_milestones_via_pi(signals)
                        if not added:
                            break
                    res = self.dispatch_next_milestone_to_model(force=False)
                    dispatch_res = res
                    if not res.get("dispatched"):
                        break
                    if not res.get("completed"):
                        fails += 1
                        if fails >= 2:
                            break
                        time.sleep(20)
            except Exception as exc:
                dispatch_res = {"dispatched": False, "error": str(exc)}

        next_item = self.planner.next_actionable_milestone()
        next_summary = None
        if next_item:
            proj = next_item["project"]
            ms = next_item["milestone"]
            next_summary = {
                "repo_name": proj.repo_name,
                "chat_title": ms.chat_title or f"猜你想做 · {proj.repo_name}",
                "mode": proj.mode,
                "milestone_id": ms.milestone_id,
                "commit_header": f"{ms.commit_type}({ms.scope}): {ms.summary}",
                "deliverables": ms.deliverables,
            }

        status_payload = {
            "last_poll_ts": int(time.time()),
            "last_poll_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "engine": "pi",
            "pi_model": self.pi_model,
            "thinking": self.thinking_level,
            "daily_quota": self.daily_quota,
            "total_signals_collected": len(signals),
            "newly_ingested_by_repo": ingested,
            "next_actionable_milestone": next_summary,
            "last_dispatch": dispatch_res or self._load_dispatch_state(),
            "github_account": self.git_sync.load_account_config(),
        }
        with open(self.status_file, "w", encoding="utf-8") as f:
            json.dump(status_payload, f, ensure_ascii=False, indent=2)

        self.log(
            f"Polled {len(signals)} signals; ingested={sum(ingested.values())}; "
            f"next={next_summary['milestone_id'] if next_summary else 'ON_DEMAND_SYNTHESIS'}"
        )
        return status_payload

    def start_detached(self, interval_seconds: int = 3600) -> int:
        """Start the lightweight Python polling daemon as a detached background process."""
        os.makedirs(self.state_dir, exist_ok=True)
        if os.path.exists(self.pid_file):
            try:
                old_pid = int(open(self.pid_file, "r", encoding="utf-8").read().strip())
                os.kill(old_pid, 0)
                return old_pid
            except Exception:
                pass

        pid1 = os.fork()
        if pid1 > 0:
            time.sleep(0.3)
            try:
                return int(open(self.pid_file, "r", encoding="utf-8").read().strip())
            except Exception:
                return pid1

        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)

        devnull_fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull_fd, 0)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        if devnull_fd > 2:
            os.close(devnull_fd)

        with open(self.pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        self.log(
            f"Started loop-engineer daemon (PID={os.getpid()}, engine=pi, model={self.pi_model}, "
            f"thinking={self.thinking_level}, daily_quota={self.daily_quota}, interval={interval_seconds}s)"
        )
        while True:
            try:
                self.run_poll_and_sync_cycle(auto_dispatch=True)
            except Exception as exc:
                self.log(f"Cycle error: {exc}")
            time.sleep(max(300, int(interval_seconds)))
