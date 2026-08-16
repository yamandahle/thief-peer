"""report/sub_game_counter.py tests. Mirrors LeagueCounter's own test
style (report_writer.py) -- same persisted-JSON-across-instances proof,
same peek-vs-record split for uncounted warm-up runs."""

from thief_peer.report.sub_game_counter import SubGameCounter


def test_first_call_for_a_new_opponent_returns_one(tmp_path):
    counter = SubGameCounter(tmp_path / "sub_games.json")
    assert counter.next_sub_game_number("http://opponent/mcp") == 1


def test_advances_by_one_on_each_counted_call(tmp_path):
    counter = SubGameCounter(tmp_path / "sub_games.json")
    assert counter.next_sub_game_number("http://opponent/mcp") == 1
    assert counter.next_sub_game_number("http://opponent/mcp") == 2
    assert counter.next_sub_game_number("http://opponent/mcp") == 3


def test_survives_a_simulated_process_restart(tmp_path):
    path = tmp_path / "sub_games.json"
    SubGameCounter(path).next_sub_game_number("http://opponent/mcp")
    SubGameCounter(path).next_sub_game_number("http://opponent/mcp")

    fresh_instance = SubGameCounter(path)  # simulates a new process
    assert fresh_instance.next_sub_game_number("http://opponent/mcp") == 3


def test_tracks_different_opponents_independently(tmp_path):
    counter = SubGameCounter(tmp_path / "sub_games.json")
    counter.next_sub_game_number("http://opponent-a/mcp")
    counter.next_sub_game_number("http://opponent-a/mcp")
    counter.next_sub_game_number("http://opponent-b/mcp")

    assert counter.next_sub_game_number("http://opponent-a/mcp") == 3
    assert counter.next_sub_game_number("http://opponent-b/mcp") == 2


def test_an_uncounted_call_peeks_without_advancing(tmp_path):
    # A warm-up/test run (is_counted=False) must not consume a real slot
    # in the eventual series -- matches LeagueCounter's own is_counted split.
    counter = SubGameCounter(tmp_path / "sub_games.json")
    assert counter.next_sub_game_number("http://opponent/mcp") == 1  # counted

    assert counter.next_sub_game_number("http://opponent/mcp", is_counted=False) == 2
    assert counter.next_sub_game_number("http://opponent/mcp", is_counted=False) == 2

    assert counter.next_sub_game_number("http://opponent/mcp") == 2  # counted, real advance
