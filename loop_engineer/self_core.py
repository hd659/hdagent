"""
hdagent v0.1 — Digital Self Kernel (`DigitalSelfCore`) & L1-L3 Autonomy Gate.

Continuously learns "Digital Haodong" from incremental cross-agent conversations
(Claude Code, Antigravity, Pi, Codex) and thought diaries without re-processing
historical signals:

1. Tier A (0-Token Fast Pass on every poll):
   - Tracks `learned_signal_ids` cursor so each new conversation is absorbed once.
   - Updates workspace attention heat (`workspace_focus`), utterance rhythm metrics,
     and a rolling reservoir of sanitized, verbatim user utterances (`authentic_utterances`)
     that capture real casual phrasing rather than stiff corporate prose.

2. Tier B (Deep Cognitive Delta Distillation via `claude-opus-5-5`, `thinking=high`, `--no-session`):
   - Incrementally distills newly observed conversations into 5 persistent memory banks:
     * `decision_principles`: how the user weighs trade-offs and chooses shortest paths
     * `redlines`: strict boundaries and anti-patterns the user dislikes or forbids
     * `active_intents`: current cross-session goals and underlying preoccupations
     * `playbooks`: repeatable workflows learned from user-agent sessions, tagged with
       recommended autonomy tier (`L1_sandbox` | `L2_confirm` | `L3_auto`)
     * `voice_notes`: concrete linguistic habits so clones speak in authentic user voice

3. L1-L3 Autonomy Gate (`ActionProposal` queue):
   - `L1_sandbox`: safe isolated execution (build & verify first, zero external mutation)
   - `L2_confirm`: draft external/cloud/GUI action and wait for 1-click user approval
   - `L3_auto`: trusted repeatable playbook authorized for end-to-end execution + audit log
"""

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .collector import EngineeringSignal
from .privacy import PrivacyGate

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME_DIR = os.path.expanduser("~")
PI_BIN = os.path.join(HOME_DIR, ".npm-global", "bin", "pi")

AUTONOMY_L1_SANDBOX = "L1_sandbox"
AUTONOMY_L2_CONFIRM = "L2_confirm"
AUTONOMY_L3_AUTO = "L3_auto"
VALID_AUTONOMY_LEVELS = {AUTONOMY_L1_SANDBOX, AUTONOMY_L2_CONFIRM, AUTONOMY_L3_AUTO}


@dataclass
class LearnedPlaybook:
    slug: str
    title: str
    trigger_when: str
    steps_summary: str
    autonomy_level: str = AUTONOMY_L1_SANDBOX
    confidence: float = 0.7
    updated_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ActionProposal:
    proposal_id: str
    title: str
    domain: str  # "sandbox_code" | "cloud_ops" | "computer_use"
    autonomy_level: str
    rationale: str
    planned_command_or_steps: str
    status: str = "pending"  # "pending" | "approved" | "executed" | "rejected"
    created_at: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def default_self_core_state() -> Dict:
    return {
        "schema_version": "hdagent-self-core-v0.1",
        "updated_at": "",
        "total_absorbed_signals": 0,
        "last_deep_distill_at": "",
        "pending_deep_signal_ids": [],
        "learned_signal_ids": [],
        "workspace_focus": {},
        "rhythm_stats": {
            "sample_count": 0,
            "avg_chars": 0,
            "short_direct_ratio": 0.0,
        },
        "decision_principles": [
            "第一性原理优先：追到底层根因与最短路径，砍掉不改变决策的装饰与冗余抽象。",
            "先对齐分叉再重投入，一旦方向明确（直接做）则一次端到端闭环交付（代码 + 测试 + 落盘）。",
            "重实用杠杆：工具必须解决自己高频真实摩擦或验证明确假设，不做空壳 CRUD 或炒冷饭微补丁。",
        ],
        "redlines": [
            "严禁在未授权情况下由后台任务直接修改线上生产网关目录或外发真实客户消息。",
            "严禁任何真实密钥、学号、私人邮箱、VPS/局域网 IP、客户标识或个人隐私反思外泄到公开仓库。",
            "讨厌 AI 八股腔、华丽空洞排比、Emoji 堆砌与晦涩机器日志刷屏，汇报必须直白像人话。",
        ],
        "active_intents": [],
        "voice_notes": [
            "口语直奔主题，常以短句切入或连续追问底层原因（如“对齐一下”、“怎么回事”、“你看看可不可以”）。",
            "中英技术词自然混打（如 agent / pi / agy / 缓存 / 端口），不写死板的甲乙方式需求公文。",
            "习惯在散乱直觉中抓本质模型，要求对方听懂潜台词并收敛成清晰结构。",
        ],
        "authentic_utterances": [],
        "playbooks": [],
    }


