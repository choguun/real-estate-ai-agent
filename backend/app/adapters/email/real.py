"""Real email adapter stub — Resend / SendGrid / SES wiring is a follow-up."""

from __future__ import annotations


class ResendEmailAdapter:
    """Stub for production email service. Real wiring in Cycle 4+."""

    def __init__(self, api_key: str, *, from_address: str = "noreply@realestateai.app") -> None:
        self._api_key = api_key
        self._from = from_address

    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        html: str | None = None,
    ) -> dict[str, str]:
        raise NotImplementedError(
            "ResendEmailAdapter.send is not wired. " "Set use_mocks=true (default) for local dev."
        )
