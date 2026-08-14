"""Team code validation (rule 45 [MUST], book Appendix E p.148): "enter a
unique group identification code, eight characters, no spaces." A separate
concept from `--group-name` (a human-readable display name used throughout
logs/GUI/reports) -- the book's own sanction framing ("organizational
failure that prevents automatic report attribution") describes a compact
code used specifically for cross-referencing a Moodle submission against
report metadata, not a display name. Kept as its own, optional field
(`--team-code`) rather than repurposing `--group-name`, so a real team
isn't forced into an unreadable 8-character group name everywhere else.
"""

from thief_peer.exceptions import ConfigError


def validate_team_code(code: str) -> None:
    """Raises ConfigError immediately (fail fast, matching this project's
    other rule-violation guards) if `code` isn't exactly 8 characters with
    no whitespace anywhere in it -- never silently truncates or strips."""
    if len(code) != 8:
        raise ConfigError(
            f"Team code {code!r} must be exactly 8 characters (rule 45 [MUST]), "
            f"got {len(code)}."
        )
    if any(char.isspace() for char in code):
        raise ConfigError(f"Team code {code!r} must not contain spaces (rule 45 [MUST]).")
