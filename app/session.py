# app/session.py
from __future__ import annotations
import uuid

# ── 매우 단순한 인-메모리 캐시 (프로토타입용) ──
_PENDING: dict[str, dict] = {}   # key = conv_id, value = partial params

def new_id() -> str:
    return str(uuid.uuid4())

def get(conv_id: str) -> dict | None:
    return _PENDING.get(conv_id)

def set(conv_id: str, params: dict):
    _PENDING[conv_id] = params

def clear(conv_id: str):
    _PENDING.pop(conv_id, None)