class DigitalSelfCore:
    def __init__(
        self,
        state_dir: str = os.path.join(PACKAGE_ROOT, ".state"),
        privacy_gate: Optional[PrivacyGate] = None,
    ):
        self.state_dir = state_dir
        self.core_file = os.path.join(self.state_dir, "self_core.json")
        self.proposals_file = os.path.join(self.state_dir, "approval_queue.json")
        self.privacy_gate = privacy_gate or PrivacyGate()

    def load(self) -> Dict:
        os.makedirs(self.state_dir, exist_ok=True)
        if os.path.isfile(self.core_file):
            try:
                with open(self.core_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                base = default_self_core_state()
                base.update(data)
                return base
            except Exception:
                pass
        state = default_self_core_state()
        self.save(state)
        return state

    def save(self, state: Dict) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        tmp = self.core_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.core_file)

    @staticmethod
    def _extract_clean_utterances(sig: EngineeringSignal) -> List[str]:
        if sig.source_type not in ("claude_session", "pi_session", "agy_transcript", "codex_session"):
            return []
        parts = [p.strip() for p in sig.summary.split(" / ") if p.strip()]
        valid = []
        for p in parts:
            # Skip pasted stack traces, terminal dumps, or ultra-short one-word replies
            if len(p) < 18 or len(p) > 260:
                continue
            if any(tok in p for tok in ("Traceback", "http://", "https://", "```", "{", "SELECT ")):
                continue
            valid.append(p)
        return valid

    @staticmethod
    def _extract_workspace_key(sig: EngineeringSignal) -> str:
        m = re.match(r"^\[([^\]]+)\]", sig.title)
        if m:
            return m.group(1)
        return sig.pillar

    def absorb_signals_fast(self, signals: List[EngineeringSignal]) -> Dict:
        """
        Tier A (0-token incremental absorption):
        Absorb any previously unseen signals, updating workspace focus, rhythm stats,
        authentic utterance samples, and queuing unseen IDs for Tier B deep distillation.
        """
        state = self.load()
        learned_set = set(state.get("learned_signal_ids") or [])
        pending_deep = list(state.get("pending_deep_signal_ids") or [])
        pending_set = set(pending_deep)
        ws_focus: Dict[str, int] = dict(state.get("workspace_focus") or {})
        utterances: List[str] = list(state.get("authentic_utterances") or [])
        existing_utt_set = set(utterances)

        new_count = 0
        lengths: List[int] = []
        for sig in signals:
            if sig.signal_id in learned_set:
                continue
            learned_set.add(sig.signal_id)
            new_count += 1
            if sig.signal_id not in pending_set:
                pending_deep.append(sig.signal_id)
                pending_set.add(sig.signal_id)

            ws_key = self._extract_workspace_key(sig)
            ws_focus[ws_key] = int(ws_focus.get(ws_key, 0)) + 1

            for utt in self._extract_clean_utterances(sig):
                clean_utt, _ = self.privacy_gate.sanitize_text(utt)
                lengths.append(len(clean_utt))
                if clean_utt not in existing_utt_set:
                    utterances.insert(0, clean_utt)
                    existing_utt_set.add(clean_utt)

        if new_count > 0:
            # Keep bounded rolling memory so state file stays compact & fresh
            state["learned_signal_ids"] = list(learned_set)[-1500:]
            state["pending_deep_signal_ids"] = pending_deep[-80:]
            state["total_absorbed_signals"] = int(state.get("total_absorbed_signals", 0)) + new_count
            state["workspace_focus"] = dict(
                sorted(ws_focus.items(), key=lambda kv: kv[1], reverse=True)[:15]
            )
            state["authentic_utterances"] = utterances[:18]

            if lengths:
                prev = state.get("rhythm_stats") or {}
                prev_n = int(prev.get("sample_count", 0))
                total_n = prev_n + len(lengths)
                avg_len = int(
                    (prev_n * float(prev.get("avg_chars", 0)) + sum(lengths)) / max(1, total_n)
                )
                short_hits = sum(1 for x in lengths if x <= 90)
                short_ratio = round(
                    (prev_n * float(prev.get("short_direct_ratio", 0.0)) + short_hits) / max(1, total_n),
                    2,
                )
                state["rhythm_stats"] = {
                    "sample_count": total_n,
                    "avg_chars": avg_len,
                    "short_direct_ratio": short_ratio,
                }
            self.save(state)

        return {
            "newly_absorbed": new_count,
            "pending_deep_count": len(state.get("pending_deep_signal_ids") or []),
            "total_absorbed": state.get("total_absorbed_signals", 0),
        }

    @staticmethod
    def _merge_unique_strings(existing: List[str], incoming: List[str], cap: int = 10) -> List[str]:
        out: List[str] = []
        seen = set()
        for item in list(incoming) + list(existing):
            s = re.sub(r"\s+", " ", str(item or "")).strip()
            if len(s) < 6:
                continue
            key = s[:28].lower()
            if key not in seen:
                seen.add(key)
                out.append(s)
            if len(out) >= cap:
                break
        return out

    def merge_distilled_delta(self, delta: Dict, consumed_ids: Optional[List[str]] = None) -> Dict:
        """Deterministically merge LLM-distilled cognitive delta into persistent `self_core.json`."""
        state = self.load()

        if isinstance(delta.get("decision_principles"), list):
            state["decision_principles"] = self._merge_unique_strings(
                state.get("decision_principles", []), delta["decision_principles"], cap=10
            )
        if isinstance(delta.get("redlines"), list):
            state["redlines"] = self._merge_unique_strings(
                state.get("redlines", []), delta["redlines"], cap=8
            )
        if isinstance(delta.get("active_intents"), list):
            # Active intents prioritize newest inferred goals first (cap 8)
            state["active_intents"] = self._merge_unique_strings(
                state.get("active_intents", []), delta["active_intents"], cap=8
            )
        if isinstance(delta.get("voice_notes"), list):
            state["voice_notes"] = self._merge_unique_strings(
                state.get("voice_notes", []), delta["voice_notes"], cap=8
            )

        if isinstance(delta.get("playbooks"), list):
            by_slug = {p.get("slug"): p for p in (state.get("playbooks") or []) if isinstance(p, dict) and p.get("slug")}
            today = time.strftime("%Y-%m-%d")
            for raw_pb in delta["playbooks"]:
                if not isinstance(raw_pb, dict):
                    continue
                slug = re.sub(r"[^a-z0-9_-]", "-", str(raw_pb.get("slug") or "").strip().lower()).strip("-")
                if not slug:
                    continue
                lvl = str(raw_pb.get("autonomy_level") or AUTONOMY_L1_SANDBOX)
                if lvl not in VALID_AUTONOMY_LEVELS:
                    lvl = AUTONOMY_L1_SANDBOX
                pb = LearnedPlaybook(
                    slug=slug,
                    title=str(raw_pb.get("title") or slug)[:80],
                    trigger_when=str(raw_pb.get("trigger_when") or "")[:180],
                    steps_summary=str(raw_pb.get("steps_summary") or "")[:260],
                    autonomy_level=lvl,
                    confidence=round(min(1.0, max(0.1, float(raw_pb.get("confidence", 0.75)))), 2),
                    updated_at=today,
                )
                by_slug[slug] = pb.to_dict()
            state["playbooks"] = list(by_slug.values())[-16:]

        if consumed_ids is not None:
            done = set(consumed_ids)
            state["pending_deep_signal_ids"] = [
                sid for sid in (state.get("pending_deep_signal_ids") or []) if sid not in done
            ]
        state["last_deep_distill_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.save(state)
        return state

    def distill_delta_via_pi(
        self,
        signals: List[EngineeringSignal],
        pi_model: str = "local-gateway/claude-opus-5-5",
        thinking_level: str = "high",
        min_pending: int = 5,
        force: bool = False,
    ) -> Dict:
        """
        Tier B: Invoke `claude-opus-5-5` (`--thinking high --no-session`) to distill newly
        accumulated cross-agent conversations & thought diaries into `self_core.json`.
        """
        self.absorb_signals_fast(signals)
        state = self.load()
        pending_ids = set(state.get("pending_deep_signal_ids") or [])
        if not force and len(pending_ids) < min_pending:
            return {"distilled": False, "reason": f"Only {len(pending_ids)}/{min_pending} new signals pending."}

        by_id = {s.signal_id: s for s in signals}
        batch = [by_id[sid] for sid in state.get("pending_deep_signal_ids", []) if sid in by_id]
        if not batch and force:
            batch = signals[:24]
        batch = batch[:28]
        if not batch:
            return {"distilled": False, "reason": "No matching signal payloads to distill."}

        digest = "\n".join(
            f"- [{s.date}] ({s.source_type} | {s.pillar}) {s.title} :: {s.summary[:240]}"
            for s in batch
        )
        current_snapshot = {
            "decision_principles": state.get("decision_principles", [])[:6],
            "redlines": state.get("redlines", [])[:6],
            "active_intents": state.get("active_intents", [])[:5],
            "voice_notes": state.get("voice_notes", [])[:5],
            "existing_playbook_slugs": [p.get("slug") for p in state.get("playbooks", [])],
        }

        prompt = (
            "你是 `hdagent` 的「数字自我内核提炼器（Digital Self Distiller）」。\n"
            "你的任务不是总结聊天内容，而是从用户在 Claude Code、Antigravity、Pi、Codex 四端的新增真实原话与思考日记中，"
            "**持续增量学习用户本人的决策逻辑、禁区红线、近期真实意图、可被分身接管的标准动作套路（Playbooks）以及他真实的说话语感**。\n\n"
            "【当前已知内核快照】\n"
            + json.dumps(current_snapshot, ensure_ascii=False, indent=2)
            + "\n\n【本轮新增跨端对话与日记样本】\n"
            + digest
            + "\n\n请只提炼真正高信噪比的增量认知（不要编造空话，严禁包含任何真实隐私账号/IP/密钥），严格输出一个 ```json ... ``` 对象：\n"
            "```json\n"
            "{\n"
            '  "decision_principles": ["1~3条新观察到的用户决策标准或取舍习惯（中文短句）"],\n'
            '  "redlines": ["0~2条新观察到的用户反感点或安全边界"],\n'
            '  "active_intents": ["2~4条用户最近跨对话反复思考或正在推进的真实目标"],\n'
            '  "voice_notes": ["1~3条用户日常提问的真实句式/口癖特征（帮助分身模仿本人说话而不像公文）"],\n'
            '  "playbooks": [\n'
            "    {\n"
            '      "slug": "kebab-playbook-id",\n'
            '      "title": "可复用的动作套路名称",\n'
            '      "trigger_when": "什么场景出现时可由 hdagent 触发",\n'
            '      "steps_summary": "按用户习惯的标准处理步骤（简明中文）",\n'
            '      "autonomy_level": "L1_sandbox | L2_confirm | L3_auto",\n'
            '      "confidence": 0.85\n'
            "    }\n"
            "  ]\n"
            "}\n"
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
            pi_model,
            "--thinking",
            thinking_level,
            "--no-mcp",
            "--no-tools",
            "--",
            prompt,
        ]
        proc = subprocess.run(cmd, cwd=PACKAGE_ROOT, env=env, capture_output=True, text=True, timeout=300)
        out = proc.stdout or ""
        match = re.search(r"```json\s*(\{.*?\})\s*```", out, re.DOTALL)
        raw_json = match.group(1) if match else out.strip()
        delta = json.loads(raw_json)
        consumed = [s.signal_id for s in batch]
        updated = self.merge_distilled_delta(delta, consumed_ids=consumed)
        return {
            "distilled": True,
            "consumed_signals": len(consumed),
            "active_intents": updated.get("active_intents", []),
            "playbooks_count": len(updated.get("playbooks", [])),
        }

    def render_clone_persona_context(self, include_utterance_samples: bool = True) -> str:
        """Render compact Digital Self Kernel prompt block for clone role-play & task execution."""
        state = self.load()
        lines = [
            "【hdagent 数字自我内核档案 (Digital Self Kernel v0.1)】",
            "1. 决策原则与品味：",
        ]
        for p in state.get("decision_principles", [])[:6]:
            lines.append(f"   - {p}")
        lines.append("2. 禁区红线：")
        for r in state.get("redlines", [])[:5]:
            lines.append(f"   - {r}")
        if state.get("active_intents"):
            lines.append("3. 近期跨端常驻关注焦点：")
            for it in state["active_intents"][:5]:
                lines.append(f"   - {it}")
        if include_utterance_samples:
            lines.append("4. 本人真实说话语感备忘（扮演用户写提示词时严禁书面公文化，直接贴近以下原话松弛度）：")
            for vn in state.get("voice_notes", [])[:5]:
                lines.append(f"   - 特征：{vn}")
            for sample in state.get("authentic_utterances", [])[:6]:
                lines.append(f"   - 原话切片：「{sample[:140]}」")
        return "\n".join(lines)

    # ---- L1 / L2 / L3 Autonomy Proposal Queue (for Cloud & Computer-Use stages) ----
    def enqueue_proposal(self, proposal: ActionProposal) -> Dict:
        proposals = self.list_proposals()
        if not proposal.created_at:
            proposal.created_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if proposal.autonomy_level not in VALID_AUTONOMY_LEVELS:
            proposal.autonomy_level = AUTONOMY_L1_SANDBOX
        proposals.insert(0, proposal.to_dict())
        tmp = self.proposals_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(proposals[:100], f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.proposals_file)
        return proposal.to_dict()

    def list_proposals(self, status: Optional[str] = None) -> List[Dict]:
        if not os.path.isfile(self.proposals_file):
            return []
        try:
            with open(self.proposals_file, "r", encoding="utf-8") as f:
                items = json.load(f)
            if status:
                return [x for x in items if x.get("status") == status]
            return items
        except Exception:
            return []
