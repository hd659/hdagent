#!/usr/bin/env python3
"""
hdagent CLI — Digital Self Kernel & Parallel Autonomous Clone Dispatcher.

Commands:
  python3 hdagent.py profile             # Inspect persistent Digital Self Kernel (`self_core.json`)
  python3 hdagent.py learn --force       # Distill unseen cross-agent conversations into SelfCore (--no-session)
  python3 hdagent.py proposals           # List L1/L2/L3 autonomy action proposals
  python3 hdagent.py status              # Poll 0-token cross-agent signals & inspect runtime status
  python3 hdagent.py synthesize          # Infer 1 new project as Digital Self (--no-session)
  python3 hdagent.py trigger --force     # Spawn an execution clone to build & ship next project
  python3 hdagent.py start-daemon        # Start detached background hdagent daemon
  python3 hdagent.py stop-daemon         # Stop background hdagent daemon
"""

import argparse
import json
import os
import signal
import time

from loop_engineer.daemon import DEFAULT_DAILY_QUOTA, DEFAULT_PI_MODEL, DEFAULT_THINKING, LoopDaemon


def main() -> None:
    parser = argparse.ArgumentParser(description="hdagent — Digital Self Kernel & Parallel Clone Engine")
    parser.add_argument(
        "command",
        choices=[
            "profile",
            "learn",
            "proposals",
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
    parser.add_argument("--force", action="store_true", help="Force immediate distillation or bypass daily quota")
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

    if args.command == "profile":
        signals = daemon.collector.collect_all()
        daemon.self_core.absorb_signals_fast(signals)
        print(json.dumps(daemon.self_core.load(), ensure_ascii=False, indent=2))
    elif args.command == "learn":
        signals = daemon.collector.collect_all()
        res = daemon.self_core.distill_delta_via_pi(
            signals,
            pi_model=daemon.pi_model,
            thinking_level=daemon.thinking_level,
            force=args.force,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.command == "proposals":
        print(json.dumps(daemon.self_core.list_proposals(), ensure_ascii=False, indent=2))
    elif args.command in ("status", "poll"):
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
            print(f"Detached hdagent runner started (PID={pid}, model={daemon.pi_model}, thinking={daemon.thinking_level})")
        else:
            results = daemon.run_all_pending_milestones(max_count=args.max_count)
            print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.command == "start-daemon":
        pid = daemon.start_detached(interval_seconds=args.interval)
        print(f"hdagent daemon running in background (PID={pid}, model={daemon.pi_model}, thinking={daemon.thinking_level})")
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
        print(f"Stopped PIDs: {stopped}" if stopped else "No active hdagent daemon running.")
    elif args.command == "complete-milestone":
        ok = daemon.planner.mark_milestone_completed(args.milestone_id, time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        print(f"Milestone {args.milestone_id} marked completed: {ok}")


if __name__ == "__main__":
    main()
