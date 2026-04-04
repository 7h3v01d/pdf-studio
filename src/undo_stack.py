"""
undo_stack.py
-------------
Lightweight command stack for undoable/redoable operations.

Supported command kinds
-----------------------
  annotation_add        sticky note added
  annotation_remove     sticky note erased
  markup_add            highlight / underline / strikethrough / freehand / signature added
  markup_remove         markup stroke erased
  stamp_add             text stamp baked onto page
  page_add              blank page inserted
  page_remove           page deleted
  page_move             page moved up / down / by drag
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


MAX_HISTORY = 100


@dataclass
class Command:
    kind: str
    redo_data: Any    # data needed to RE-apply the action
    undo_data: Any    # data needed to UNDO the action


class UndoStack:
    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    # ------------------------------------------------------------------
    # Push a new command (clears redo branch)
    # ------------------------------------------------------------------
    def push(self, cmd: Command):
        self._undo.append(cmd)
        if len(self._undo) > MAX_HISTORY:
            self._undo.pop(0)
        self._redo.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def peek_undo(self) -> Command | None:
        return self._undo[-1] if self._undo else None

    def peek_redo(self) -> Command | None:
        return self._redo[-1] if self._redo else None

    # ------------------------------------------------------------------
    # Pop for execution (caller applies the actual state change)
    # ------------------------------------------------------------------
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

    def clear(self):
        self._undo.clear()
        self._redo.clear()
