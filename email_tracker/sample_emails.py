"""Sample inbox used by the proof-of-concept classifier.

These stand in for the real inbox so the classifier can be demoed without any
OAuth setup. Each dict matches the shape returned by `email_source.Email` — so
when the Microsoft Graph source is wired in (see `graph_source.py`), the rest of
the pipeline does not change.
"""

SAMPLE_EMAILS = [
    {
        "id": "1",
        "from_name": "Maria Chen",
        "from_addr": "maria@northwind-robotics.com",
        "subject": "Re: Series B term sheet — a few open points",
        "received": "2026-06-08T08:14:00",
        "body": (
            "Hi Sam,\n\n"
            "Thanks for sending the term sheet over. We're excited. A couple of "
            "points the team wants to discuss before we sign: the liquidation "
            "preference (we'd push for 1x non-participating) and the size of the "
            "option pool. Could we get 30 minutes on the calendar this week to "
            "walk through them? Hoping to move quickly.\n\n"
            "Best,\nMaria\nCEO, Northwind Robotics"
        ),
    },
    {
        "id": "2",
        "from_name": "AWS Billing",
        "from_addr": "no-reply@amazon.com",
        "subject": "Your AWS invoice is available",
        "received": "2026-06-08T06:02:00",
        "body": (
            "Your AWS invoice for May 2026 is now available. Total: $1,204.55. "
            "No action is required; the amount will be charged to your card on "
            "file. View your invoice in the billing console."
        ),
    },
    {
        "id": "3",
        "from_name": "David Okafor",
        "from_addr": "david.okafor@helioscredit.com",
        "subject": "Intro — Helios Credit, looking at your fund",
        "received": "2026-06-07T19:45:00",
        "body": (
            "Sam — great to meet you at the SaaS Capital dinner. As discussed, "
            "Helios is exploring an LP commitment to Fund III. Could you share "
            "the data room and the latest LP deck? We'd want to complete our "
            "diligence over the next 4-6 weeks. Happy to sign an NDA first if "
            "needed.\n\nDavid"
        ),
    },
    {
        "id": "4",
        "from_name": "Priya Raman",
        "from_addr": "priya@arcadiacapital.io",
        "subject": "Lunch Friday?",
        "received": "2026-06-07T15:30:00",
        "body": (
            "Hey Sam — are you around for lunch Friday? Wanted to catch up before "
            "the partner meeting. No agenda, just overdue. :)"
        ),
    },
    {
        "id": "5",
        "from_name": "Quantum Yield Partners",
        "from_addr": "winner@qy-partners-promo.biz",
        "subject": "GUARANTEED 40% RETURNS — exclusive allocation for you",
        "received": "2026-06-07T11:11:00",
        "body": (
            "Dear Investor, you have been SELECTED for an exclusive allocation in "
            "our flagship fund delivering GUARANTEED 40% annual returns. Wire "
            "funds before Friday to secure your spot. Reply now!!!"
        ),
    },
    {
        "id": "6",
        "from_name": "Tom Reilly",
        "from_addr": "treilly@meridian-legal.com",
        "subject": "Meridian deal — signature pages needed by EOD",
        "received": "2026-06-08T09:50:00",
        "body": (
            "Sam, we're ready to close the Meridian acquisition. I need the "
            "executed signature pages from your side by end of day today to file "
            "with the closing set tomorrow morning. Everything else is final. "
            "Let me know if you hit any snags.\n\nTom\nMeridian Legal"
        ),
    },
    {
        "id": "7",
        "from_name": "Jenna Wills",
        "from_addr": "jenna@brightpath-health.com",
        "subject": "Following up on our pitch",
        "received": "2026-06-05T13:20:00",
        "body": (
            "Hi Sam, following up on the deck we sent two weeks ago for "
            "BrightPath Health's seed round. We've since signed two enterprise "
            "pilots and would love to get your thoughts. Is this something "
            "Arcadia would consider? Totally understand if it's not a fit."
        ),
    },
    {
        "id": "8",
        "from_name": "Calendar",
        "from_addr": "calendar-notification@arcadiacapital.io",
        "subject": "Reminder: Partner meeting Monday 9am",
        "received": "2026-06-08T07:00:00",
        "body": (
            "This is an automated reminder that the weekly partner meeting is "
            "scheduled for Monday at 9:00 AM in the main conference room."
        ),
    },
]
