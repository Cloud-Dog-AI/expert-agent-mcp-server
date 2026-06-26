# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Sub-expert delegation support."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.session.manager import SessionManager
from src.database.connection import get_db
from src.database.models import Session as SessionModel, SubExpertBinding


class DelegationManager:
    """Create and trace delegated expert execution trees."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.session_manager = SessionManager(db)

    def _get_db(self) -> Session:
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _ancestry_session_ids(self, session: SessionModel) -> List[int]:
        ids = [int(session.id)]
        current = session.parent_session
        while current is not None:
            ids.append(int(current.id))
            current = current.parent_session
        return ids

    def _ancestry_expert_ids(self, session: SessionModel) -> List[int]:
        ids = [int(session.expert_config_id)]
        current = session.parent_session
        while current is not None:
            ids.append(int(current.expert_config_id))
            current = current.parent_session
        return ids

    def delegate(
        self,
        parent_session_id: int,
        sub_expert_id: int,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        depth: int = 0,
    ) -> Dict[str, Any]:
        db = self._get_db()
        parent = db.query(SessionModel).filter(SessionModel.id == parent_session_id).first()
        if not parent:
            raise ValueError("Parent session not found")

        binding = (
            db.query(SubExpertBinding)
            .filter(
                SubExpertBinding.parent_expert_id == parent.expert_config_id,
                SubExpertBinding.child_expert_id == sub_expert_id,
                SubExpertBinding.enabled.is_(True),
            )
            .first()
        )
        if not binding:
            raise ValueError("Sub-expert binding not found")

        max_depth = int(binding.max_depth or get_config("service_composition.max_delegation_depth") or 3)
        if depth >= max_depth:
            raise ValueError("Maximum delegation depth exceeded")

        ancestry_experts = self._ancestry_expert_ids(parent)
        if int(sub_expert_id) in ancestry_experts:
            raise ValueError("Self-referencing loop detected")

        child, notification = self.session_manager.create_session(
            user_id=parent.user_id,
            expert_config_id=sub_expert_id,
            title=f"Delegated from session {parent_session_id}",
            check_limits=False,
        )
        if notification:
            raise ValueError(str(notification))

        child.parent_session_id = parent.id
        db.commit()
        db.refresh(child)

        metadata = {
            "delegated_by_session_id": parent_session_id,
            "task": task,
            "context": context or {},
            "depth": depth + 1,
            "delegation_prompt": binding.delegation_prompt,
        }
        self.session_manager.add_message(
            child.id,
            "user",
            task,
            metadata=metadata,
        )
        return {
            "parent_session_id": parent_session_id,
            "child_session_id": child.id,
            "sub_expert_id": sub_expert_id,
            "depth": depth + 1,
            "task": task,
        }

    def get_delegation_tree(self, session_id: int) -> Dict[str, Any]:
        db = self._get_db()
        root = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not root:
            raise ValueError("Session not found")

        def _walk(node: SessionModel) -> Dict[str, Any]:
            return {
                "session_id": node.id,
                "expert_config_id": node.expert_config_id,
                "children": [_walk(child) for child in node.child_sessions],
            }

        return _walk(root)
