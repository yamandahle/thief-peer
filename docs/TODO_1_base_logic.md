# TODO — Stage 1: Base Logic

See `PRD_1_base_logic.md` for full rationale. Book: Ch.3.
PRD milestone: "Thief agent moves legally on the grid in isolation."

- [x] Scaffold repo: `src/thief_peer/`, `tests/{unit,integration}`,
      `config/thief/`, `data/`, `results/`, `assets/`, `notebooks/`
- [x] `pyproject.toml`: uv, ruff (`select=[E,F,W,I,N,UP,B,C4,SIM]`),
      `pytest-cov` with `fail_under = 85`
- [x] `.gitignore` (`.env`, `credentials.json`, `token.json`, `*.key`, `*.pem`,
      `logs/`, `results/`) + `.env-example` with dummy placeholders
- [x] `constants.py`: `Direction` (N/S/E/W only — no diagonals), `MoveType`,
      `NONCE_BYTES`, fixed protocol strings
- [x] `exceptions.py`: `ConfigError`, `CryptoError`, `SimulationError`, `ProviderError`
- [x] `domain/board.py`: `Board.legal_moves()` / `distance()` (Manhattan) /
      `in_bounds()` / `is_barrier()`, respecting barriers — *(corrected
      during implementation: no `Board.step()`; state mutation deliberately
      lives on `OwnGameState.apply_move`, per PRD_1 §4's immutable-Board
      decision, not on `Board` itself)*
- [x] `domain/own_state.py`: `OwnGameState` (position, visited trail, step
      count, known barriers)
- [x] `domain/rules.py`: capture-on-barrier-cell, no-legal-move-capture
      (stuck), survival-threshold checks
- [x] `shared/config.py` (v0): private TOML loader only, dotted `.get()` API
- [x] Unit tests for board/own_state/rules — happy path + edge cases (no legal
      moves, off-board, barrier-occupied cell)

**Done when:** a single Python process builds a board + Thief state and
enumerates legal N/S/E/W/STAY moves respecting a hardcoded barrier set and
capture/survival rules, fully unit-tested — no network code exists yet.
✅ **Met** — 43 unit tests, 100% coverage (≥85% required), `ruff check` clean,
all files well under the 150-line cap.

**Status:** done
