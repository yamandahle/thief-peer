"""round_reporter.py tests (dev/observability tool only). Only the new
hint-vs-scent lie-detection surfacing (book ch.4.4/6.4, backlog item 17) is
covered here -- the rest of this module is pure terminal output over data
the runtime loop already has, with no dedicated tests before this."""

from thief_peer.peer.round_reporter import print_match_summary, print_round_summary

_RECORD = {"payload": {"move": "N", "hint_text": "cold"}}


def test_print_round_summary_reports_agrees_when_hint_agreement_is_true(capsys):
    print_round_summary(1, 35, "Thief-Team", "Cop-Team", _RECORD, "north", 0, (3, 3), 35, hint_agreement=True)

    out = capsys.readouterr().out
    assert "AGREES with their scent" in out


def test_print_round_summary_reports_contradicts_when_hint_agreement_is_false(capsys):
    print_round_summary(1, 35, "Thief-Team", "Cop-Team", _RECORD, "north", 0, (3, 3), 35, hint_agreement=False)

    out = capsys.readouterr().out
    assert "CONTRADICTS their scent" in out


def test_print_round_summary_reports_no_signal_when_hint_agreement_is_none(capsys):
    print_round_summary(1, 35, "Thief-Team", "Cop-Team", _RECORD, "north", 0, (3, 3), 35)

    out = capsys.readouterr().out
    assert "no signal to compare" in out


def _match_result():
    return {
        "final_result": {"winner_group": "Thief-Team", "total_score": {}, "tokens_total_series": {}},
        "audit": {"passed": True},
    }


def test_print_match_summary_reports_the_contradiction_count(capsys):
    print_match_summary(_match_result(), "Thief-Team", hint_agreement_log=[True, False, False, None])

    out = capsys.readouterr().out
    assert "contradicted their own scent in 2/3 comparable round(s)" in out


def test_print_match_summary_omits_the_line_when_nothing_was_ever_comparable(capsys):
    print_match_summary(_match_result(), "Thief-Team", hint_agreement_log=[None, None])

    out = capsys.readouterr().out
    assert "Their hints:" not in out


def test_print_match_summary_omits_the_line_when_no_log_is_given(capsys):
    print_match_summary(_match_result(), "Thief-Team")

    out = capsys.readouterr().out
    assert "Their hints:" not in out
