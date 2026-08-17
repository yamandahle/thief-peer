"""interop/std_v1/round_loop.py tests -- fakes mirror test_round_loop.py's
own style for the native protocol's play_round."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.round_loop import play_sub_game
from thief_peer.strategy.brain_base import Decision


class _FakeTurnHandler:
    """Always moves East -- deterministic, so tests can pre-compute
    exactly where the Thief will be at each step."""

    def __init__(self, state):
        self.state = state

    def play_turn(self, opponent_scent_snapshot, opponent_hint_text="", own_scent_snapshot=None):
        decision = Decision(move_type=None, direction=Direction.E, hint="cold")
        r, c = self.state.position
        self.state.position = (r, c + 1)
        self.state.step_count += 1
        return decision


class _FakeScent:
    def advance(self, cell):
        pass

    def snapshot(self):
        return {}


class _SpyTransport:
    def __init__(self):
        self.sent_messages = []

    def call(self, tool_name, payload, retryable=True):
        if tool_name == "receive_turn":
            self.sent_messages.append(payload["message"])
        return {"ok": True}


def _cop_turn(step, capture_claim, barrier_placed=None, commit="fake-commit"):
    return {
        "step": step, "sender": "police", "capture_claim": capture_claim,
        "barrier_placed": barrier_placed, "hint": "", "smell_grid": {}, "commit": commit,
    }


def test_survival_when_max_steps_reached_without_capture():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_cop_turn(2, capture_claim=[6, 6]))  # far away, never catches

    end_reason, records, peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=3, turn_deadline_sec=1.0,
    )

    assert end_reason == "survival"
    assert records[-1]["step"] == 3
    assert records[-1]["win_claim"] == {"type": "survival"}
    assert peer_commits == {2: "fake-commit"}


def test_capture_when_the_cop_lands_on_the_thief():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)
    # Thief moves E to (3,4) at step 1; Cop's step-2 claim matches it.
    exchange.record_turn(_cop_turn(2, capture_claim=[3, 4]))

    end_reason, records, _peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=35, turn_deadline_sec=1.0,
    )

    assert end_reason == "capture"
    # The final record is the caught Thief's own sealed no-move STAY,
    # carrying the truthful claim_response.
    assert records[-1]["move"] == "STAY"
    assert records[-1]["claim_response"] == {"claim": [3, 4], "caught": True}


def test_no_capture_when_the_claim_misses():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_cop_turn(2, capture_claim=[0, 0]))
    exchange.record_turn(_cop_turn(4, capture_claim=[0, 0]))
    exchange.record_turn(_cop_turn(6, capture_claim=[0, 0]))

    end_reason, _records, _peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=5, turn_deadline_sec=1.0,
    )

    assert end_reason == "survival"


def test_claim_response_is_carried_on_the_next_outgoing_turn():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_cop_turn(2, capture_claim=[0, 0]))  # misses
    exchange.record_turn(_cop_turn(4, capture_claim=[0, 0]))  # misses

    transport = _SpyTransport()
    play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), transport, exchange,
        max_steps=3, turn_deadline_sec=1.0,
    )

    # Step 1 has no claim_response yet (nothing received from the Cop).
    step_1 = next(m for m in transport.sent_messages if m["step"] == 1)
    assert step_1["claim_response"] is None
    # Step 3 carries the answer to the Cop's step-2 claim.
    step_3 = next(m for m in transport.sent_messages if m["step"] == 3)
    assert step_3["claim_response"] == {"claim": [0, 0], "caught": False}


def test_timeout_when_the_cop_never_replies():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)  # nothing recorded

    end_reason, records, peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=35, turn_deadline_sec=0.1,
    )

    assert end_reason == "timeout"
    assert len(records) == 1
    assert peer_commits == {}


def test_a_barrier_that_traps_the_thief_is_a_capture_via_condition_c():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(0, 0))
    exchange = StdExchange(poll_interval=0.01)
    # Thief moves E to (0,1) at step 1, which has exactly three in-bounds
    # orthogonal neighbors: (0,0), (0,2), (1,1). Two are already known
    # barriers; the Cop's step-2 turn declares the third, trapping it --
    # a capture via condition C even though the claim itself, [6,6],
    # misses entirely.
    state.record_barrier((0, 0))
    state.record_barrier((0, 2))
    exchange.record_turn(_cop_turn(2, capture_claim=[6, 6], barrier_placed=[1, 1]))

    end_reason, _records, _peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=35, turn_deadline_sec=1.0,
    )

    assert end_reason == "capture"


def test_peer_commits_are_tracked_across_multiple_cop_turns():
    board = Board(size=7, barriers=set())
    state = OwnGameState(position=(3, 3))
    exchange = StdExchange(poll_interval=0.01)
    exchange.record_turn(_cop_turn(2, capture_claim=[0, 0], commit="commit-2"))
    exchange.record_turn(_cop_turn(4, capture_claim=[0, 0], commit="commit-4"))

    _end_reason, _records, peer_commits = play_sub_game(
        _FakeTurnHandler(state), board, state, _FakeScent(), _SpyTransport(), exchange,
        max_steps=5, turn_deadline_sec=1.0,
    )

    assert peer_commits == {2: "commit-2", 4: "commit-4"}
