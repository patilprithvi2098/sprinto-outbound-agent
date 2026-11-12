"""Send a draft to the operator's own inbox. There is no way to pass a recipient: it is always OPERATOR_EMAIL."""
import os
import smtplib
from email.message import EmailMessage


def send_to_operator(subject, body):
    recipient = os.environ["OPERATOR_EMAIL"]
    sender = os.environ.get("GMAIL_SENDER") or recipient
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, recipient, subject
    message.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
        smtp.send_message(message)
