"""Compass-direction hint parsing (book Ch.6.4, page 47: "on every incoming
hint, apply Bayes' rule to update probabilities, placing a reliability
coefficient on the text"). A small, deterministic, symmetric vocabulary
both sides already share -- plain string matching, never an LLM (page 49
forbids letting the LLM touch spatial/movement decisions, only the verbal
layer). Returns `None` when no direction word is found, so
`BeliefGrid.observe_hint` stays an honest no-op rather than fabricating a
signal the hint text didn't actually contain.
"""

_NORTH, _SOUTH, _EAST, _WEST = "north", "south", "east", "west"


def parse_direction_cue(hint_text: str, board_size: int) -> dict[str, float] | None:
    """Substring-matches the four cardinal words (case-insensitive) --
    this alone also naturally catches diagonals ("northeast", "north-east",
    "north east") and adjectival forms ("northern side") since each still
    contains the cardinal word as a substring. Returns a sparse
    `{"row,col": 1.0}` map over whichever half/quadrant of the board the
    matched word(s) name, or None if no direction word appears at all."""
    text = hint_text.lower()
    north, south = _NORTH in text, _SOUTH in text
    east, west = _EAST in text, _WEST in text
    if not (north or south or east or west):
        return None

    row_mid = board_size // 2
    if north and not south:
        rows = range(0, row_mid)
    elif south and not north:
        rows = range(row_mid, board_size)
    else:
        rows = range(0, board_size)

    col_mid = board_size // 2
    if west and not east:
        cols = range(0, col_mid)
    elif east and not west:
        cols = range(col_mid, board_size)
    else:
        cols = range(0, board_size)

    return {f"{r},{c}": 1.0 for r in rows for c in cols}
