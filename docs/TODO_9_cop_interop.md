# TODO — Stage 9: Cop-Repo Interop Adapter + Scent-Lock Ceremony

See `PRD_9_cop_interop.md` for full rationale. Book: Ch.4.5 (scent-lock),
Ch.5.5 (Step-0). Built once the Cop repo reached its own PRD 10.

- [x] `domain/scent_lock.py`: ch.4.5 ceremony, matching Cop repo's
      `integrity/scent_model_lock.py` byte-for-byte (empirically verified)
- [x] Wired into native `negotiate()`/`peer/handshake.py` (Thief-vs-Thief)
- [x] `config/thief/game.json`: added missing `network_and_league`/
      `rate_limiter_gatekeeper` sections
- [x] `interop/cop_wire.py`: Step-0 declaration build/sign, scent
      serialize/deserialize, config hash — all verified against her
      cloned source
- [x] `interop/cop_handshake.py`: outbound Step-0 exchange + verification
      of her response
- [x] `interop/cop_turn_sender.py`: outbound commit/reveal/scent-pull/
      final-reveal/barrier/capture calls matching her exact tool surface
- [x] `interop/cop_server_tools.py`: `CopContextAdapter` + inbound tool
      registration, including resolving the `receive_barrier_declaration`/
      `receive_capture_claim` name collision with the pre-existing native
      tools of the same name
- [x] `interop/cop_round_loop.py`: `play_round_cop` (her pull-based scent
      shape, kept separate from native `play_round`)
- [x] `interop/cop_opponent.py`: `network.opponent_protocol` dispatch
      (`"native"` default / `"cop_v1"`), wired into `PeerRuntime`
- [x] `peer/match_end.py`: skips the audit exchange (tools don't exist on
      her server) when `opponent_protocol != "native"`, rather than
      crashing after an otherwise-complete match
- [x] Tests: scent-lock hash pinned + cross-verified: Step-0 signature
      cross-verified; scent wire round-trip cross-verified; a real
      live-socket test between this repo's own two adapters (client half
      calling the server half) that caught the tool-name-collision bug
      before it could reach a real match; a full `cop_v1`-mode
      `PeerRuntime.run()` test with a cooperative stub Cop opponent

**Deliberately not built** (see PRD_9 §5): making this side's own per-turn
`h_commit` verify against her real end-of-match audit — her commit
envelope is a 7-field structure this repo's own sealing doesn't produce.
A live match against her would complete negotiation, Step-0, and the full
turn loop, but the audit step is skipped/reported as "not evaluated"
rather than attempted and failed.

**Still outstanding (manual, not code):** making `config/thief/game.json`
byte-identical to her actual shared config file (a coordination step);
agreeing which side sets `initiate_step0`/whichever side dials in first;
an actual live connection test against her real running process.

**Status:** done
