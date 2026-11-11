"""Generate frontend/src/lib/csl/protocol.ts from app/protocol.py.

    python scripts/gen_ts.py            # write the file
    python scripts/gen_ts.py --check    # exit 1 if the file is out of date
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic.alias_generators import to_camel  # noqa: E402

from app import protocol as P  # noqa: E402

OUT = ROOT.parent / "frontend" / "src" / "lib" / "csl" / "protocol.ts"
NAMED = {get_args(t): name for name, t in P.NAMED_TYPES.items()}
# Models the client sends: fields with defaults become optional there.
INPUT_MODELS = set(P.CLIENT_COMMANDS.values()) | {P.CreateSessionRequest}


def ts_type(tp: Any, seen: list[type]) -> str:
    origin = get_origin(tp)
    if tp is Any:
        return "unknown"
    if tp is type(None):
        return "null"
    if tp is str:
        return "string"
    if tp in (int, float):
        return "number"
    if tp is bool:
        return "boolean"
    if origin is Literal:
        args = get_args(tp)
        if args in NAMED:
            return NAMED[args]
        return " | ".join(f'"{a}"' if isinstance(a, str) else str(a).lower() for a in args)
    if origin in (Union, types.UnionType):
        return " | ".join(ts_type(a, seen) for a in get_args(tp))
    if origin is list:
        inner = ts_type(get_args(tp)[0], seen)
        return f"({inner})[]" if " | " in inner else f"{inner}[]"
    if origin is dict:
        return f"Record<string, {ts_type(get_args(tp)[1], seen)}>"
    if isinstance(tp, type) and issubclass(tp, P.Wire):
        if tp not in seen:
            seen.append(tp)
        return tp.__name__
    raise TypeError(f"gen_ts.py cannot translate {tp!r}")


def interface(model: type[P.Wire], seen: list[type]) -> str:
    lines = []
    if not model.model_fields:
        return f"export type {model.__name__} = Record<string, never>;"
    for name, field in model.model_fields.items():
        optional = "?" if model in INPUT_MODELS and not field.is_required() else ""
        lines.append(f"  {to_camel(name)}{optional}: {ts_type(field.annotation, seen)};")
    return f"export interface {model.__name__} {{\n" + "\n".join(lines) + "\n}"


def generate() -> str:
    seen: list[type] = []
    roots = [*P.SERVER_EVENTS.values(), *P.CLIENT_COMMANDS.values(), *P.REST_MODELS]
    for m in roots:
        if m not in seen:
            seen.append(m)
    blocks: list[str] = []
    i = 0
    while i < len(seen):  # `seen` grows as nested models are discovered
        blocks.append(interface(seen[i], seen))
        i += 1
    aliases = [
        f"export type {name} = " + " | ".join(f'"{a}"' for a in get_args(t)) + ";"
        for name, t in P.NAMED_TYPES.items()
    ]
    events = "\n".join(
        f'  | {{ type: "{t}"; seq: number | null; ts: number; data: {m.__name__} }}'
        for t, m in P.SERVER_EVENTS.items()
    )
    commands = "\n".join(
        f'  | {{ type: "{t}"; data{"?" if not m.model_fields else ""}: {m.__name__} }}'
        for t, m in P.CLIENT_COMMANDS.items()
    )
    return (
        "// AUTO-GENERATED from backend/app/protocol.py by backend/scripts/gen_ts.py. Do not edit.\n\n"
        f"export const PROTOCOL_VERSION = {P.PROTOCOL_VERSION};\n\n"
        + "\n".join(aliases)
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n/** Everything the server sends over the WebSocket. `seq` is null for events that are not logged. */\n"
        + f"export type ServerEvent =\n{events};\n\n"
        + "/** Everything the client may send over the WebSocket. */\n"
        + f"export type ClientCommand =\n{commands};\n"
    )


if __name__ == "__main__":
    text = generate()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{OUT} is out of date. Run: python scripts/gen_ts.py")
            sys.exit(1)
        print("protocol.ts is up to date")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT}")
