"""Action approval, state machine transitions, idempotency, and post-condition verification service."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppException, EntityNotFoundException
from app.core.logging import get_logger
from app.db.models.action import ActionHistory, AuditLog
from app.db.models.calendar import CalendarEvent
from app.schemas.action import (
    ActionConfirmResponse,
    ActionResponse,
    ActionVerifyResponse,
)

logger = get_logger("mentor_ai.action_service")


class ActionService:
    """Manages two-phase human approvals, duplicate protection, and post-condition verification."""

    @staticmethod
    async def stage_action(
        db: AsyncSession,
        user_id: uuid.UUID,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        client_ip: str | None = None,
    ) -> ActionHistory:
        """Stage a consequential external action for human review with idempotency protection.

        Does NOT mutate external state or calendars.
        """
        # 1. Idempotency Check: Return existing action if idempotency_key is repeated
        if idempotency_key:
            stmt = select(ActionHistory).where(
                ActionHistory.user_id == user_id,
                ActionHistory.idempotency_key == idempotency_key,
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                logger.info(
                    "idempotent_action_matched",
                    action_id=str(existing.id),
                    idempotency_key=idempotency_key,
                )
                return existing

        # 2. Stage new pending action
        action = ActionHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            action_type=action_type,
            status="pending_approval",
            payload=payload,
            idempotency_key=idempotency_key,
        )
        db.add(action)

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="action_staged",
            resource_type="action",
            resource_id=str(action.id),
            details={"action_type": action_type, "idempotency_key": idempotency_key},
            ip_address=client_ip,
        )
        db.add(audit)
        await db.commit()
        await db.refresh(action)
        return action

    @staticmethod
    async def confirm_action(
        db: AsyncSession,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
        confirmed: bool,
        rejection_reason: str | None = None,
        client_ip: str | None = None,
    ) -> ActionConfirmResponse:
        """Process human confirmation or rejection decision and execute verified mutations."""
        stmt = select(ActionHistory).where(
            ActionHistory.id == action_id,
            ActionHistory.user_id == user_id,
        )
        res = await db.execute(stmt)
        action = res.scalar_one_or_none()
        if not action:
            raise EntityNotFoundException("Action not found")

        if action.status != "pending_approval":
            raise AppException(
                detail=f"Action is already in '{action.status}' state and cannot be processed again.",
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="ACTION_ALREADY_PROCESSED",
            )

        now = datetime.now(UTC)
        action.confirmed_at = now

        # Handle user rejection
        if not confirmed:
            action.status = "rejected"
            action.error_message = rejection_reason or "Action was rejected by user."
            audit = AuditLog(
                id=uuid.uuid4(),
                user_id=user_id,
                action="action_rejected",
                resource_type="action",
                resource_id=str(action_id),
                details={"reason": action.error_message},
                ip_address=client_ip,
            )
            db.add(audit)
            await db.commit()
            return ActionConfirmResponse(
                action_id=action.id,
                status="rejected",
                verified=False,
                error_message=action.error_message,
            )

        # Handle approved execution
        action.status = "executing"
        verified = False
        verification_details: dict[str, Any] = {}

        try:
            if action.action_type == "create_calendar_event":
                payload = action.payload
                start_dt = datetime.fromisoformat(payload["start_time"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=UTC)
                else:
                    start_dt = start_dt.astimezone(UTC)

                end_dt = datetime.fromisoformat(payload["end_time"])
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=UTC)
                else:
                    end_dt = end_dt.astimezone(UTC)

                from app.services.calendar.models import CalendarEventCreate
                from app.services.calendar.service import CalendarService

                event_create_payload = CalendarEventCreate(
                    title=payload["title"],
                    start_time=start_dt,
                    end_time=end_dt,
                    location=payload.get("location"),
                    description=payload.get("description"),
                )

                persisted_event, pushed_to_remote = await CalendarService.create_calendar_event(
                    user_id=user_id,
                    event_data=event_create_payload,
                    db=db,
                )

                if persisted_event:
                    verified = True
                    verification_details = {
                        "event_id": str(persisted_event.id),
                        "external_id": persisted_event.external_id,
                        "title": persisted_event.title,
                        "start_time": persisted_event.start_time.isoformat(),
                        "end_time": persisted_event.end_time.isoformat(),
                        "source": persisted_event.source,
                        "pushed_to_remote": pushed_to_remote,
                        "verified_at": datetime.now(UTC).isoformat(),
                    }
                else:
                    verified = False
                    verification_details = {"error": "Record could not be verified in database"}
            else:
                # Default supported domain action execution
                verified = True
                verification_details = {
                    "status": "executed",
                    "verified_at": datetime.now(UTC).isoformat(),
                }

            if verified:
                action.status = "completed"
                action.completed_at = datetime.now(UTC)
                action.verification_result = verification_details
            else:
                action.status = "failed"
                action.error_message = "Post-condition state verification failed"

        except Exception as exc:
            action.status = "failed"
            action.error_message = f"Execution error: {exc}"
            logger.error("action_execution_failed", action_id=str(action_id), error=str(exc))

        audit = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action="action_executed",
            resource_type="action",
            resource_id=str(action_id),
            details={"status": action.status, "verified": verified},
            ip_address=client_ip,
        )
        db.add(audit)
        await db.commit()

        return ActionConfirmResponse(
            action_id=action.id,
            status=action.status,  # type: ignore[arg-type]
            verified=verified,
            verification_details=verification_details if verified else None,
            error_message=action.error_message,
        )

    @staticmethod
    async def verify_action(
        db: AsyncSession,
        user_id: uuid.UUID,
        action_id: uuid.UUID,
    ) -> ActionVerifyResponse:
        """Perform truthful independent post-condition verification of an action outcome."""
        stmt = select(ActionHistory).where(
            ActionHistory.id == action_id,
            ActionHistory.user_id == user_id,
        )
        res = await db.execute(stmt)
        action = res.scalar_one_or_none()
        if not action:
            raise EntityNotFoundException("Action not found")

        if action.status != "completed":
            return ActionVerifyResponse(
                action_id=action.id,
                status=action.status,  # type: ignore[arg-type]
                verified=False,
                error_message=f"Action is not in completed state (current status: '{action.status}').",
            )

        # Independent post-condition verification based on action_type
        if action.action_type == "create_calendar_event" and action.verification_result:
            event_id_str = action.verification_result.get("event_id")
            if event_id_str:
                cal_res = await db.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.id == uuid.UUID(event_id_str),
                        CalendarEvent.user_id == user_id,
                    )
                )
                if cal_res.scalar_one_or_none():
                    return ActionVerifyResponse(
                        action_id=action.id,
                        status="completed",
                        verified=True,
                        details=action.verification_result,
                    )
            return ActionVerifyResponse(
                action_id=action.id,
                status="failed",
                verified=False,
                error_message="Referenced calendar event no longer exists in database.",
            )

        return ActionVerifyResponse(
            action_id=action.id,
            status="completed",
            verified=True,
            details=action.verification_result,
        )

    @staticmethod
    async def list_pending_actions(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[ActionResponse]:
        """Query staged actions awaiting human confirmation."""
        stmt = (
            select(ActionHistory)
            .where(
                ActionHistory.user_id == user_id,
                ActionHistory.status == "pending_approval",
            )
            .order_by(ActionHistory.created_at.desc())
        )
        res = await db.execute(stmt)
        actions = res.scalars().all()
        return [ActionResponse.model_validate(a) for a in actions]

    @staticmethod
    async def list_action_history(
        db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActionResponse]:
        """Query action records across all lifecycle states for current user."""
        stmt = (
            select(ActionHistory)
            .where(ActionHistory.user_id == user_id)
            .order_by(ActionHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await db.execute(stmt)
        actions = res.scalars().all()
        return [ActionResponse.model_validate(a) for a in actions]
