import os
import uuid
import smtplib
from pathlib import Path
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.config import settings, STORAGE_DIR
from app.models.entities import Document, CandidatePII, CandidateProfile, Notification, AuditEvent, RecruitmentAction
from app.integrations.dms_adapter import dms_adapter
from app.security.encryption import pii_crypto

class EmailAgentService:
    """
    AI Escalation & Email Agent.
    Monitors candidate dormancy and dispatches automated escalation notifications
    to leadership/hiring managers (e.g. damayanthi.u@riscrm.com) with candidate resumes attached.
    """

    def __init__(self):
        self.emails_dir = STORAGE_DIR / "emails"
        self.emails_dir.mkdir(parents=True, exist_ok=True)
        self.default_recipient = "damayanthi.u@riscrm.com"

    def _get_smtp_settings(self) -> Dict[str, Any]:
        """Loads latest SMTP configuration dynamically from .env to avoid stale cached settings."""
        try:
            from dotenv import load_dotenv
            load_dotenv(settings.BASE_DIR / ".env", override=True)
        except Exception:
            pass

        enabled = os.getenv("SMTP_ENABLED", "false").lower() in ("true", "1")
        server = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
        port = int(os.getenv("SMTP_PORT", "587"))
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1")
        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip("\"'")
        from_email = os.getenv("SMTP_FROM_EMAIL", "").strip() or username or "recruitment@hrconsole.internal"
        from_name = os.getenv("SMTP_FROM_NAME", "HR Recruitment Console").strip("\"'")

        return {
            "enabled": enabled,
            "server": server,
            "port": port,
            "use_tls": use_tls,
            "username": username,
            "password": password,
            "from_email": from_email,
            "from_name": from_name
        }

    def send_dormancy_escalation_email(
        self,
        doc_id: str,
        db: Session,
        recipient_email: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes an escalation dossier for a candidate unnoticed for threshold/3-month period,
        attaches their actual resume from the DMS, and dispatches to damayanthi.u@riscrm.com.
        """
        target_email = recipient_email or self.default_recipient
        smtp_cfg = self._get_smtp_settings()

        # 1. Fetch document and file
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Candidate resume '{doc_id}' not found.")

        file_data = None
        file_path = dms_adapter.get_file_path(doc.dms_ref)
        if file_path and file_path.exists():
            with open(file_path, "rb") as f:
                file_data = f.read()
        elif doc.ikm_ref:
            try:
                from app.integrations.ikm_adapter import ikm_adapter
                file_data = ikm_adapter.download_document(doc.ikm_ref)
                if file_data and file_path:
                    try:
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(file_path, "wb") as f:
                            f.write(file_data)
                    except Exception:
                        pass
            except Exception:
                file_data = None

        if not file_data:
            raise HTTPException(status_code=404, detail=f"Original resume file for '{doc_id}' not found in DMS or IKM.")

        # 2. Fetch candidate identity (authorized decryption for escalation payload)
        pii_rec = db.query(CandidatePII).filter(CandidatePII.doc_id == doc_id).first()
        cand_name = f"Candidate {doc_id}"
        cand_email = "Not Provided"
        if pii_rec:
            decrypted = pii_crypto.decrypt_pii_dict({
                "name_encrypted": pii_rec.name_encrypted,
                "email_encrypted": pii_rec.email_encrypted
            })
            cand_name = decrypted.get("name") or cand_name
            cand_email = decrypted.get("email") or cand_email

        # 3. Calculate inactivity metrics
        latest_action = (
            db.query(RecruitmentAction)
            .filter(RecruitmentAction.doc_id == doc_id)
            .order_by(RecruitmentAction.action_at.desc())
            .first()
        )
        now = datetime.now(timezone.utc)
        last_time = latest_action.action_at if latest_action else doc.uploaded_at
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        days_inactive = max(0, (now - last_time).days)

        profile_rec = db.query(CandidateProfile).filter(CandidateProfile.doc_id == doc_id).first()
        skills = profile_rec.structured_profile_json.get("skills", []) if profile_rec and profile_rec.structured_profile_json else []
        skills_str = ", ".join(skills[:8]) if skills else "Technical Skills documented in resume"

        # 4. Construct reason text
        escalation_reason = reason or f"Candidate resume has not been noticed or acted upon for {days_inactive} days (over 3 months review window)."

        # 5. Build MIME Multipart Email with Attachment
        msg = MIMEMultipart()
        sender_email = smtp_cfg["from_email"]
        sender_name = smtp_cfg["from_name"]
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = target_email
        msg["Subject"] = f"[Recruitment Review Alert] Candidate Resume Unnoticed for {days_inactive} Days: {cand_name} ({doc_id})"

        recipient_greeting = "Damayanthi" if "damayanthi" in target_email.lower() else "Hiring Manager"

        body_text = f"""Dear {recipient_greeting},

This is a recruitment escalation generated by the HR Recruitment Console.

A candidate profile in our recruitment repository has exceeded our standard follow-up review threshold:

=======================================================
CANDIDATE DOSSIER
=======================================================
• Document ID:        {doc_id}
• Candidate Name:      {cand_name}
• Registered Email:    {cand_email}
• Days Inactive:       {days_inactive} days (Exceeding review SLA)
• Primary Skillset:    {skills_str}
• Last Action Taken:   {latest_action.action_type if latest_action else 'Uploaded'}
• Last Recorded Date:  {last_time.strftime('%b %d, %Y %I:%M %p')}

REASON FOR ESCALATION:
{escalation_reason}

ATTACHED RESUME:
The candidate's original resume document ("{doc.original_filename}") is attached directly to this email for your immediate inspection, hiring manager circulation, and candidate re-engagement.

ACTION REQUIRED:
Please review the attached resume and update the candidate's status in the HR Console:
http://127.0.0.1:8000

Sincerely,
HR Recruitment Console
Workflow & Inactivity Intelligence
"""
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Attach the actual resume file (from DMS or IKM)
        attachment_mime = MIMEApplication(file_data)
        attachment_mime.add_header(
            "Content-Disposition",
            "attachment",
            filename=doc.original_filename
        )
        msg.attach(attachment_mime)

        # 6. Save email artifact (.eml) locally
        email_id = f"EMAIL-{uuid.uuid4().hex[:8]}"
        eml_path = self.emails_dir / f"{email_id}.eml"
        with open(eml_path, "wb") as f:
            f.write(msg.as_bytes())

        # 7. Live SMTP Delivery
        delivered_via_smtp = False
        smtp_note = ""

        if smtp_cfg["enabled"]:
            if not smtp_cfg["username"] or not smtp_cfg["password"]:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "SMTP delivery is enabled (SMTP_ENABLED=true) but SMTP_USERNAME or SMTP_PASSWORD is not set in .env. "
                        "To send emails via Gmail, enter your Gmail address and 16-character Google App Password in .env."
                    )
                )

            try:
                if smtp_cfg["port"] == 465:
                    with smtplib.SMTP_SSL(smtp_cfg["server"], smtp_cfg["port"], timeout=25) as server:
                        server.login(smtp_cfg["username"], smtp_cfg["password"])
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(smtp_cfg["server"], smtp_cfg["port"], timeout=25) as server:
                        if smtp_cfg["use_tls"]:
                            server.starttls()
                        server.login(smtp_cfg["username"], smtp_cfg["password"])
                        server.send_message(msg)
                delivered_via_smtp = True
                smtp_note = f"Dispatched live email via {smtp_cfg['server']} to {target_email}."
            except smtplib.SMTPAuthenticationError as auth_err:
                raise HTTPException(
                    status_code=401,
                    detail=(
                        f"Google/SMTP authentication failed ({auth_err.smtp_code}). "
                        "For Gmail/Google Workspace, make sure 2-Step Verification is active and you use a 16-character "
                        "Google App Password (https://myaccount.google.com/apppasswords), NOT your regular Google account password."
                    )
                )
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to deliver email through SMTP server {smtp_cfg['server']}:{smtp_cfg['port']}: {str(e)}"
                )
        else:
            smtp_note = (
                f"Simulated dispatch: Email saved locally to storage/emails/{email_id}.eml. "
                "Configure SMTP in .env to deliver real emails to inboxes."
            )

        # 8. Persist or update Notification in DB
        notif = (
            db.query(Notification)
            .filter(Notification.doc_id == doc_id)
            .first()
        )
        if not notif:
            notif = Notification(
                id=f"notif-{uuid.uuid4().hex[:8]}",
                doc_id=doc_id,
                title=f"3-Month Inactivity Escalation: {cand_name}",
                message=escalation_reason,
                severity="danger",
                days_inactive=days_inactive,
                created_at=now
            )
            db.add(notif)

        # Only mark as emailed if it was actually transmitted via live SMTP (or if user did not enable SMTP)
        notif.email_sent = delivered_via_smtp
        if delivered_via_smtp:
            notif.email_sent_to = target_email
            notif.email_sent_at = now
            notif.email_attachment_filename = doc.original_filename

        # 9. Log Audit Event
        db.add(AuditEvent(
            event_id=f"aud-{uuid.uuid4().hex[:8]}",
            actor_id="ai-agent",
            action="send_dormancy_escalation_email",
            target_doc_id=doc_id,
            outcome="success",
            metadata_json={
                "recipient": target_email,
                "email_id": email_id,
                "days_inactive": days_inactive,
                "attachment": doc.original_filename,
                "file_size_bytes": len(file_data),
                "delivered_via_smtp": delivered_via_smtp,
                "smtp_server": smtp_cfg["server"] if smtp_cfg["enabled"] else None
            }
        ))

        db.commit()

        return {
            "success": True,
            "email_id": email_id,
            "recipient": target_email,
            "doc_id": doc_id,
            "candidate_name": cand_name,
            "days_inactive": days_inactive,
            "attachment_filename": doc.original_filename,
            "attachment_size_kb": round(len(file_data) / 1024, 2),
            "sent_at": now.isoformat(),
            "delivered_via_smtp": delivered_via_smtp,
            "message": (
                f"Successfully sent live email to {target_email} with resume '{doc.original_filename}' attached."
                if delivered_via_smtp
                else f"Escalation email archived to storage/emails/{email_id}.eml. To send live emails, configure SMTP in .env."
            )
        }

email_agent = EmailAgentService()

