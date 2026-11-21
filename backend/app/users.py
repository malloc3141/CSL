"""Nickname login: who a learner is, and which sessions are theirs.

    POST /api/users/login {name}        -> {user, created}   the nickname is the whole login (no password)
    GET  /api/users/{userId}            -> user              404 if the id is not known (any more)
    GET  /api/users/{userId}/sessions   -> the user's sessions, newest first

This identifies learners and lets them find their sessions again from any browser. It is not access
control: whoever knows a nickname can sign in as it, and a session can still be opened by its id alone.
Creating a session without a user stays possible (POST /api/sessions without `userId`).
"""
from __future__ import annotations

import unicodedata
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .protocol import LoginRequest, LoginResponse, SessionSummary, User
from .session import new_id
from .store import Store

NAME_MIN, NAME_MAX = 2, 20


def clean_name(raw: str) -> str:
    """The nickname as stored and shown: Unicode-normalized, inner whitespace collapsed, trimmed."""
    return " ".join(unicodedata.normalize("NFKC", raw).split())


def name_key(name: str) -> str:
    """What makes two nicknames the same one: case does not count ("Minsu" = "minsu")."""
    return name.casefold()


def users_router() -> APIRouter:
    router = APIRouter(prefix="/api/users")

    @router.post("/login")
    async def login(body: LoginRequest, request: Request) -> dict[str, Any]:
        name = clean_name(body.name)
        if not NAME_MIN <= len(name) <= NAME_MAX or not name.isprintable():
            raise HTTPException(422, f"A nickname has {NAME_MIN} to {NAME_MAX} characters.")
        store: Store = request.app.state.store
        row, created = await store.login_user(new_id(), name, name_key(name))
        return LoginResponse(user=User.model_validate(row), created=created).wire()

    @router.get("/{user_id}")
    async def get_user(user_id: str, request: Request) -> dict[str, Any]:
        row = await request.app.state.store.get_user(user_id)
        if row is None:
            raise HTTPException(404, "Unknown user.")
        return User.model_validate(row).wire()

    @router.get("/{user_id}/sessions")
    async def user_sessions(user_id: str, request: Request) -> list[dict[str, Any]]:
        store: Store = request.app.state.store
        if await store.get_user(user_id) is None:
            raise HTTPException(404, "Unknown user.")
        runners = request.app.state.registry.runners
        out = []
        for row in await store.list_user_sessions(user_id):
            item = SessionSummary.model_validate(row)
            runner = runners.get(item.session_id)
            if runner is not None:  # in memory: fresher than the last save
                s = runner.session
                item.phase, item.status, item.message_count = s.phase, s.status, len(s.messages)
            out.append(item.wire())
        return out

    return router
