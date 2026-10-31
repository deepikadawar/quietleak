"""Cancellation guidance. QuietLeak explains and tracks; it never cancels anything itself."""
from __future__ import annotations

METHODS = ["UPI AutoPay", "Debit or credit card", "App store billing"]
STATUSES = ["Not started", "In progress", "Completed (self-reported)"]

CHECKLISTS = {
    "UPI AutoPay": [
        "Open the service's official billing settings and find the subscription-management option.",
        "Follow its cancellation steps and save the confirmation (screenshot or email).",
        "Open your UPI app and find this service under AutoPay / mandates.",
        "Check the mandate status. Pause or revoke it if it is still active.",
        "Confirm future deductions are no longer authorised under it.",
        "Re-check after the next expected billing date that no debit occurred.",
    ],
    "Debit or credit card": [
        "Open the service's official billing settings and find the subscription-management option.",
        "Follow its cancellation steps and save the confirmation.",
        "Check whether the card is saved for recurring billing (card-on-file or standing instruction) and remove it or the instruction if you can.",
        "Contact your bank or card issuer if you cannot stop the charge through the service.",
        "Re-check your statement after the next expected billing date.",
    ],
    "App store billing": [
        "Open the app-store account that was used to buy the subscription.",
        "Find the subscription in that account's subscription list.",
        "Cancel it there. Deleting the app does not cancel the subscription.",
        "Save the confirmation and note the date until which access continues.",
        "Re-check your statement after the next expected billing date.",
    ],
}


def recommended_next_step(method: str, subscription_cancelled: bool, mandate_cancelled: bool) -> str:
    if method == "App store billing":
        if subscription_cancelled:
            return ("Check the store's subscription list to confirm it shows no renewal date, and keep the "
                    "confirmation. There is no separate mandate for you to revoke here.")
        return "Cancel the subscription in the store account that bills for it. Cancelling inside the app itself may not be enough."

    if subscription_cancelled and mandate_cancelled:
        return ("Verify both: the service shows the subscription as cancelled and the mandate shows as revoked. "
                "Keep both confirmations and check your next statement.")
    if mandate_cancelled:
        return ("Check the mandate's status and make sure future deductions are no longer authorised under it. "
                "Then contact the service to confirm what happened to your subscription and whether any account "
                "balance or cancellation obligation remains.")
    if subscription_cancelled:
        return ("Now check the payment side. Make sure no mandate or saved-card instruction can still debit you, "
                "and revoke it if one exists.")
    return ("Start with the service's own billing settings and cancel the subscription there. "
            "Then check the payment mandate or card instruction separately.")


DISCLAIMER = ("Educational guidance for a fictional example. Actual steps depend on the provider, "
              "the terms and the mandate status. QuietLeak does not cancel anything for you.")
