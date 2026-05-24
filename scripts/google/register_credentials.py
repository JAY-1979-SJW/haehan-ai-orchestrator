"""Disabled Google credential registration command.

Google login must use a user-present browser session or official OAuth/API
credentials. This command intentionally does not collect or save Google account
passwords.
"""
from __future__ import annotations


def main() -> None:
    print("Google password registration is disabled.")
    print("Use user-present browser login or an official OAuth/API flow.")


if __name__ == "__main__":
    main()
