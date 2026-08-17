"""interop/std_v1/series_runner.py tests -- a scripted fake peer answering
inline inside its Transport.call (mirrors test_std_v1_handshake.py's own
_PeerTransport pattern), driving a real two-sub-game series end to end
through negotiate -> round_loop -> audit -> consensus. Section 6/10
[MATCH] role alternation means sub-game 1 (odd) is our natural Thief
role and sub-game 2 (even) is our alternated Police role -- the fake
peer is therefore symmetric too: it plays Police (its own natural role,
complementary to ours) on sub-game 1 and Thief on sub-game 2, always
evading/missing so every sub-game ends in survival."""

from thief_peer.constants import Direction
from thief_peer.domain.board import Board
from thief_peer.domain.own_state import OwnGameState
from thief_peer.interop.std_v1.audit import build_audit_envelope, build_consensus_envelope
from thief_peer.interop.std_v1.crypto import (
    consensus_digest,
    derive_game_id,
    derive_game_uid,
    fresh_nonce,
)
from thief_peer.interop.std_v1.exchange import StdExchange
from thief_peer.interop.std_v1.handshake import build_offer
from thief_peer.interop.std_v1.roles import opposite_role, role_for_sub_game
from thief_peer.interop.std_v1.sealing import build_audit_record, build_turn_payload, seal_turn
from thief_peer.interop.std_v1.series_runner import NATURAL_ROLE, _row_for, play_series
from thief_peer.interop.std_v1.terms import load_terms
from thief_peer.strategy.brain_base import Decision

MY_GROUP = "thief-team"
THEIR_GROUP = "dev-team"
TERMS = {**load_terms(), "max_steps": 3, "num_games": 2}


class _FakeTurnHandler:
    """Always moves East -- same fixed pattern as round_loop's own tests."""

    def __init__(self, state):
        self.state = state

    def play_turn(self, opponent_scent_snapshot, opponent_hint_text="", own_scent_snapshot=None):
        r, c = self.state.position
        self.state.position = (r, c + 1)
        self.state.step_count += 1
        return Decision(move_type=None, direction=Direction.E, hint="")


class _FakeScent:
    def advance(self, cell):
        pass

    def snapshot(self):
        return {}


def _expected_digest(num_games: int) -> str:
    rows = [
        _row_for(n, role_for_sub_game(NATURAL_ROLE, n), "survival", False, MY_GROUP, THEIR_GROUP)
        for n in range(1, num_games + 1)
    ]
    from thief_peer.interop.std_v1.audit import build_consensus_object

    game_id = derive_game_id(MY_GROUP, THEIR_GROUP)
    game_uid = derive_game_uid(TERMS, MY_GROUP, THEIR_GROUP)
    return consensus_digest(build_consensus_object(game_id, game_uid, rows))


class _FakePeerTransport:
    """A scripted "dev-team" opponent that alternates roles the same way
    we do (complementary every sub-game): plays Police on our Thief
    sub-games (always misses, so we survive) and Thief on our Police
    sub-games (always evades, so it survives). Echoes audit/consensus
    envelopes shaped by the test's own knobs."""

    def __init__(self, my_exchange: StdExchange, peer_digest=None, peer_result_claim=None, tamper=False):
        self._exchange = my_exchange
        self._game_uid = derive_game_uid(TERMS, MY_GROUP, THEIR_GROUP)
        self._peer_digest = peer_digest
        self._peer_result_claim = peer_result_claim
        self._tamper = tamper
        self._peer_records: dict[int, list[dict]] = {}
        self._current_sub_game = 0
        self._peer_role = "police"

    def call(self, tool_name, payload, retryable=True):
        if tool_name == "negotiate":
            self._handle_negotiate(payload["message"])
        elif tool_name == "receive_turn":
            self._handle_turn(payload["message"])
        elif tool_name == "submit_audit":
            self._handle_audit(payload["payload"])
        return {"ok": True}

    def _handle_negotiate(self, offer):
        sub_game_number = offer["sub_game_number"]
        self._peer_role = opposite_role(offer["role"])
        their_offer = build_offer(
            TERMS, THEIR_GROUP, self._peer_role, sub_game_number, {"group_id": THEIR_GROUP},
            self._game_uid, fresh_nonce(),
        )
        self._exchange.record_offer(their_offer)
        self._peer_records[sub_game_number] = []
        self._current_sub_game = sub_game_number
        if self._peer_role == "thief":
            # The Thief always sends the first turn of a sub-game --
            # since this fake peer plays Thief this time, it must push
            # its own step-1 turn now, before our Police loop starts
            # waiting for it.
            self._send_thief_turn(sub_game_number, step=1, capture_claim=None)

    def _handle_turn(self, message):
        sub_game_number = self._current_sub_game
        if message["sender"] == "thief":
            step = message["step"]
            if step >= TERMS["max_steps"]:
                return  # the win-claiming final turn needs no reply
            cop_payload = build_turn_payload(
                step=step + 1, sender="police", move="STAY", hint="", smell_grid={},
                capture_claim=[0, 0],  # always misses -- the thief starts elsewhere and moves East
            )
            sealed = seal_turn(cop_payload)
            record = build_audit_record(cop_payload, sealed["nonce"])
            if self._tamper:
                record = {**record, "move": "N"}
            self._peer_records[sub_game_number].append(record)
            self._exchange.record_turn(
                {**cop_payload, "commit": sealed["commit"], "capture_claim": [0, 0], "barrier_placed": None}
            )
        else:  # message["sender"] == "police" -- our alternated turn, peer replies as Thief
            self._send_thief_turn(sub_game_number, step=message["step"] + 1, capture_claim=message["capture_claim"])

    def _send_thief_turn(self, sub_game_number, step, capture_claim):
        claim_response = {"claim": capture_claim, "caught": False} if capture_claim is not None else None
        win_claim = {"type": "survival"} if step >= TERMS["max_steps"] else None
        payload = build_turn_payload(
            step=step, sender="thief", move="STAY", hint="", smell_grid={},
            claim_response=claim_response, win_claim=win_claim,
        )
        sealed = seal_turn(payload)
        record = build_audit_record(payload, sealed["nonce"])
        if self._tamper:
            record = {**record, "move": "N"}
        self._peer_records[sub_game_number].append(record)
        self._exchange.record_turn({**payload, "commit": sealed["commit"]})

    def _handle_audit(self, payload):
        if payload.get("result_claim") == "series_consensus" and "sub_game_number" not in payload:
            digest = self._peer_digest if self._peer_digest is not None else _expected_digest(TERMS["num_games"])
            self._exchange.record_audit(build_consensus_envelope(self._peer_role, digest))
            return
        sub_game_number = payload["sub_game_number"]
        result_claim = self._peer_result_claim if self._peer_result_claim is not None else "survival"
        envelope = build_audit_envelope(
            self._peer_role, self._peer_records[sub_game_number], result_claim, sub_game_number
        )
        self._exchange.record_audit(envelope)


