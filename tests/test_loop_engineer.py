"""
Unit test suite for `loop-engineer`.
"""

import os
import tempfile

import pytest

from loop_engineer.collector import ConversationCollector, EngineeringSignal
from loop_engineer.github_sync import GitHubSyncManager
from loop_engineer.persona import DEFAULT_PERSONA
from loop_engineer.planner import WeeklyPlanner, build_default_weekly_projects
from loop_engineer.privacy import PrivacyGate


def test_privacy_gate_redacts_secrets_and_pii():
    import json

    with tempfile.TemporaryDirectory() as tmpdir:
        deny = os.path.join(tmpdir, "deny.json")
        mock_sid = "88" + "776655"
        with open(deny, "w", encoding="utf-8") as f:
            json.dump({"student_id": [mock_sid]}, f)

        gate = PrivacyGate(denylist_path=deny)
        mock_email = "alice.mock" + "@" + "university.edu"
        mock_key = "sk-" + "abc1234567890def"
        mock_ip = "203.0." + "114.99"
        mock_wx = "WX:" + "demo_handle"
        raw = f"Student {mock_sid} with email {mock_email} used key {mock_key} on node {mock_ip} and {mock_wx}."
        sanitized, hits = gate.sanitize_text(raw)
        assert mock_sid not in sanitized
        assert mock_email not in sanitized
        assert mock_key not in sanitized
        assert mock_ip not in sanitized
        assert mock_wx not in sanitized
        assert set(hits) >= {
            "student_id",
            "campus_and_personal_email",
            "openai_or_gateway_api_key",
            "private_ips_and_hosts",
            "private_handles",
        }

        with pytest.raises(ValueError):
            gate.assert_clean(raw, context="unit_test")


def test_persona_topic_classification():
    assert DEFAULT_PERSONA.classify_topic("Moodle and Edstem attendance MCP tool") == "workflow-mcp"
    assert DEFAULT_PERSONA.classify_topic("Claude 5h/7d quota gateway router and BrokenPipe") == "ai-infra-harness"
    assert DEFAULT_PERSONA.classify_topic("Solidity EVM vault and BTC perpetuals funding rate") == "quant-fintech-web3"
    assert DEFAULT_PERSONA.classify_topic("Perishable capacity arbitrage transaction-cost model") == "cognitive-systems"


def test_weekly_planner_ingests_signals_and_tracks_milestones():
    with tempfile.TemporaryDirectory() as tmpdir:
        planner = WeeklyPlanner(state_dir=tmpdir)
        projects = planner.load_or_init_projects()
        assert len(projects) == 6
        modes = {p.mode for p in projects}
        assert modes == {"self_optimize", "extrapolate_new"}

        dummy_signal = EngineeringSignal(
            signal_id="conv-12345",
            date="2026-10-25",
            source_type="recent_conversation",
            title="Troubleshoot Wi-Fi and Misty proxy routing",
            summary="Check IPv6 and split-tunnel routing on home network.",
            pillar="workflow-mcp",
            source_path="/tmp/mock.md",
        )
        counts = planner.ingest_signals([dummy_signal])
        assert counts["netmap"] == 1

        next_item = planner.next_actionable_milestone(repo_name="netmap")
        assert next_item is not None
        ms_id = next_item["milestone"].milestone_id
        assert ms_id == "nm-m1"

        assert planner.mark_milestone_completed(ms_id, "2026-10-25T00:45:00+08:00")
        next_after = planner.next_actionable_milestone(repo_name="netmap")
        assert next_after["milestone"].milestone_id == "nm-m2"


def test_signal_synthesizer_creates_new_projects_and_merges_llm_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        planner = WeeklyPlanner(state_dir=tmpdir)
        planner.load_or_init_projects()

        new_signals = [
            EngineeringSignal(
                signal_id="conv-vault-01",
                date="2026-10-25",
                source_type="recent_conversation",
                title="落地私有邮箱与 OAuth 令牌保险箱及免 AdsPower 浏览器启动器",
                summary="支持微软 OAuth2 IMAP 提取 6 位验证码与 Magic Link，固定端口 SOCKS5 桥接。",
                pillar="ai-infra-harness",
                source_path="/tmp/mock.md",
            ),
            EngineeringSignal(
                signal_id="conv-omni-02",
                date="2026-10-25",
                source_type="recent_conversation",
                title="解析 omni-moderation 内容安全前置审核与满 3 次自动进蜜罐 Tarpit 机制",
                summary="剥离代码块实现零误伤，三次违规拉入 Tarpit。",
                pillar="ai-infra-harness",
                source_path="/tmp/mock.md",
            ),
        ]
        created = planner.auto_synthesize_from_signals(new_signals)
        assert "oie-m1" in created
        assert "let-m1" in created

        llm_added = planner.merge_llm_synthesized_plan(
            [
                {
                    "repo_name": "custom-synth-repo",
                    "pillar": "ai-infra-harness",
                    "mode": "extrapolate_new",
                    "tagline": "Test synthesized repo",
                    "milestones": [
                        {
                            "milestone_id": "csr-m1",
                            "commit_type": "feat",
                            "scope": "core",
                            "summary": "implement core logic",
                            "deliverables": ["csr/core.py", "tests/test_core.py"],
                        }
                    ],
                }
            ]
        )
        assert llm_added == ["csr-m1"]


