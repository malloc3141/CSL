"""Run one session in the terminal: no web server, no frontend.
For trying a pipeline while developing it.

    python scripts/cli.py "Why is summer hotter than winter?"
    python scripts/cli.py "여름은 왜 겨울보다 더운가?" --lang ko --pipeline baseline --auto
    python scripts/cli.py "..." --pipeline mypkg.pipeline:MyPipeline

While it runs:
    <Enter>        next message (step mode) / start the discussion
    some text      say it (initialization reply, or a message in the discussion)
    /auto          let the discussion run by itself        /step   back to step mode
    /pause /resume /state /quit
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.orchestrator import Connection, SessionRegistry  # noqa: E402
from app.pipeline import load_pipeline  # noqa: E402
from app.protocol import CLIENT_COMMANDS  # noqa: E402
from app.store import Store  # noqa: E402


def show_state(agent: str, state: dict) -> None:
    print(f"  [{agent}]")
    for b in state["beliefs"]:
        print(f"    belief   ({b['accuracy'] or '-'}) {b['text']}")
    print(f"    explains ({state['explanationAccuracy'] or '-'}) {state['explanation']}")
    for q in state["openQuestions"]:
        print(f"    asks     {q}")


async def printer(conn: Connection, names: dict[str, str]) -> None:
    while True:
        event = await conn.queue.get()
        if event is None:
            return
        kind, data = event["type"], event["data"]
        if kind == "turn.started":
            print(f"\n{data['speakerName']}: ", end="", flush=True)
        elif kind == "message.delta":
            print(data["text"], end="", flush=True)
        elif kind == "message.completed":
            m = data["message"]
            print(f"\n{m['speakerName']}: {m['text']}" if m["role"] == "user" else "", flush=True)
        elif kind == "turn.cancelled":
            print(f"  ... ({data['reason']})", flush=True)
        elif kind == "classroom.ready":
            print(f"\n--- classroom (focus: {data['focus']}) ---")
            for p in data["participants"]:
                names[p["id"]] = p["name"]
                print(f"  {p['name']} [{p['role']}] {p['origin'] or ''} | {p['description'] or ''}")
            for agent, version in data["states"].items():
                show_state(names.get(agent, agent), version["state"])
            print("--- press Enter to start the discussion ---")
        elif kind == "state.updated":
            u = data["update"]
            print(f"  ~ {names.get(u['agentId'], u['agentId'])} state v{u['version']}")
            for ch in u["changes"]:
                print(f"      {ch['field']} {ch['kind']}: {ch['after'] or ch['before']}")
        elif kind == "user.invited":
            print("  (the tutor is waiting for your explanation: type it, or Enter to pass)")
        elif kind == "phase.changed":
            print(f"\n=== phase: {data['phase']}{' (' + data['reason'] + ')' if data['reason'] else ''} ===")
        elif kind == "status.changed":
            print(f"  [{data['status']}]", flush=True)
        elif kind == "error":
            print(f"\n!! {data['code']}: {data['message']}", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("topic")
    parser.add_argument("--lang", choices=["ko", "en"], default="en")
    parser.add_argument("--pipeline", help="mock | baseline | module:Class (default: PIPELINE from .env)")
    parser.add_argument("--auto", action="store_true", help="run by itself instead of step by step")
    args = parser.parse_args()

    settings = get_settings()
    settings.debug = True
    if args.pipeline:
        settings.pipeline = args.pipeline
    store = Store(":memory:")
    await store.start()
    registry = SessionRegistry(settings, store, load_pipeline(settings))
    runner = registry.create(args.topic, args.lang)
    conn = Connection()
    runner.attach(conn)
    names: dict[str, str] = {}
    print_task = asyncio.create_task(printer(conn, names))

    def send(type_: str, **data) -> None:
        runner.submit(type_, CLIENT_COMMANDS[type_].model_validate(data))

    if not args.auto:
        send("control.set_pace", auto=False)
    print(f"pipeline: {registry.pipeline.name} | {'auto' if args.auto else 'step'} mode | /quit to exit")
    try:
        while True:
            line = (await asyncio.to_thread(sys.stdin.readline))
            if not line:  # EOF
                break
            line = line.strip()
            phase = runner.session.phase
            if line == "/quit":
                break
            elif line == "/auto":
                send("control.set_pace", auto=True)
            elif line == "/step":
                send("control.set_pace", auto=False)
            elif line == "/pause":
                send("control.pause")
            elif line == "/resume":
                send("control.resume")
            elif line == "/state":
                for agent, versions in runner.session.states.items():
                    show_state(names.get(agent, agent), versions[-1].state.wire())
            elif phase == "init":
                send("init.reply", text=line) if line else send("control.resume")
            elif phase in ("building", "ready"):
                send("discussion.start" if phase == "ready" else "control.resume")
            elif phase == "discussion":
                send("user.message", text=line) if line else send("control.step")
            else:
                break
    finally:
        await registry.stop()
        print_task.cancel()
        await store.stop()


if __name__ == "__main__":
    asyncio.run(main())
