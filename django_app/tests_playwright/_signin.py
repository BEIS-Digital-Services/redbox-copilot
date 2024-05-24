import logging
import os
import subprocess
from pathlib import Path

from _settings import BASE_URL
from dotenv import load_dotenv
from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)
DJANGO_ROOT = Path(__file__).parents[1]
load_dotenv(dotenv_path=DJANGO_ROOT / ".env", override=True)


def sign_in(page: Page):
    email_address = os.environ["USER_EMAIL"]

    if not email_address:
        message = "USER_EMAIL not set in your .env - this must be set to the email address you use for signing in."
        raise ValueError(message)

    # Sign in page
    page.goto(f"{BASE_URL}/sign-in/")
    expect(page.get_by_text("Redbox Copilot")).to_be_visible()
    page.get_by_label("Email Address").type(email_address)
    page.get_by_text("Continue").click()

    # Get magic link
    command = ["poetry", "run", "python", "manage.py", "show_magiclink_url", email_address]
    result = subprocess.run(command, capture_output=True, text=True, cwd=DJANGO_ROOT)  # noqa: S603
    magic_link = result.stdout.strip()

    # Complete sign-in and verify
    page.goto(f"{BASE_URL}{magic_link}")
    page.get_by_role("button").click()
    expect(page.get_by_text("Sign out")).to_be_visible()
