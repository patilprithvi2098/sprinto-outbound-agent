"""Send a draft to the operator's own inbox. There is no way to pass a recipient: it is always OPERATOR_EMAIL."""
import os
import smtplib
import time
from email.message import EmailMessage


RETRY_WAIT = 2


def send_to_operator(subject, body):
    recipient = os.environ["OPERATOR_EMAIL"]
    sender = os.environ.get("GMAIL_SENDER") or recipient
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
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
