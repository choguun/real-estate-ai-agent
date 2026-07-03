"""Email adapter Protocol — sends transactional email.

Two implementations:
- MockEmailAdapter (dev): logs to console
- RealEmailAdapter (prod): Resend / SendGrid / SES (stub for now)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailAdapter(Protocol):
    """The single interface the rest of the app uses to send email."""

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> dict[str, str]:
        """Send a transactional email. Returns a record with an `id`.

        Mock returns a generated UUID; real returns the provider's
        message id.
        """
        ...
