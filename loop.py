#!/usr/bin/env python3
"""
Loop Engineer CLI Entrypoint (Powered by Pi Agent: local-gateway/claude-opus-5-5, thinking=high).

Commands:
  python3 loop.py status              # Inspect collected signals, quota, and next project
  python3 loop.py poll                # Run one silent cross-agent signal collection cycle (0 tokens)
  python3 loop.py synthesize          # Infer 1 new project from cross-agent conversations (--no-session)
  python3 loop.py trigger --force     # Immediately synthesize (if needed) & build 1 project via Pi
  python3 loop.py run-plan --detach   # Detach background Pi sequential runner
  python3 loop.py start-daemon        # Start lightweight detached background daemon
  python3 loop.py stop-daemon         # Stop background daemon and any detached runner
"""

import argparse
import json
import os
import signal

from loop_engineer.daemon import DEFAULT_DAILY_QUOTA, DEFAULT_PI_MODEL, DEFAULT_THINKING, LoopDaemon


def main() -> None:
    parser = argparse.ArgumentParser(description="Loop Engineer — Subtext-Driven Autonomous GitHub Builder")
    parser.add_argument(
        "command",
        choices=[
            "status",
            "poll",
            "synthesize",
            "trigger",
            "run-plan",
            "start-daemon",
            "stop-daemon",
            "complete-milestone",
        ],
    )
    parser.add_argument("--interval", type=int, default=1800, help="Daemon poll interval in seconds (default: 1800)")
    parser.add_argument("--model", type=str, default=DEFAULT_PI_MODEL, help=f"Pi model ID (default: {DEFAULT_PI_MODEL})")
    parser.add_argument("--thinking", type=str, default=DEFAULT_THINKING, help=f"Pi thinking level (default: {DEFAULT_THINKING})")
    parser.add_argument("--daily-quota", type=int, default=DEFAULT_DAILY_QUOTA, help=f"Max projects/day (default: {DEFAULT_DAILY_QUOTA})")
    parser.add_argument("--force", action="store_true", help="Bypass daily quota limit when triggering Pi")
    parser.add_argument("--detach", action="store_true", help="Run `run-plan` in detached background mode")
    parser.add_argument("--max-count", type=int, default=2, help="Max milestones to run in `run-plan`")
    parser.add_argument("--repo", type=str, default=None, help="Target a specific repo_name when triggering")
    parser.add_argument("--milestone-id", type=str, default="", help="Milestone ID to mark completed")
    args = parser.parse_args()

    daemon = LoopDaemon(
        pi_model=args.model,
        thinking_level=args.thinking,
        daily_quota=args.daily_quota,
    )

    if args.command in ("status", "poll"):
        status = daemon.run_poll_and_sync_cycle(auto_dispatch=False)
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif args.command == "synthesize":
        signals = daemon.collector.collect_all()
        added = daemon.synthesize_milestones_via_pi(signals)
        nxt = daemon.planner.next_actionable_milestone()
        out = {
            "signals_scanned": len(signals),
            "synthesized_milestones": added,
            "next": (
                {
                    "repo_name": nxt["project"].repo_name,
                    "chat_title": nxt["milestone"].chat_title,
                    "tagline": nxt["project"].tagline,
                    "origin_context": nxt["project"].origin_context,
                    "user_voice_prompt": nxt["milestone"].user_voice_prompt,
                    "deliverables": nxt["milestone"].deliverables,
                }
                if nxt
                else None
            ),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.command == "trigger":
        daemon.run_poll_and_sync_cycle(auto_dispatch=False)
        res = daemon.dispatch_next_milestone_to_model(force=args.force, repo_name=args.repo)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.command == "run-plan":
        daemon.run_poll_and_sync_cycle(auto_dispatch=False)
        if args.detach:
            pid = daemon.start_plan_runner_detached(max_count=args.max_count)
            print(f"Detached Pi sequential plan runner started (PID={pid}, model={daemon.pi_model}, thinking={daemon.thinking_level})")
        else:
            results = daemon.run_all_pending_milestones(max_count=args.max_count)
            print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.command == "start-daemon":
        pid = daemon.start_detached(interval_seconds=args.interval)
        print(f"Loop Engineer daemon running in background (PID={pid}, model={daemon.pi_model}, thinking={daemon.thinking_level})")
    elif args.command == "stop-daemon":
        stopped = []
        for pfile in (daemon.pid_file, daemon.runner_pid_file):
            if os.path.exists(pfile):
                try:
                    pid = int(open(pfile, "r", encoding="utf-8").read().strip())
                    os.kill(pid, signal.SIGTERM)
                    os.remove(pfile)
                    stopped.append(pid)
                except Exception:
                    pass
        print(f"Stopped PIDs: {stopped}" if stopped else "No active daemon/runner running.")
    elif args.command == "complete-milestone":
        import time

        ok = daemon.planner.mark_milestone_completed(args.milestone_id, time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        print(f"Milestone {args.milestone_id} marked completed: {ok}")


if __name__ == "__main__":
    main()
