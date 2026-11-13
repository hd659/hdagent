"""
Dual-Engine Backlog & Subtext-Driven Project Rotation Planner.

Operates on Two Distinct Engines:
1. `extrapolate_new` (~80%): Brand-new standalone tools/products inferred from Haodong's
   cross-agent conversations (Claude Code, Antigravity, Pi, Codex) and thought diaries,
   built cleanly under `~/Desktop/hdagent/workspaces/<repo_name>`.
2. `self_optimize` (~20%): Substantial new capabilities on safe local projects
   (excluding live production gateway `Desktop/cs/api`).

Enforces anti-monotony rotation: never locks onto a single repository (such as `frictionlab`),
capping consecutive runs on the same repository so ideation tracks fresh conversations.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .collector import EngineeringSignal

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME_DIR = os.path.expanduser("~")
MAX_CONSECUTIVE_SAME_REPO = 2
SATURATED_MILESTONE_CAP = 6


@dataclass
class CommitMilestone:
    milestone_id: str
    commit_type: str  # e.g. "feat", "test", "perf", "docs"
    scope: str
    summary: str
    deliverables: List[str]
    status: str = "pending"  # "pending" | "completed"
    committed_at: Optional[str] = None
    chat_title: str = ""
    user_voice_prompt: str = ""


@dataclass
class PlannedProject:
    repo_name: str
    pillar: str
    mode: str  # "self_optimize" | "extrapolate_new"
    local_target_dir: str
    tagline: str
    origin_context: str
    scheduled_days: List[str]
    tech_stack: List[str]
    milestones: List[CommitMilestone] = field(default_factory=list)
    dynamic_signals: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def build_default_weekly_projects() -> List[PlannedProject]:
    """Construct baseline dual-engine projects (used only when initializing an empty state dir)."""
    return [
        PlannedProject(
            repo_name="loop-engineer",
            pillar="ai-infra-harness",
            mode="extrapolate_new",
            local_target_dir=PACKAGE_ROOT,
            tagline="Conversation-driven autonomous GitHub incubator & existing-project self-optimizer.",
            origin_context=(
                "Built to continuously analyze daily human-agent interactions and thought diaries, "
                "inferring latent project ideas and shipping tested open-source tools."
            ),
            scheduled_days=["2026-10-25 (Day 1)"],
            tech_stack=["Python", "PyTest", "GitHub CLI", "Pi Agent"],
            milestones=[
                CommitMilestone(
                    milestone_id="le-m1",
                    commit_type="feat",
                    scope="core",
                    summary="implement persona filter, zero-leak privacy gate, and multi-source collector",
                    deliverables=["loop_engineer/persona.py", "loop_engineer/privacy.py", "loop_engineer/collector.py"],
                    status="completed",
                ),
                CommitMilestone(
                    milestone_id="le-m2",
                    commit_type="feat",
                    scope="scheduler",
                    summary="add dual-engine planner and autonomous daemon",
                    deliverables=["loop_engineer/planner.py", "loop_engineer/github_sync.py", "loop_engineer/daemon.py", "loop.py"],
                    status="completed",
                ),
                CommitMilestone(
                    milestone_id="le-m3",
                    commit_type="test",
                    scope="suite",
                    summary="add unit tests for privacy redaction, signal classification, and milestone state machine",
                    deliverables=["tests/test_loop_engineer.py", "README.md", "WEEKLY_PLAN.md"],
                    status="completed",
                ),
            ],
        ),
        PlannedProject(
            repo_name="netmap",
            pillar="workflow-mcp",
            mode="self_optimize",
            local_target_dir=f"{HOME_DIR}/Desktop/cs/netmap",
            tagline="[Existing Project Optimization] Upgrade netmap from static proxy viewer to active Split-Tunnel & CDN TTFB Doctor.",
            origin_context="Directly optimizes `Desktop/cs/netmap` based on Wi-Fi & proxy split-tunnel debugging.",
            scheduled_days=["2026-10-26 (Day 2)"],
            tech_stack=["Python", "HTML/JS", "macOS scutil/lsof"],
            milestones=[
                CommitMilestone(
                    milestone_id="nm-m1",
                    commit_type="feat",
                    scope="probe",
                    summary="add concurrent TTFB latency probes across direct interface, system proxy, and SSH tunnel",
                    deliverables=["server.py", "tests/test_netmap_probe.py"],
                ),
                CommitMilestone(
                    milestone_id="nm-m2",
                    commit_type="feat",
                    scope="doctor",
                    summary="detect split-tunnel routing misconfigurations and render alerts in UI",
                    deliverables=["server.py", "index.html", "README.md"],
                ),
            ],
        ),
        PlannedProject(
            repo_name="single-thread-lock",
            pillar="cognitive-systems",
            mode="extrapolate_new",
            local_target_dir=os.path.join(PACKAGE_ROOT, "workspaces", "single-thread-lock"),
            tagline="[New Extrapolated Project] Anti-TodoList single-aperture execution lock for networked thinkers.",
            origin_context="Extrapolated from Phantom Overload & Activation Friction thought diary.",
            scheduled_days=["2026-10-27 (Day 3)", "2026-10-28 (Day 4)"],
            tech_stack=["Python", "Textual/CLI", "SQLite", "PyTest"],
            milestones=[
                CommitMilestone(
                    milestone_id="stl-m1",
                    commit_type="feat",
                    scope="vault",
                    summary="implement zero-list brain-dump sink (RAM-to-Disk) and 10-minute micro-slice decomposer",
                    deliverables=["single_thread/vault.py", "tests/test_vault.py"],
                ),
                CommitMilestone(
                    milestone_id="stl-m2",
                    commit_type="feat",
                    scope="aperture",
                    summary="build single-task terminal aperture with ground-state reset timer and anti-peek lock",
                    deliverables=["single_thread/cli.py", "tests/test_aperture.py", "README.md"],
                ),
            ],
        ),
        PlannedProject(
            repo_name="submission-truth-auditor",
            pillar="workflow-mcp",
            mode="extrapolate_new",
            local_target_dir=os.path.join(PACKAGE_ROOT, "workspaces", "submission-truth-auditor"),
            tagline="[New Extrapolated Project] Pre-submission numeric cross-verifier & Viva Question Generator.",
            origin_context="Extrapolated from pre-submission report numeric verification and Viva rediscuss prep.",
            scheduled_days=["2026-10-28 (Day 4)", "2026-10-29 (Day 5)"],
            tech_stack=["Python", "AST/Regex", "PyTest"],
            milestones=[
                CommitMilestone(
                    milestone_id="sta-m1",
                    commit_type="feat",
                    scope="auditor",
                    summary="extract numeric claims from Markdown/PDF reports and cross-verify against deterministic script outputs",
                    deliverables=["truth_auditor/numeric_diff.py", "tests/test_numeric_diff.py"],
                ),
                CommitMilestone(
                    milestone_id="sta-m2",
                    commit_type="feat",
                    scope="viva",
                    summary="analyze C++/Python AST complexity invariants to generate adversarial Tutor Viva/Rediscuss questions",
                    deliverables=["truth_auditor/viva_challenger.py", "tests/test_viva.py", "README.md"],
                ),
            ],
        ),
        PlannedProject(
            repo_name="moodle-ed-autopilot-patch",
            pillar="workflow-mcp",
            mode="self_optimize",
            local_target_dir=f"{HOME_DIR}/Desktop/cs/moodle-mcp",
            tagline="[Existing Project Optimization] Add MYT timezone deadline normalizer & Short-Extension guard to moodle-mcp.",
            origin_context="Directly optimizes `Desktop/cs/moodle-mcp` based on AEDT vs MYT deadline timezone discovery.",
            scheduled_days=["2026-10-29 (Day 5)"],
            tech_stack=["Python", "FastMCP", "zoneinfo"],
            milestones=[
                CommitMilestone(
                    milestone_id="map-m1",
                    commit_type="feat",
                    scope="deadline-myt",
                    summary="add AEDT-to-MYT deadline normalizer and Short-Extension window calculator to moodle-mcp",
                    deliverables=["deadline_myt.py", "tests/test_deadline_myt.py"],
                ),
            ],
        ),
        PlannedProject(
            repo_name="dex-cex-friction-radar",
            pillar="quant-fintech-web3",
            mode="extrapolate_new",
            local_target_dir=os.path.join(PACKAGE_ROOT, "workspaces", "dex-cex-friction-radar"),
            tagline="[New Extrapolated Project] On-chain DEX vs CEX perpetuals transaction-cost arbitrage radar & Solidity atomic vault.",
            origin_context="Synthesizes Transaction Cost Economics diary with on-chain quant exploration.",
            scheduled_days=["2026-10-30 (Day 6)", "2026-10-31 (Day 7)"],
            tech_stack=["Solidity", "Python", "AsyncIO", "PyTest"],
            milestones=[
                CommitMilestone(
                    milestone_id="dcf-m1",
                    commit_type="feat",
                    scope="friction-engine",
                    summary="model net arbitrage spread between Uniswap v3 concentrated liquidity pools and CEX perps after gas/slippage friction",
                    deliverables=["friction_radar/spread_model.py", "tests/test_spread_model.py"],
                ),
                CommitMilestone(
                    milestone_id="dcf-m2",
                    commit_type="feat",
                    scope="contracts",
                    summary="implement Solidity atomic settlement vault with minimum net-profit guard and flash-rebalance hook",
                    deliverables=["contracts/AtomicFrictionVault.sol", "tests/test_vault_guard.py", "README.md"],
                ),
            ],
        ),
    ]


class WeeklyPlanner:
    def __init__(self, state_dir: str = os.path.join(PACKAGE_ROOT, ".state")):
        self.state_dir = state_dir
        self.backlog_file = os.path.join(self.state_dir, "backlog.json")
        self.flagship_file = os.path.join(self.state_dir, "flagship.json")

    def load_flagship(self) -> Optional[Dict]:
        """Deprecated hard-lock hook: always returns None so no single repo monopolizes daily runs."""
        return None

    def load_or_init_projects(self, force_reset: bool = False) -> List[PlannedProject]:
        os.makedirs(self.state_dir, exist_ok=True)
        if not force_reset and os.path.exists(self.backlog_file):
            try:
                with open(self.backlog_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                projects: List[PlannedProject] = []
                allowed_ms_keys = {
                    "milestone_id",
                    "commit_type",
                    "scope",
                    "summary",
                    "deliverables",
                    "status",
                    "committed_at",
                    "chat_title",
                    "user_voice_prompt",
                }
                for item in raw.get("projects", []):
                    if "mode" not in item:
                        break
                    milestones = [
                        CommitMilestone(**{k: v for k, v in m.items() if k in allowed_ms_keys})
                        for m in item.get("milestones", [])
                    ]
                    item_copy = dict(item)
                    item_copy["milestones"] = milestones
                    projects.append(PlannedProject(**item_copy))
                if projects:
                    return projects
            except Exception:
                pass

        projects = build_default_weekly_projects()
        self.save_projects(projects)
        return projects

    def save_projects(self, projects: List[PlannedProject]) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        payload = {"projects": [p.to_dict() for p in projects]}
        tmp = self.backlog_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.backlog_file)

    def ingest_signals(self, signals: List[EngineeringSignal]) -> Dict[str, int]:
        """Link collected conversation/diary signals to matching projects without mutating pending milestones."""
        projects = self.load_or_init_projects()
        by_name = {p.repo_name: p for p in projects}
        added_counts: Dict[str, int] = {p.repo_name: 0 for p in projects}

        for sig in signals:
            blob = f"{sig.title} {sig.summary}".lower()
            if any(k in blob for k in ("wi-fi", "misty", "netmap", "ipv6", "tailscale", "dns", "路由")):
                target = by_name.get("netmap", projects[0])
            elif any(k in blob for k in ("fit1043", "fit1008", "fit1055", "rubric", "pdf", "rediscuss", "核对")):
                target = by_name.get("submission-truth-auditor", projects[0])
            elif any(k in blob for k in ("moodle", "edstem", "short extension", "mpu", "选课")):
                target = by_name.get("moodle-ed-autopilot-patch", projects[0])
            elif any(k in blob for k in ("过载", "启动", "状态", "冥想", "切片", "overload", "friction", "bayes")):
                target = by_name.get("single-thread-lock", projects[0])
            elif any(k in blob for k in ("区块链", "量化", "交易成本", "套利", "grid", "okx", "blockchain", "quant")):
                target = by_name.get("dex-cex-friction-radar", projects[0])
            else:
                target = projects[-1]

            existing_ids = {d.get("signal_id") for d in target.dynamic_signals}
            if sig.signal_id not in existing_ids and len(target.dynamic_signals) < 50:
                target.dynamic_signals.append(
                    {
                        "signal_id": sig.signal_id,
                        "date": sig.date,
                        "source_type": sig.source_type,
                        "title": sig.title,
                    }
                )
                added_counts[target.repo_name] += 1

        self.save_projects(projects)
        return added_counts

    def auto_synthesize_from_signals(self, signals: List[EngineeringSignal]) -> List[str]:
        """Deterministic fallback synthesizer (kept for offline/unit-test use)."""
        projects = self.load_or_init_projects()
        by_name = {p.repo_name: p for p in projects}
        created_ms: List[str] = []
        combined_text = " ".join(f"{s.title} {s.summary}" for s in signals).lower()

        if any(k in combined_text for k in ("邮箱保险箱", "oauth", "imap", "adspower", "browser_launcher", "magic link")):
            if "oauth-imap-otp-extractor" not in by_name:
                proj = PlannedProject(
                    repo_name="oauth-imap-otp-extractor",
                    pillar="ai-infra-harness",
                    mode="extrapolate_new",
                    local_target_dir=os.path.join(PACKAGE_ROOT, "workspaces", "oauth-imap-otp-extractor"),
                    tagline="[New Extrapolated Project] Zero-GUI XOAUTH2 IMAP OTP/Magic-Link extractor & isolated SOCKS5 browser profile launcher.",
                    origin_context="Synthesized from OAuth2 IMAP OTP extraction and isolated browser profile workflow.",
                    scheduled_days=["Dynamic Queue"],
                    tech_stack=["Python", "IMAP4/XOAUTH2", "SOCKS5", "PyTest"],
                    milestones=[
                        CommitMilestone(
                            milestone_id="oie-m1",
                            commit_type="feat",
                            scope="imap-xoauth2",
                            summary="implement XOAUTH2 access-token refresher and deterministic 6-digit OTP & magic-link MIME parser",
                            deliverables=["otp_vault/imap_xoauth2.py", "tests/test_imap_xoauth2.py"],
                        ),
                    ],
                )
                projects.append(proj)
                by_name[proj.repo_name] = proj
                created_ms.append("oie-m1")

        if any(k in combined_text for k in ("omni-moderation", "omini", "蜜罐", "tarpit", "酒馆", "前置审核")):
            if "llm-edge-tarpit-guard" not in by_name:
                proj = PlannedProject(
                    repo_name="llm-edge-tarpit-guard",
                    pillar="ai-infra-harness",
                    mode="extrapolate_new",
                    local_target_dir=os.path.join(PACKAGE_ROOT, "workspaces", "llm-edge-tarpit-guard"),
                    tagline="[New Extrapolated Project] Zero-latency code-aware LLM moderation filter & 3-strike SSE tarpit router.",
                    origin_context="Synthesized from code-aware edge moderation filtering and progressive tarpit routing.",
                    scheduled_days=["Dynamic Queue"],
                    tech_stack=["Python", "Regex/AST", "SSE", "PyTest"],
                    milestones=[
                        CommitMilestone(
                            milestone_id="let-m1",
                            commit_type="feat",
                            scope="moderation",
                            summary="implement code-block & tool-result stripper with weighted jailbreak/moderation risk scorer",
                            deliverables=["edge_guard/moderation_filter.py", "tests/test_moderation_filter.py"],
                        ),
                    ],
                )
                projects.append(proj)
                by_name[proj.repo_name] = proj
                created_ms.append("let-m1")

        if created_ms:
            self.save_projects(projects)
        return created_ms

    def merge_llm_synthesized_plan(self, items: List[Dict]) -> List[str]:
        """Merge LLM-synthesized projects or milestones into `backlog.json`, rejecting saturated or self-referential repos."""
        projects = self.load_or_init_projects()
        by_name = {p.repo_name: p for p in projects}
        all_ms_ids = {m.milestone_id for p in projects for m in p.milestones}
        added_ms: List[str] = []

        for raw in items:
            repo_name = str(raw.get("repo_name") or "").strip().lower()
            if not repo_name or repo_name in ("hdagent", "loop-engineer", "frictionlab", "api", "personal-ai-gateway"):
                continue

            # Reject adding more milestones to an already saturated repo
            if repo_name in by_name and len(by_name[repo_name].milestones) >= SATURATED_MILESTONE_CAP:
                continue

            mode = str(raw.get("mode") or "extrapolate_new")
            workspaces_root = os.path.join(PACKAGE_ROOT, "workspaces")
            target_dir = str(
                raw.get("local_target_dir")
                or os.path.join(workspaces_root, repo_name)
            )
            # Safety rail: never let background autonomous jobs mutate live production gateway `Desktop/cs/api` or `hdagent` root
            if (
                "/Desktop/cs/api" in target_dir
                or target_dir.rstrip("/") in (PACKAGE_ROOT.rstrip("/"), f"{HOME_DIR}/Desktop/project", f"{HOME_DIR}/Desktop/hdagent")
            ):
                mode = "extrapolate_new"
                target_dir = os.path.join(workspaces_root, repo_name)
            elif "/Desktop/project/workspaces/" in target_dir:
                target_dir = os.path.join(workspaces_root, repo_name)

            proj_default_title = str(raw.get("chat_title") or "").strip()
            proj_default_prompt = str(raw.get("user_voice_prompt") or "").strip()

            raw_milestones = raw.get("milestones") or []
            new_ms_objs: List[CommitMilestone] = []
            for m in raw_milestones[:2]:
                ms_id = str(m.get("milestone_id") or "").strip()
                if not ms_id or ms_id in all_ms_ids:
                    continue
                deliverables = [str(d) for d in (m.get("deliverables") or []) if d]
                if not deliverables:
                    continue
                chat_title = str(m.get("chat_title") or proj_default_title or f"猜你想做 · {repo_name}").strip()
                user_prompt = str(m.get("user_voice_prompt") or proj_default_prompt or "").strip()
                new_ms_objs.append(
                    CommitMilestone(
                        milestone_id=ms_id,
                        commit_type=str(m.get("commit_type") or "feat"),
                        scope=str(m.get("scope") or "core"),
                        summary=str(m.get("summary") or "implement core project deliverables and unit tests"),
                        deliverables=deliverables,
                        status="pending",
                        chat_title=chat_title,
                        user_voice_prompt=user_prompt,
                    )
                )
                all_ms_ids.add(ms_id)
                added_ms.append(ms_id)

            if not new_ms_objs:
                continue

            if repo_name in by_name:
                by_name[repo_name].milestones.extend(new_ms_objs)
            else:
                proj = PlannedProject(
                    repo_name=repo_name,
                    pillar=str(raw.get("pillar") or "ai-infra-harness"),
                    mode=mode,
                    local_target_dir=target_dir,
                    tagline=str(raw.get("tagline") or f"[New Extrapolated Project] {repo_name}"),
                    origin_context=str(raw.get("origin_context") or "Synthesized from cross-agent conversation subtext."),
                    scheduled_days=[str(raw.get("scheduled_day") or "Dynamic Subtext Queue")],
                    tech_stack=[str(t) for t in (raw.get("tech_stack") or ["Python", "PyTest"])],
                    milestones=new_ms_objs,
                )
                projects.append(proj)
                by_name[repo_name] = proj

        if added_ms:
            self.save_projects(projects)
        return added_ms

    def recent_completed_repos(self, limit: int = MAX_CONSECUTIVE_SAME_REPO) -> List[str]:
        """Return repo_names of the most recently completed milestones (sorted by committed_at)."""
        projects = self.load_or_init_projects()
        done_pairs = []
        for proj in projects:
            for ms in proj.milestones:
                if ms.status == "completed" and ms.committed_at:
                    done_pairs.append((ms.committed_at, proj.repo_name))
        done_pairs.sort(reverse=True)
        return [repo for _, repo in done_pairs[:limit]]

    def next_actionable_milestone(self, repo_name: Optional[str] = None) -> Optional[Dict]:
        """Return the next pending milestone with anti-monotony rotation."""
        projects = self.load_or_init_projects()
        pending_candidates = []
        for proj in projects:
            if repo_name and proj.repo_name != repo_name:
                continue
            for ms in proj.milestones:
                if ms.status == "pending":
                    pending_candidates.append({"project": proj, "milestone": ms})
                    break

        if not pending_candidates:
            return None
        if repo_name or len(pending_candidates) == 1:
            return pending_candidates[0]

        recent = self.recent_completed_repos(limit=MAX_CONSECUTIVE_SAME_REPO)
        if len(recent) == MAX_CONSECUTIVE_SAME_REPO and len(set(recent)) == 1:
            overused_repo = recent[0]
            for cand in pending_candidates:
                if cand["project"].repo_name != overused_repo:
                    return cand
        return pending_candidates[0]

    def mark_milestone_completed(self, milestone_id: str, timestamp_iso: str) -> bool:
        projects = self.load_or_init_projects()
        updated = False
        for proj in projects:
            for ms in proj.milestones:
                if ms.milestone_id == milestone_id:
                    ms.status = "completed"
                    ms.committed_at = timestamp_iso
                    updated = True
        if updated:
            self.save_projects(projects)
        return updated
