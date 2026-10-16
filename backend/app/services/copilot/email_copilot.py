"""Gmail Copilot service for conversational email searching, thread context, draft preview, and confirmed sending."""

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.copilot import EmailDraftPreview
from app.services.copilot.approval import generate_action_approval, verify_action_approval
from app.services.gmail.base import GmailProviderException
from app.services.gmail.models import GmailSendPayload
from app.services.gmail.sanitizer import sanitize_email_text
from app.services.gmail.service import GmailService

logger = get_logger("mentor_ai.copilot.email")


class CopilotEmailService:
    """Conversational assistant for safe, context-aware Gmail interactions."""

    @classmethod
    async def prepare_email_reply(
        cls, db: AsyncSession, user_id: uuid.UUID, prompt: str
    ) -> EmailDraftPreview:
        """Search connected Gmail account, resolve recipient and thread context, and draft a response."""
        # 1. Check if Gmail integration is connected and active
        status = await GmailService.get_status(user_id=user_id, db=db)
        if not status.is_connected:
            return EmailDraftPreview(
                recipient_email="",
                subject="",
                body="",
                status="not_found",
                requires_confirmation=False,
                clarification_question="Your Gmail account is not connected yet. Please connect Gmail in Settings to enable email assistance.",
            )

        # 2. Extract potential recipient search terms from prompt
        lower = prompt.lower()
        search_query = None

        # Check for explicit email address
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", prompt)
        if email_match:
            search_query = email_match.group(0)
        else:
            # Check for common instructor/contact keywords
            keywords = ["instructor", "professor", "teacher", "advisor", "ta", "mentor", "boss"]
            matched_kw = [kw for kw in keywords if kw in lower]
            if matched_kw:
                search_query = matched_kw[0]

        # 3. Search messages in inbox
        try:
            message_list = await GmailService.list_messages(
                user_id=user_id, db=db, folder="inbox", max_results=10, query=search_query
            )
            messages = message_list.messages
        except GmailProviderException as e:
            logger.warn("Failed to query Gmail messages for copilot", error=str(e))
            return EmailDraftPreview(
                recipient_email="",
                subject="",
                body="",
                status="failed",
                requires_confirmation=False,
                clarification_question=f"Could not access your Gmail inbox: {e.message}",
            )

        if not messages:
            return EmailDraftPreview(
                recipient_email="",
                subject="",
                body="",
                status="not_found",
                requires_confirmation=False,
                clarification_question="I searched your inbox but couldn't find any recent email threads matching that description. Could you provide the instructor's name or exact email address?",
            )

        # 4. Check for ambiguous recipients
        unique_senders: dict[str, str] = {}
        for msg in messages:
            sender_str = msg.sender or ""
            # Extract email from sender string "Name <email@example.com>"
            email_part = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", sender_str)
            if email_part:
                clean_email = email_part.group(0)
                name_part = re.sub(r"<.*?>", "", sender_str).strip() or clean_email
                unique_senders[clean_email] = name_part

        if len(unique_senders) > 1 and not email_match:
            # Multiple candidate senders found
            candidates = [
                {"email": email, "name": name}
                for email, name in unique_senders.items()
            ][:4]

            names_list = ", ".join(f"{c['name']} ({c['email']})" for c in candidates)
            return EmailDraftPreview(
                recipient_email="",
                subject="",
                body="",
                status="ambiguous_recipient",
                requires_confirmation=False,
                clarification_question=f"I found {len(candidates)} possible email contacts: {names_list}. Which person would you like to reply to?",
                candidates=candidates,
            )

        # 5. Resolve selected target message and retrieve full thread context
        target_summary = messages[0]
        try:
            detail = await GmailService.get_message(
                user_id=user_id, message_id=target_summary.id, db=db
            )
        except Exception:
            detail = None

        sender_email = ""
        sender_name = ""
        raw_sender = detail.sender if detail else target_summary.sender
        sender_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_sender)
        if sender_match:
            sender_email = sender_match.group(0)
            sender_name = re.sub(r"<.*?>", "", raw_sender).strip() or sender_email
        else:
            sender_email = raw_sender
            sender_name = raw_sender

        subject = detail.subject if detail else target_summary.subject
        if not subject.lower().startswith("re:"):
            reply_subject = f"Re: {subject}"
        else:
            reply_subject = subject

        # Sanitize incoming body snippet to prevent prompt injection
        snippet = sanitize_email_text(
            detail.snippet if detail else target_summary.snippet
        )

        # 6. Compose context-appropriate student reply draft
        # Tailor body based on user request keywords
        if "tomorrow" in lower:
            time_commitment = "by tomorrow"
        elif "today" in lower:
            time_commitment = "later today"
        else:
            time_commitment = "as soon as possible"

        if "assignment" in lower:
            task_topic = "the assignment"
        elif "project" in lower:
            task_topic = "the project deliverables"
        elif "exam" in lower or "quiz" in lower:
            task_topic = "the exam preparation"
        else:
            task_topic = "my coursework update"

        draft_body = (
            f"Dear {sender_name.split()[0] if sender_name else 'Professor'},\n\n"
            f"I hope this email finds you well. Regarding {task_topic}, I wanted to let you know that I am actively working on it and will submit it {time_commitment}.\n\n"
            f"Thank you for your understanding and guidance.\n\n"
            f"Best regards,\n"
            f"Your Student"
        )

        context_summary = f"Replying to email from {sender_name} with subject '{subject}'. Context: \"{snippet[:120]}...\""
        thread_id = target_summary.thread_id or target_summary.id

        approval_id = generate_action_approval(
            user_id=user_id,
            action_type="send_email",
            payload={
                "recipient_email": sender_email,
                "subject": reply_subject,
                "body": draft_body,
                "thread_id": thread_id,
            },
        )

        return EmailDraftPreview(
            thread_id=thread_id,
            recipient_email=sender_email,
            recipient_name=sender_name,
            subject=reply_subject,
            body=draft_body,
            context_summary=context_summary,
            requires_confirmation=True,
            approval_id=approval_id,
            status="draft_ready",
        )

    @classmethod
    async def send_confirmed_email(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        recipient_email: str,
        subject: str,
        body: str,
        thread_id: str | None = None,
        approval_id: str | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Send an explicitly user-confirmed email draft through GmailService."""
        if not recipient_email or "@" not in recipient_email:
            return False, "Invalid recipient email address.", {}

        # If approval_id is provided, verify token authenticity, expiration, and payload integrity
        if approval_id:
            payload_data = {
                "recipient_email": recipient_email,
                "subject": subject,
                "body": body,
                "thread_id": thread_id,
            }
            valid, reason = verify_action_approval(
                approval_id=approval_id,
                user_id=user_id,
                expected_action_type="send_email",
                current_payload=payload_data,
            )
            if not valid:
                logger.warning("Email send blocked: invalid approval token", reason=reason, user_id=str(user_id))
                return False, f"Send authorization failed: {reason}", {}

        payload = GmailSendPayload(
            to=recipient_email,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )

        try:
            result = await GmailService.send_email_verified(
                user_id=user_id, payload=payload, db=db
            )
            return (
                True,
                f"Email successfully sent to {recipient_email}.",
                {
                    "message_id": result.message_id,
                    "thread_id": result.thread_id,
                    "sent_at": result.sent_at.isoformat() if result.sent_at else None,
                },
            )
        except Exception as e:
            logger.error("Failed to send confirmed email", error=str(e), recipient=recipient_email)
            return False, f"Failed to send email: {str(e)}", {}
