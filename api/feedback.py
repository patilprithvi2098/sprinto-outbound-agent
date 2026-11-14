"""Vercel entry for /api/feedback: the same request handler the local server uses (app/httpd.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from httpd import Handler as handler  # noqa: E402,F401  (Vercel looks for a class named `handler`)
