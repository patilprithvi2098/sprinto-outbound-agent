"""Send a draft to the operator's own inbox: the recipient is always OPERATOR_EMAIL.
A CC is delivered only to an address the operator listed in CC_ALLOWED (addresses or @domains he controls);
anyone else marked as CC is named in the email but never mailed, so no prospect gets a message from this app."""
import os
import smtplib
import time
from email.message import EmailMessage


RETRY_WAIT = 2


def cc_allowed(email):
    allowed = [a.strip().lower() for a in (os.environ.get("CC_ALLOWED") or "").split(",") if a.strip()]
    email = (email or "").strip().lower()
    return any(email == a or (a.startswith("@") and email.endswith(a)) for a in allowed)


def send_to_operator(subject, body, cc=()):
    recipient = os.environ["OPERATOR_EMAIL"]
    sender = os.environ.get("GMAIL_SENDER") or recipient
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
    cc = [a for a in cc if cc_allowed(a)]  # checked here as well as by the caller
    if cc:
        message["Cc"] = ", ".join(cc)
    message.set_content(body)
    for attempt in (1, 2):  # only connecting and logging in are retried: a retry after the message went out would send it twice
        try:
            smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20)
            smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
            break
        except smtplib.SMTPAuthenticationError:
            raise  # a rejected login will not pass on a second try
        except Exception:
            if attempt == 2:
                raise
            time.sleep(RETRY_WAIT)
    try:
        smtp.send_message(message)  # never retried
    finally:
        try:
            smtp.quit()
        except Exception:
            pass  # the message is already accepted; a failed goodbye is not a failed send
