"""
Multi-Source Cross-Agent User Utterance & Subtext Collector.

Silently polls Haodong's organic conversations across all active AI harnesses and thought diaries:
1. Claude Code Sessions (`~/.claude/projects/*/*.jsonl`)
2. Antigravity Transcripts (`~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl`)
3. Pi Client Sessions (`~/.pi/agent/sessions/*/*.jsonl`, excluding `Desktop-project` self-runs)
4. Codex Sessions (`~/.codex/sessions/**/*.jsonl`)
5. Thought Diaries (`~/Documents/diary/*.md`, excluding private relationship notes)
6. Architectural Entries from Obsidian Recent Conversations (`08-topics/recent-conversations.md`, excluding customer support tickets)

All extracted signals pass through `PrivacyGate` before leaving memory.
"""

import glob
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .persona import BuilderPersona, DEFAULT_PERSONA
from .privacy import PrivacyGate


@dataclass
class EngineeringSignal:
    signal_id: str
    date: str
    source_type: str  # "claude_session" | "pi_session" | "agy_transcript" | "codex_session" | "thought_diary" | "recent_conversation"
    title: str
    summary: str
    pillar: str
    source_path: str
    redacted_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


class ConversationCollector:
    def __init__(
        self,
        recent_conv_path: str = os.path.expanduser("~/Documents/Obsidian Vault/08-topics/recent-conversations.md"),
        archive_conv_path: str = os.path.expanduser("~/Documents/Obsidian Vault/08-topics/recent-conversations-archive.md"),
        diary_dir: str = os.path.expanduser("~/Documents/diary"),
        active_projects_dir: str = os.path.expanduser("~/Documents/Obsidian Vault/01-projects/_active"),
        agy_brain_dir: str = os.path.expanduser("~/.gemini/antigravity/brain"),
        pi_sessions_dir: str = os.path.expanduser("~/.pi/agent/sessions"),
        claude_projects_dir: str = os.path.expanduser("~/.claude/projects"),
        codex_sessions_dir: str = os.path.expanduser("~/.codex/sessions"),
        persona: BuilderPersona = DEFAULT_PERSONA,
        privacy_gate: Optional[PrivacyGate] = None,
    ):
        self.recent_conv_path = recent_conv_path
        self.archive_conv_path = archive_conv_path
        self.diary_dir = diary_dir
        self.active_projects_dir = active_projects_dir
        self.agy_brain_dir = agy_brain_dir
        self.pi_sessions_dir = pi_sessions_dir
        self.claude_projects_dir = claude_projects_dir
        self.codex_sessions_dir = codex_sessions_dir
        self.persona = persona
        self.privacy_gate = privacy_gate or PrivacyGate()

    @staticmethod
    def _make_id(prefix: str, key: str) -> str:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}-{digest}"

    @staticmethod
    def _workspace_tag_from_dir(dirname: str) -> str:
        home_slug = os.path.expanduser("~").strip("/").replace("/", "-")
        cleaned = re.sub(rf"^-+{re.escape(home_slug)}-?", "", dirname)
        cleaned = re.sub(r"^Desktop-?", "", cleaned)
        return cleaned or "home"

    @staticmethod
    def _is_noise_or_self_loop(text: str) -> bool:
        lowered = (text or "").strip().lower()
        if len(lowered) < 12:
            return True
        if lowered in ("continue", "ok", "你好", "收到", "直接做", "继续"):
            return True
        ignore_phrases = (
            "询问当前是否在做项目",
            "你现在在做项目吗",
            "为什么今天没有做任务",
            "loop engineer",
            "loop-engineer",
            "动态需求合成器",
            "旗舰项目规划器",
            "[loopbuild",
            "猜你想做",
            "继续上一个会话的内容",
            "现在这个项目文件夹做的任务符合我的需求吗",
            "总结一下目前所有的project做的任务",
            "reply with exactly: ok",
            "<task-notification>",
            "<command-name>",
            "<local-command",
            "# agents.md instructions",
            "[工单 #",
            "feedback_loop.py",
        )
        return any(p in lowered for p in ignore_phrases)

    @staticmethod
    def _is_customer_support_ticket(text: str) -> bool:
        lowered = (text or "").lower()
        ticket_markers = (
            "fb-2026",
            "客户 `",
            "客户 #",
            "客户#",
            "误删唯一默认密钥",
            "双扣账单",
            "恢复客户",
            "核验客户",
            "核实客户",
        )
        if any(m in lowered for m in ticket_markers):
            return True
        return bool(re.search(r"客户\s*[^\s]{1,12}\s*\(#\d+\)", lowered))

    @staticmethod
    def _is_private_personal_diary(fname: str, text: str) -> bool:
        blob = f"{fname} {text[:300]}".lower()
        private_markers = ("intimacy", "masculinity", "恋爱", "亲密关系", "前任", "情感内耗")
        return any(m in blob for m in private_markers)

    def _build_signal(
        self,
        prefix: str,
        key: str,
        date_str: str,
        source_type: str,
        raw_title: str,
        raw_summary: str,
        source_path: str,
    ) -> EngineeringSignal:
        clean_title, hits1 = self.privacy_gate.sanitize_text(raw_title)
        clean_summary, hits2 = self.privacy_gate.sanitize_text(raw_summary)
        pillar = self.persona.classify_topic(f"{clean_title} {clean_summary}")
        return EngineeringSignal(
            signal_id=self._make_id(prefix, key),
            date=date_str[:10] if date_str else time.strftime("%Y-%m-%d"),
            source_type=source_type,
            title=clean_title[:96],
            summary=clean_summary[:420],
            pillar=pillar,
            source_path=source_path,
            redacted_rules=sorted(set(hits1 + hits2)),
        )

    def collect_claude_sessions(self, max_sessions: int = 14) -> List[EngineeringSignal]:
        """Extract organic user prompts from Claude Code (`~/.claude/projects/*/*.jsonl`)."""
        if not os.path.isdir(self.claude_projects_dir):
            return []
        candidates = []
        for proj_dir in os.listdir(self.claude_projects_dir):
            if (
                "private-tmp" in proj_dir
                or "Desktop-project" in proj_dir
                or "scratch-workspaces" in proj_dir
            ):
                continue
            full_dir = os.path.join(self.claude_projects_dir, proj_dir)
            if not os.path.isdir(full_dir):
                continue
            ws_tag = self._workspace_tag_from_dir(proj_dir)
            for fname in os.listdir(full_dir):
                if fname.endswith(".jsonl"):
                    fpath = os.path.join(full_dir, fname)
                    try:
                        candidates.append((os.path.getmtime(fpath), ws_tag, fname, fpath))
                    except OSError:
                        pass

        candidates.sort(reverse=True)
        signals: List[EngineeringSignal] = []
        for mtime, ws_tag, fname, fpath in candidates[: max_sessions * 3]:
            if len(signals) >= max_sessions:
                break
            user_turns: List[str] = []
            ts_str = time.strftime("%Y-%m-%d", time.localtime(mtime))
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("type") != "user":
                            continue
                        msg = obj.get("message") or {}
                        content = msg.get("content")
                        if isinstance(content, str):
                            txt = content.strip()
                        elif isinstance(content, list):
                            txt = " ".join(
                                str(c.get("text", ""))
                                for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            ).strip()
                        else:
                            txt = ""
                        txt = re.sub(r"\[Image:[^\]]+\]", "", txt)
                        txt = re.sub(r"\s+", " ", txt).strip()
                        if self._is_noise_or_self_loop(txt) or self._is_customer_support_ticket(txt):
                            continue
                        if obj.get("timestamp"):
                            ts_str = str(obj["timestamp"])[:10]
                        user_turns.append(txt)
                        if len(user_turns) >= 3:
                            break
            except Exception:
                continue

            if user_turns:
                joined = " / ".join(user_turns)
                signals.append(
                    self._build_signal(
                        prefix="claude",
                        key=fname,
                        date_str=ts_str,
                        source_type="claude_session",
                        raw_title=f"[Claude/{ws_tag}] {user_turns[0][:72]}",
                        raw_summary=joined,
                        source_path=fpath,
                    )
                )
        return signals

    def collect_pi_sessions(self, max_sessions: int = 12) -> List[EngineeringSignal]:
        """Scan recent Pi Client JSONL sessions outside `Desktop/project` for organic user prompts."""
        if not os.path.isdir(self.pi_sessions_dir):
            return []
        candidates = []
        for sub in os.listdir(self.pi_sessions_dir):
            if "Desktop-project" in sub or "private-tmp" in sub:
                continue
            sub_dir = os.path.join(self.pi_sessions_dir, sub)
            if not os.path.isdir(sub_dir):
                continue
            ws_tag = self._workspace_tag_from_dir(sub)
            for fname in os.listdir(sub_dir):
                if fname.endswith(".jsonl"):
                    fpath = os.path.join(sub_dir, fname)
                    try:
                        candidates.append((os.path.getmtime(fpath), ws_tag, fname, fpath))
                    except OSError:
                        pass

        candidates.sort(reverse=True)
        signals: List[EngineeringSignal] = []
        for mtime, ws_tag, fname, fpath in candidates[: max_sessions * 2]:
            if len(signals) >= max_sessions:
                break
            user_turns: List[str] = []
            ts_str = fname[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", fname) else time.strftime("%Y-%m-%d", time.localtime(mtime))
            skip_file = False
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("type") == "session_info":
                            sname = str(obj.get("name") or "")
                            if "[LoopBuild" in sname or "猜你想做" in sname:
                                skip_file = True
                                break
                        elif obj.get("type") == "message":
                            msg = obj.get("message") or {}
                            if msg.get("role") == "user":
                                parts = msg.get("content") or []
                                txt = " ".join(
                                    str(p.get("text", ""))
                                    for p in parts
                                    if isinstance(p, dict) and p.get("type") == "text"
                                )
                                txt = re.sub(r"\s+", " ", txt).strip()
                                if self._is_noise_or_self_loop(txt) or self._is_customer_support_ticket(txt):
                                    continue
                                user_turns.append(txt)
                                if len(user_turns) >= 3:
                                    break
            except Exception:
                continue

            if not skip_file and user_turns:
                signals.append(
                    self._build_signal(
                        prefix="pi",
                        key=fname,
                        date_str=ts_str,
                        source_type="pi_session",
                        raw_title=f"[Pi/{ws_tag}] {user_turns[0][:72]}",
                        raw_summary=" / ".join(user_turns),
                        source_path=fpath,
                    )
                )
        return signals

    def collect_recent_transcripts(self, max_conversations: int = 12) -> List[EngineeringSignal]:
        """Scan recent Antigravity `transcript.jsonl` files for organic user requests."""
        if not os.path.isdir(self.agy_brain_dir):
            return []
        candidates = []
        for conv_id in os.listdir(self.agy_brain_dir):
            tpath = os.path.join(
                self.agy_brain_dir, conv_id, ".system_generated", "logs", "transcript.jsonl"
            )
            if os.path.isfile(tpath):
                try:
                    candidates.append((os.path.getmtime(tpath), conv_id, tpath))
                except OSError:
                    pass
        candidates.sort(reverse=True)
        signals: List[EngineeringSignal] = []

        for mtime, conv_id, tpath in candidates[: max_conversations * 2]:
            if len(signals) >= max_conversations:
                break
            user_turns: List[str] = []
            created_at = time.strftime("%Y-%m-%d", time.localtime(mtime))
            try:
                with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("type") == "USER_INPUT":
                            raw_content = str(obj.get("content") or "")
                            req_match = re.search(
                                r"<USER_REQUEST>(.*?)</USER_REQUEST>", raw_content, re.DOTALL
                            )
                            user_text = (
                                req_match.group(1).strip() if req_match else raw_content.strip()
                            )
                            user_text = re.sub(r"\s+", " ", user_text)
                            if self._is_noise_or_self_loop(user_text) or self._is_customer_support_ticket(user_text):
                                continue
                            if obj.get("created_at"):
                                created_at = str(obj["created_at"])[:10]
                            user_turns.append(user_text)
                            if len(user_turns) >= 3:
                                break
            except Exception:
                continue

            if user_turns:
                signals.append(
                    self._build_signal(
                        prefix="agy",
                        key=conv_id,
                        date_str=created_at,
                        source_type="agy_transcript",
                        raw_title=f"[AGY] {user_turns[0][:72]}",
                        raw_summary=" / ".join(user_turns),
                        source_path=tpath,
                    )
                )
        return signals

    def collect_codex_sessions(self, max_sessions: int = 8) -> List[EngineeringSignal]:
        """Scan recent Codex CLI sessions (`~/.codex/sessions/**/*.jsonl`) for organic user prompts."""
        if not os.path.isdir(self.codex_sessions_dir):
            return []
        files = glob.glob(os.path.join(self.codex_sessions_dir, "**", "*.jsonl"), recursive=True)
        candidates = []
        for fpath in files:
            try:
                candidates.append((os.path.getmtime(fpath), os.path.basename(fpath), fpath))
            except OSError:
                pass
        candidates.sort(reverse=True)
        signals: List[EngineeringSignal] = []

        for mtime, fname, fpath in candidates[: max_sessions * 2]:
            if len(signals) >= max_sessions:
                break
            user_turns: List[str] = []
            ts_str = time.strftime("%Y-%m-%d", time.localtime(mtime))
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            continue
                        if obj.get("timestamp"):
                            ts_str = str(obj["timestamp"])[:10]
                        pl = obj.get("payload") or {}
                        if obj.get("type") == "response_item" and pl.get("role") == "user":
                            parts = pl.get("content") or []
                            txt = " ".join(
                                str(c.get("text", ""))
                                for c in parts
                                if isinstance(c, dict) and c.get("type") in ("input_text", "text")
                            )
                            txt = re.sub(r"\s+", " ", txt).strip()
                            if (
                                txt.startswith("<environment_context>")
                                or self._is_noise_or_self_loop(txt)
                                or self._is_customer_support_ticket(txt)
                            ):
                                continue
                            user_turns.append(txt)
                            if len(user_turns) >= 3:
                                break
            except Exception:
                continue

            if user_turns:
                signals.append(
                    self._build_signal(
                        prefix="codex",
                        key=fname,
                        date_str=ts_str,
                        source_type="codex_session",
                        raw_title=f"[Codex] {user_turns[0][:72]}",
                        raw_summary=" / ".join(user_turns),
                        source_path=fpath,
                    )
                )
        return signals

    def collect_thought_diaries(self) -> List[EngineeringSignal]:
        """Parse cognitive models, product intuition, and quant insights from `~/Documents/diary/`."""
        if not os.path.isdir(self.diary_dir):
            return []
        signals: List[EngineeringSignal] = []
        for fname in sorted(os.listdir(self.diary_dir), reverse=True):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(self.diary_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            if self._is_private_personal_diary(fname, text):
                continue

            date_match = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", fname)
            date_str = date_match.group(1) if date_match else "2026-10-01"
            heading_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            raw_title = heading_match.group(1).strip() if heading_match else fname
            body_preview = re.sub(r"\s+", " ", text[:700]).strip()
            signals.append(
                self._build_signal(
                    prefix="diary",
                    key=fname,
                    date_str=date_str,
                    source_type="thought_diary",
                    raw_title=f"[Diary] {raw_title}",
                    raw_summary=body_preview,
                    source_path=fpath,
                )
            )
        return signals

    def _parse_conversation_markdown(self, md_path: str, limit: int = 20) -> List[EngineeringSignal]:
        if not os.path.exists(md_path):
            return []
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return []

        pattern = re.compile(
            r"^###\s+(\d{4}-\d{2}-\d{2})\s+·\s+([^\n]+)\n"
            r"(?:-\s+状态：[^\n]*\n)?"
            r"(?:-\s+Agent：[^\n]*\n)?"
            r"-\s+摘要：([^\n]+)",
            re.MULTILINE,
        )
        signals: List[EngineeringSignal] = []
        for match in pattern.finditer(content):
            if len(signals) >= limit:
                break
            date_str = match.group(1).strip()
            raw_title = match.group(2).strip()
            raw_summary = re.sub(r"\s+", " ", match.group(3).strip())
            blob = f"{raw_title} {raw_summary}"
            if self._is_noise_or_self_loop(blob) or self._is_customer_support_ticket(blob):
                continue
            signals.append(
                self._build_signal(
                    prefix="conv",
                    key=f"{date_str}:{raw_title}",
                    date_str=date_str,
                    source_type="recent_conversation",
                    raw_title=raw_title,
                    raw_summary=raw_summary,
                    source_path=md_path,
                )
            )
        return signals

    def collect_recent_conversations(self) -> List[EngineeringSignal]:
        """Parse architectural/exploration entries from `recent-conversations.md`."""
        active = self._parse_conversation_markdown(self.recent_conv_path, limit=20)
        archived = self._parse_conversation_markdown(self.archive_conv_path, limit=12)
        return active + archived

    def collect_all(self) -> List[EngineeringSignal]:
        """Collect, deduplicate, and rank organic signals across all cross-agent sources."""
        raw_user_signals = (
            self.collect_claude_sessions()
            + self.collect_pi_sessions()
            + self.collect_recent_transcripts()
            + self.collect_codex_sessions()
            + self.collect_thought_diaries()
            + self.collect_recent_conversations()
        )
        source_weight = {
            "claude_session": 6,
            "pi_session": 6,
            "agy_transcript": 6,
            "codex_session": 6,
            "thought_diary": 5,
            "recent_conversation": 3,
        }
        seen = set()
        unique: List[EngineeringSignal] = []
        for sig in raw_user_signals:
            if sig.signal_id not in seen:
                seen.add(sig.signal_id)
                unique.append(sig)

        unique.sort(key=lambda s: (s.date, source_weight.get(s.source_type, 1)), reverse=True)
        return unique