def test_git_sync_commit_and_author_rewrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "repo")
        state_dir = os.path.join(tmpdir, "state")
        sync = GitHubSyncManager(root_dir=repo_dir, state_dir=state_dir)
        sync.ensure_git_repo(repo_dir)

        sample_file = os.path.join(repo_dir, "hello.py")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("x = 42\n")

        committed, rev = sync.commit_files(repo_dir, ["hello.py"], "feat(core): add sample module")
        assert committed is True
        assert len(rev) >= 6

        sync.rewrite_author_history(repo_dir, "new_blank_user", "new_blank_user@users.noreply.github.com")
        cfg = sync.load_account_config()
        assert cfg["bound"] is False


def test_cross_agent_collector_and_noise_filters():
    import json
    from loop_engineer.collector import ConversationCollector

    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = os.path.join(tmpdir, "claude")
        ws_dir = os.path.join(claude_dir, "-Users-demo-Desktop-colab")
        os.makedirs(ws_dir, exist_ok=True)
        with open(os.path.join(ws_dir, "s1.jsonl"), "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-11-12T10:00:00Z",
                        "message": {
                            "role": "user",
                            "content": "我想把 6-stem 音轨分离结果自动对齐成可试听的混音工程，每次手动拖轨道太费劲了",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-11-12T10:05:00Z",
                        "message": {"role": "user", "content": "核验客户 #999 误删唯一默认密钥"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        diary_dir = os.path.join(tmpdir, "diary")
        os.makedirs(diary_dir, exist_ok=True)
        with open(os.path.join(diary_dir, "2026-11-01-intimacy-reflection.md"), "w", encoding="utf-8") as f:
            f.write("# 亲密关系反思\n个人隐私内容不应进入公开孵化信号。")
        with open(os.path.join(diary_dir, "2026-11-02-product-intuition.md"), "w", encoding="utf-8") as f:
            f.write("# 工具设计直觉\n好的开发者工具应该一眼看清状态摩擦。")

        collector = ConversationCollector(
            recent_conv_path=os.path.join(tmpdir, "none.md"),
            archive_conv_path=os.path.join(tmpdir, "none2.md"),
            diary_dir=diary_dir,
            agy_brain_dir=os.path.join(tmpdir, "no_agy"),
            pi_sessions_dir=os.path.join(tmpdir, "no_pi"),
            claude_projects_dir=claude_dir,
            codex_sessions_dir=os.path.join(tmpdir, "no_codex"),
        )
        sigs = collector.collect_all()
        assert len(sigs) == 2
        titles = " ".join(s.title for s in sigs)
        assert "6-stem" in titles
        assert "工具设计直觉" in titles
        assert "亲密关系" not in titles
        assert "误删唯一默认密钥" not in titles


def test_anti_monotony_rotation_and_clean_dialog_prompts():
    from loop_engineer.daemon import DEFAULT_PI_MODEL, DEFAULT_THINKING, LoopDaemon

    with tempfile.TemporaryDirectory() as tmpdir:
        planner = WeeklyPlanner(state_dir=tmpdir)
        planner.load_or_init_projects()

        # Blacklisted or live production targets must be rejected or redirected safely
        rejected = planner.merge_llm_synthesized_plan(
            [
                {
                    "repo_name": "frictionlab",
                    "milestones": [{"milestone_id": "fl-999", "deliverables": ["a.py"]}],
                }
            ]
        )
        assert rejected == []

        added = planner.merge_llm_synthesized_plan(
            [
                {
                    "repo_name": "harness-bench-matrix",
                    "mode": "extrapolate_new",
                    "local_target_dir": os.path.expanduser("~/Desktop/cs/api"),
                    "chat_title": "猜你想做 · 多端模型延迟与缓存对照台 (harness-bench-matrix)",
                    "user_voice_prompt": "我最近在对比 Claude Code、Pi 和 Antigravity 调不同模型的首字速度和缓存命中率，帮我做个一键跑对照表的小工具。",
                    "milestones": [
                        {
                            "milestone_id": "hbm-m1",
                            "commit_type": "feat",
                            "scope": "mvp",
                            "summary": "build benchmark runner and CLI matrix report",
                            "deliverables": ["bench/runner.py", "tests/test_runner.py"],
                        }
                    ],
                }
            ]
        )
        assert added == ["hbm-m1"]
        nxt = planner.next_actionable_milestone(repo_name="harness-bench-matrix")
        assert "/Desktop/cs/api" not in nxt["project"].local_target_dir
        assert "workspaces/harness-bench-matrix" in nxt["project"].local_target_dir

        daemon = LoopDaemon(root_dir=tmpdir, state_dir=tmpdir, pi_model="local-gateway/claude-opus-5-5-high")
        assert daemon.pi_model == DEFAULT_PI_MODEL == "local-gateway/claude-opus-5-5"
        assert daemon.thinking_level == DEFAULT_THINKING == "high"
        user_msg = daemon.build_milestone_user_prompt(nxt["project"], nxt["milestone"])
        sys_msg = daemon.build_milestone_system_prompt(nxt["project"], nxt["milestone"])
        assert user_msg.startswith("我最近在对比")
        assert "GitHubSyncManager" not in user_msg
        assert "GitHubSyncManager" in sys_msg
        assert "### 1. 我猜你的需求是什么" in sys_msg

