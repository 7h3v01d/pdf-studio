"""
undo_stack.py
-------------
Bounded command stack for undoable / redoable document operations.

Native PDF changes such as signatures and stamps may carry compressed before / after
snapshots.  The stack therefore enforces both a command-count limit and a total
payload budget so repeated edits cannot consume unbounded memory.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


MAX_HISTORY = 100
MAX_HISTORY_BYTES = 128 * 1024 * 1024


@dataclass
class Command:
    kind: str
    redo_data: Any
    undo_data: Any


def _payload_size(value: Any, seen: set[int] | None = None) -> int:
    """Estimate retained binary/container payload without importing heavy tools."""
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)
    if isinstance(value, dict):
        return sum(_payload_size(key, seen) + _payload_size(item, seen)
                   for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return sum(_payload_size(item, seen) for item in value)
    return 0


def command_payload_size(command: Command) -> int:
    return _payload_size(command.undo_data) + _payload_size(command.redo_data)


class UndoStack:
    def __init__(self, *, max_history: int = MAX_HISTORY,
                 max_history_bytes: int = MAX_HISTORY_BYTES):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self.max_history = max(1, int(max_history))
        self.max_history_bytes = max(1, int(max_history_bytes))

    def _trim(self):
        while len(self._undo) > self.max_history:
            self._undo.pop(0)
        while self._undo and sum(command_payload_size(c) for c in self._undo) > self.max_history_bytes:
            self._undo.pop(0)

    def push(self, cmd: Command):
        self._undo.append(cmd)
        self._redo.clear()
        self._trim()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def peek_undo(self) -> Command | None:
        return self._undo[-1] if self._undo else None

    def peek_redo(self) -> Command | None:
        return self._redo[-1] if self._redo else None

    def pop_undo(self) -> Command | None:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        self._redo.append(cmd)
        return cmd

    def pop_redo(self) -> Command | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        self._undo.append(cmd)
        return cmd

    def snapshot(self) -> tuple[list[Command], list[Command]]:
        """Return a shallow command snapshot for document-open rollback."""
        return (list(self._undo), list(self._redo))

    def restore(self, snapshot: tuple[list[Command], list[Command]]) -> None:
        undo, redo = snapshot
        self._undo = list(undo)
        self._redo = list(redo)
        self._trim()

    def clear(self):
        self._undo.clear()
        self._redo.clear()
