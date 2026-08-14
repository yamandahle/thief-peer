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


def hint_agrees_with_scent(
    region: dict[str, float] | None, scent_snapshot: dict[str, float]
) -> bool | None:
    """Book ch.4.4/6.4: scent is unforgeable ground truth, unlike the hint,
    which may lie -- `BeliefGrid.observe_hint`/`observe_scent` already blend
    the two mathematically every round (a lying hint can never outweigh
    real scent), but that comparison was previously never made explicit
    anywhere, logged, or tracked. `region` is the hint's own already-parsed
    direction cue (`parse_direction_cue`'s output, reused rather than
    reparsed); `scent_snapshot` is the same opponent-reported trail already
    folded into the belief this round. Returns `None` when there's nothing
    to compare -- no direction word in the hint, or no scent reported yet
    (e.g. the opponent's first move) -- never a fabricated verdict; `True`
    when the single most-scented cell falls inside the hinted region,
    `False` otherwise."""
    if region is None or not scent_snapshot:
        return None
    peak_cell = max(scent_snapshot, key=scent_snapshot.get)
    return peak_cell in region
