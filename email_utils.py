"""
email_utils.py
--------------
Helper functions for sending transactional emails via Flask-Mail.
All functions are fire-and-forget: errors are caught and logged so they
never crash the main request.
"""

import logging
from flask import current_app
from flask_mail import Message as MailMessage
from extensions import mail

logger = logging.getLogger(__name__)


def _send(subject: str, recipients: list[str], body: str, html: str = None):
    """Low-level send. Catches exceptions so callers don't have to."""
    try:
        msg = MailMessage(subject=subject, recipients=recipients, body=body, html=html)
        mail.send(msg)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", recipients, exc)


# ── Public helpers ─────────────────────────────────────────────────────────────

def send_welcome_email(user):
    """Sent when a new account is created."""
    _send(
        subject="Welcome to DUT Collaboration Hub!",
        recipients=[user.email],
        body=(
            f"Hi {user.name},\n\n"
            "Your account has been created successfully.\n"
            f"Role: {user.role.capitalize()}\n\n"
            "Log in at any time to explore projects and collaborate.\n\n"
            "— DUT Collaboration Hub Team"
        ),
        html=(
            f"<h2>Welcome, {user.name}!</h2>"
            "<p>Your account has been created successfully.</p>"
            f"<p><strong>Role:</strong> {user.role.capitalize()}</p>"
            "<p>Log in at any time to explore projects and collaborate.</p>"
            "<br><p>— DUT Collaboration Hub Team</p>"
        )
    )


def send_application_received(student, project):
    """Notify student that their application was received."""
    _send(
        subject=f"Application Received – {project.title}",
        recipients=[student.email],
        body=(
            f"Hi {student.name},\n\n"
            f'Your application to "{project.title}" has been received.\n'
            "You will be notified once the faculty member reviews it.\n\n"
            "— DUT Collaboration Hub"
        ),
    )


def send_application_approved(student, project):
    """Notify student that their application was approved."""
    _send(
        subject=f"🎉 Application Approved – {project.title}",
        recipients=[student.email],
        body=(
            f"Hi {student.name},\n\n"
            f'Congratulations! Your application to "{project.title}" '
            "has been approved and you are now enrolled.\n\n"
            "Log in to view your project dashboard and get started.\n\n"
            "— DUT Collaboration Hub"
        ),
        html=(
            f"<h2>Congratulations, {student.name}!</h2>"
            f"<p>Your application to <strong>{project.title}</strong> has been approved.</p>"
            "<p>You are now enrolled. Log in to get started!</p>"
        )
    )


def send_application_rejected(student, project):
    """Notify student that their application was not successful."""
    _send(
        subject=f"Application Update – {project.title}",
        recipients=[student.email],
        body=(
            f"Hi {student.name},\n\n"
            f'Unfortunately your application to "{project.title}" '
            "was not successful this time.\n"
            "Please browse other open projects and feel free to apply again.\n\n"
            "— DUT Collaboration Hub"
        ),
    )


def send_new_project_notification(student, project):
    """Notify a student about a newly posted project."""
    _send(
        subject=f"New Project Available – {project.title}",
        recipients=[student.email],
        body=(
            f"Hi {student.name},\n\n"
            f'A new project has been posted: "{project.title}".\n'
            f"Department: {project.department}\n"
            f"Deadline: {project.deadline}\n\n"
            "Log in to browse and apply.\n\n"
            "— DUT Collaboration Hub"
        ),
    )


def send_new_message_notification(recipient, sender, project):
    """Notify a user that they have a new chat message."""
    _send(
        subject=f"New Message in {project.title}",
        recipients=[recipient.email],
        body=(
            f"Hi {recipient.name},\n\n"
            f"{sender.name} sent a message in the project chat for \"{project.title}\".\n"
            "Log in to read and reply.\n\n"
            "— DUT Collaboration Hub"
        ),
    )
