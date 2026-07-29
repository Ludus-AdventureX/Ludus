"""Invite-gated registration: public sign-up is closed for the alpha.

The alpha's only entry point used to be the prototype guest endpoint — anyone
who loaded the page minted a workspace, and every workspace carries its own
analysis-run budget, which makes an open door an amplifier for the most
expensive route in the product. Registration is now the way in, and it requires
an invite code the operator hands out one recipient at a time.

Codes are configured as SHA-256 digests in ``SIGNUP_INVITE_CODE_HASHES`` so a
leaked deployment config does not leak usable codes. Two rules make the gate
trustworthy:

- comparison is constant-time, over every configured digest, so response timing
  cannot be used to narrow a code down;
- an unset or empty variable CLOSES registration instead of opening it. A
  misconfigured deployment turns people away; it does not silently become a
  public sign-up page.

Revocation is deployment-level: drop the digest and restart. That is honest
about what this is — a hand-operated alpha gate, not an invite management
system. What it is NOT: per-code single use, per-code expiry, or an audit trail
of which code admitted whom. A code shared with a second person admits the
second person too.
"""

from __future__ import annotations

import hashlib
import os
from secrets import compare_digest

SIGNUP_INVITE_HASHES_ENV = "SIGNUP_INVITE_CODE_HASHES"

# Bound the accepted code length: a code is typed by a human, and an unbounded
# string would let a caller push arbitrary bytes through the hash.
MAX_CODE_LENGTH = 128


def invite_code_digest(code: str) -> str:
    """Digest a code exactly the way the configured digests were produced."""

    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def configured_signup_digests() -> tuple[str, ...]:
    """Parse the configured digests; unparseable entries are simply ignored."""

    raw = os.getenv(SIGNUP_INVITE_HASHES_ENV, "")
    digests = []
    for entry in raw.replace(";", ",").split(","):
        candidate = entry.strip().lower()
        # A digest is 64 hex characters; anything else is a config typo, and
        # accepting it would weaken the comparison below.
        if len(candidate) == 64 and all(c in "0123456789abcdef" for c in candidate):
            digests.append(candidate)
    return tuple(digests)


def signup_open() -> bool:
    """True when at least one usable code is configured."""

    return bool(configured_signup_digests())


def signup_code_accepted(code: str | None) -> bool:
    """Constant-time membership test of ``code`` against the configured digests.

    Every configured digest is compared even after a match so the work done does
    not depend on which code was supplied (or on how many were configured before
    the matching one).
    """

    digests = configured_signup_digests()
    if not digests:
        return False
    if not code or len(code) > MAX_CODE_LENGTH:
        return False
    candidate = invite_code_digest(code)
    accepted = False
    for digest in digests:
        if compare_digest(candidate, digest):
            accepted = True
    return accepted
