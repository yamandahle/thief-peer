# TODO — Stage 1: Base Logic

See `PRD_1_base_logic.md` for full rationale. Book: Ch.3.
PRD milestone: "Thief agent moves legally on the grid in isolation."

- [ ] Scaffold repo: `src/thief_peer/`, `tests/{unit,integration}`,
      `config/thief/`, `data/`, `results/`, `assets/`, `notebooks/`
- [ ] `pyproject.toml`: uv, ruff (`select=[E,F,W,I,N,UP,B,C4,SIM]`),
      `pytest-cov` with `fail_under = 85`
- [ ] `.gitignore` (`.env`, `credentials.json`, `token.json`, `*.key`, `*.pem`,
      `logs/`, `results/`) + `.env-example` with dummy placeholders
- [ ] `constants.py`: `Direction` (N/S/E/W only — no diagonals), `MoveType`,
      `NONCE_BYTES`, fixed protocol strings
- [ ] `exceptions.py`: `ConfigError`, `CryptoError`, `SimulationError`, `ProviderError`
- [ ] `domain/board.py`: `Board.legal_moves()` / `distance()` (Manhattan) /
      `in_bounds()` / `step()`, respecting barriers
- [ ] `domain/own_state.py`: `OwnGameState` (position, visited trail, step log,
      known barriers)
- [ ] `domain/rules.py`: capture-on-barrier-cell, no-legal-move-capture,
      survival-threshold checks
- [ ] `shared/config.py` (v0): private TOML loader only, dotted `.get()` API
- [ ] Unit tests for board/own_state/rules — happy path + edge cases (no legal
      moves, off-board, barrier-occupied cell)

**Done when:** a single Python process builds a board + Thief state and
enumerates legal N/S/E/W/STAY moves respecting a hardcoded barrier set and
capture/survival rules, fully unit-tested — no network code exists yet.

**Status:** not started
