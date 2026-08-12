"""Organized per-round + match-summary terminal output for `cli.py run`
(dev/observability tool only -- pure print helpers over data the runtime
loop already has, no state of its own, not part of any report artifact or
wire protocol)."""


def print_round_summary(
    step: int,
    max_moves: int,
    group_name: str,
    opponent_group_name: str,
    record: dict,
    opponent_hint: str,
    known_barrier_count: int,
    position: tuple[int, int],
    survival_threshold: int,
) -> None:
    payload = record["payload"]
    move = payload["move"]
    # native mode: a plain string ("S"/"STAY"); cop_v1 interop mode: a
    # {"type", "direction"} envelope (interop/cop_wire.py's
    # build_cop_move_envelope) -- normalize both to one display string.
    move_display = move if isinstance(move, str) else move.get("direction", move.get("type", "?"))
    print(f"\n{'-' * 60}")
    print(f"Round {step}/{max_moves} -- {group_name} vs {opponent_group_name}")
    print(f"  My move:        {move_display:<6} (position now: {position})")
    print(f"  My hint:        {payload['hint_text']!r}")
    print(f"  Their hint:     {opponent_hint!r}")
    print(f"  Barriers known: {known_barrier_count}")
    print(f"  Survival:       step {step}/{survival_threshold} toward the survival threshold")
    print("-" * 60)


def print_score_breakdown(brain, belief, board, state) -> None:
    """Diagnostic only (not wired in by default): the actual weighted-sum
    score and its three components for every legal move this turn, so
    "why did it pick this move" can be answered by reading real numbers
    instead of guessing."""
    barriers = frozenset(state.known_barriers)
    moves = board.legal_moves(state.position, barriers)
    print(f"  Belief most-likely opponent cell: {belief.most_likely()}")
    print("  Score breakdown (move: expected_distance / mobility / lookahead -> total):")
    for direction, cell in moves:
        expected_distance = brain._expected_distance(cell, belief, board)
        mobility = brain._mobility_score(cell, board, barriers)
        lookahead = brain._lookahead_score(cell, belief, board)
        total = (
            brain._expected_distance_weight * expected_distance
            + brain._mobility_weight * mobility
            + brain._lookahead_weight * lookahead
        )
        label = direction.value if direction else "STAY"
        print(f"    {label:<5}: {expected_distance:6.2f} / {mobility} / {lookahead:5.2f} -> {total:7.2f}")


def print_match_summary(result: dict, group_name: str) -> None:
    final = result["final_result"]
    audit = result["audit"]
    print(f"\n{'=' * 60}")
    winner = final["winner_group"]
    outcome = "WON" if winner == group_name else "LOST"
    print(f"MATCH OVER -- {outcome} (winner: {winner})")
    print(f"  Score:        {final['total_score']}")
    print(f"  Audit passed: {audit['passed']}")
    print(f"  Tokens used:  {final['tokens_total_series']}")
    print("=" * 60)