def _factories():
    return (
        lambda: Board(size=TERMS["board_size"], barriers=set()),
        lambda role: OwnGameState(
            position=tuple(TERMS["thief_start"] if role == "thief" else TERMS["cop_start"])
        ),
        lambda board, state: _FakeTurnHandler(state),
        lambda: _FakeScent(),
    )


def test_play_series_happy_path_reaches_agreement():
    exchange = StdExchange(poll_interval=0.01)
    transport = _FakePeerTransport(exchange)
    board_f, state_f, handler_f, scent_f = _factories()

    result = play_series(
        transport, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        board_f, state_f, handler_f, scent_f,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    )

    assert result["agreed"] is True
    rows = result["consensus_object"]["sub_games"]
    assert len(rows) == 2
    assert all(row["result"] == "survival" for row in rows)
    # sub-game 1: we play our natural Thief role and survive -> we win.
    assert rows[0]["roles"][MY_GROUP] == "thief"
    assert rows[0]["winner_group"] == MY_GROUP
    # sub-game 2: role alternates -- we play Police, the peer (playing
    # Thief) survives -> the peer wins, not us.
    assert rows[1]["roles"][MY_GROUP] == "police"
    assert rows[1]["winner_group"] == THEIR_GROUP


def test_play_series_flags_disagreement_when_peer_digest_differs():
    exchange = StdExchange(poll_interval=0.01)
    transport = _FakePeerTransport(exchange, peer_digest="0" * 64)
    board_f, state_f, handler_f, scent_f = _factories()

    result = play_series(
        transport, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        board_f, state_f, handler_f, scent_f,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    )

    assert result["agreed"] is False
    assert result["peer_consensus_sha"] == "0" * 64


def test_play_series_flags_disagreement_when_peer_result_claim_differs():
    exchange = StdExchange(poll_interval=0.01)
    transport = _FakePeerTransport(exchange, peer_result_claim="capture")
    board_f, state_f, handler_f, scent_f = _factories()

    result = play_series(
        transport, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        board_f, state_f, handler_f, scent_f,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    )

    assert result["agreed"] is False
    assert all(report["peer_result_claim"] == "capture" for report in result["sub_games"])


def test_play_series_flags_tamper_when_peer_audit_records_dont_match_what_we_saw_live():
    exchange = StdExchange(poll_interval=0.01)
    transport = _FakePeerTransport(exchange, tamper=True)
    board_f, state_f, handler_f, scent_f = _factories()

    result = play_series(
        transport, exchange, TERMS, MY_GROUP, THEIR_GROUP, {"group_id": MY_GROUP},
        board_f, state_f, handler_f, scent_f,
        turn_deadline_sec=2.0, resend_interval_sec=0.05, negotiate_ceiling_sec=2.0, audit_ceiling_sec=2.0,
    )

    assert result["agreed"] is False
    assert all(report["verify"]["tampered"] for report in result["sub_games"])
    assert all(row["result"] == "tamper_forfeit" for row in result["consensus_object"]["sub_games"])
    assert all(row["winner_group"] is None for row in result["consensus_object"]["sub_games"])
    assert all(row["score"][MY_GROUP] == 0 and row["score"][THEIR_GROUP] == 0 for row in result["consensus_object"]["sub_games"])


def test_row_for_uses_the_spec_score_table_and_flips_with_role():
    capture_row = _row_for(1, "police", "capture", False, MY_GROUP, THEIR_GROUP)
    assert capture_row["score"] == {MY_GROUP: 20, THEIR_GROUP: 5}
    assert capture_row["winner_group"] == MY_GROUP

    survival_row = _row_for(2, "thief", "survival", False, MY_GROUP, THEIR_GROUP)
    assert survival_row["score"] == {MY_GROUP: 10, THEIR_GROUP: 5}
    assert survival_row["winner_group"] == MY_GROUP

    timeout_row = _row_for(3, "thief", "timeout", False, MY_GROUP, THEIR_GROUP)
    assert timeout_row["score"] == {MY_GROUP: 0, THEIR_GROUP: 0}
    assert timeout_row["winner_group"] is None
