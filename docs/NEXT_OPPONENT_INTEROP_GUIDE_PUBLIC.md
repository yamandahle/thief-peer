# P2P Cop–Thief Match Interoperability Specification

This document defines the protocol, configuration and reporting requirements two independent
implementations must satisfy to play a peer-to-peer Cop–Thief series against each other.

Terminology: **local peer** and **remote peer** denote the two running agents; **each team**
denotes the two participating groups. **MUST**, **MUST NOT**, **SHOULD** and **MAY** carry their
usual normative meaning.

Requirement markers:

- **[MATCH]** — MUST be identical or compatible on both sides; otherwise the series cannot
  complete correctly.
- **[REPORT]** — MUST appear in each team's own `result_<game_id>.json` (Section 12), although it
  is excluded from the canonical consensus hash. Some [REPORT] values originate with the remote
  peer and therefore MUST be exchanged during negotiation (Section 3).
- **[LOCAL]** — an implementation detail each team chooses freely.

---

## 1. Quick Start

1. Adopt the same 14 signed terms (Section 2 / Appendix A).
2. Expose a public MCP endpoint at path `/mcp`, reachable from the public internet, with no
   required bearer authentication (Section 7).
3. Agree a shared `game_id` label out of band. It MUST be identical on both sides; `game_uid`
   then derives identically for both peers (Section 3).
4. Agree complementary starting roles (Section 10).
5. Exchange the identity and reporting fields listed in Section 3.
6. Run the non-counted compatibility test (Section 15).
7. Exchange the Ready template (Section 16), then play.

---

## 2. Signed Terms

The negotiated agreement is a flat, closed set of exactly 14 keys. It is not a nested
configuration object. Adding, renaming or dropping a key changes the object and its signature,
and the handshake is refused.

**[MATCH]** Use the exact JSON values and types of Appendix A. Term objects are compared after
parsing (key order and whitespace are irrelevant), but `game_uid` and the terms signature are
computed over the **canonical bytes** of the terms, so JSON types matter: `0.1` / `0.9` as JSON
numbers, coordinates as integer arrays, strings exactly as given. Two representations a language
may treat as equal (an integer versus a float, for example) can still produce different canonical
bytes, and therefore a different signature and `game_uid`.

**[MATCH] The 14 signed terms:**

| Key | Value | Meaning |
|---|---|---|
| `board_size` | `7` | 7×7 grid |
| `smell_grid_size` | `5` | 5×5 scent kernel footprint |
| `decay_per_step` | `0.1` | scent decay ρ per turn |
| `emit_intensity` | `0.9` | scent centre intensity (also the cap) |
| `min_center_intensity` | `0.5` | scent centre floor |
| `max_steps` | `35` | maximum turns and the Thief survival threshold |
| `barriers_max` | `14` | maximum barriers a Cop may place in a sub-game |
| `setting` | `"Haifa"` | world/theme string (signed, so it MUST match) |
| `hint_max_words` | `15` | maximum words in a turn hint |
| `axis_origin_corner` | `"top-left"` | cell (0,0) is top-left |
| `axis_start_index` | `0` | indices start at 0 |
| `thief_start` | `[3, 3]` | Thief spawn |
| `cop_start` | `[0, 0]` | Cop spawn |
| `num_games` | `6` | sub-games in the official series |

**Coordinate convention:** `[row, col]`, values `0..6`. Row grows downward (south); column grows
right (east); origin top-left.

**[LOCAL] Outside the signed set:** scoring values (fixed by the rules, Section 6, and not
negotiated), any `schema_version` field, and any league or rate-limiter settings such as
per-request timeouts and token budgets. Only the 14 keys above are exchanged and signed.

A companion `config/game.json` may accompany this specification: it is the rulebook's shared
constitution file in sectioned form, carrying the same board, movement, scoring and pheromone
values plus league and rate-limiter settings, and naming both teams in `agreed_between`. Only the
14 flat keys above cross the wire and enter the signature and `game_uid`. `min_center_intensity`
is the one signed term with no counterpart section in that file.

---

## 3. Identity & Negotiation

Both peers exchange a signed negotiation message before **each** sub-game (a fresh handshake per
sub-game).

**Negotiation fields:**

- `terms` **[MATCH]** — the 14 signed terms.
- `nonce`, `signature` **[MATCH]** — `signature = commit_of(terms, nonce)` (Appendix B).
- `group_id` **[MATCH]** — non-empty; used to derive the shared ids. A greeting without it is
  refused.
- `role` **[MATCH]** — wire role for this sub-game (`"police"` / `"thief"`).
- `sub_game_number` **[MATCH]** — `1..6`.
- `identity` **[MATCH]** — the identity block below.
- `game_uid` **[MATCH]** — the derived id below.

**Identity block** (inside `identity`). Every field is **[REPORT]**: each team's report names both
groups, so a field the remote peer never sends cannot appear in the local peer's report.

- `group_id`, `group_name` **[MATCH]** — the group id, spelled identically everywhere; it keys the
  consensus rows.
- `git_commit_hash` and `github_commit` **[REPORT]** — the real 40-character commit the running
  code was built from. It MUST be sent in **every** per-sub-game handshake and MUST be updated if
  the code is redeployed mid-series; the report requires the commit **per sub-game**, and
  different sub-games MAY legitimately carry different values. A value that is not exactly 40 hex
  characters is treated as absent.
- `members` **[MATCH] [REPORT]** — a non-empty list of team members.
- `repos` **[REPORT]** — `{"cop": "<url>", "thief": "<url>"}`, the two public repository URLs.
  Each team's report MUST carry four repository links, and this field is the only source for the
  remote peer's two.
- `mcp_servers` **[REPORT]** — a role→URL map, e.g. `{"cop": "<url>", "thief": "<url>"}`. It MUST
  be non-empty. The two entries need not differ; one URL MAY serve both roles.
- `llm_model` and `spec` **[REPORT]** — the model name and the machine specification
  (CPU, cores, RAM, GPU). Reported only; never validated against the sender.

**Greeting validation.** A receiver MUST refuse a greeting when:

1. `terms` is absent or is not an object.
2. `terms` does not contain all 14 keys.
3. `terms` differs from the local terms (this is where a wrong `setting`, `hint_max_words` or
   start cell stops the series).
4. `nonce` or `signature` is absent, or the signature does not verify against the sender's terms.
5. `group_id` is absent, leaving no derivable `game_id`.
6. A declared `game_uid` differs from the derived one.

**[MATCH] The handshake is mutual, not a single POST.** A single successful `negotiate` call MUST
NOT be treated as a completed handshake. A sender MAY re-send the identical offer — same `nonce`,
`terms` and `identity`, never regenerated on a retry — until the remote offer for the same
`sub_game_number` has arrived. Consequently:

- Receivers MUST be idempotent: a repeated, identical offer is accepted again, never rejected as a
  duplicate and never treated as a second, conflicting greeting.
- Offers are matched by `sub_game_number`. An offer tagged for a different sub-game MAY be skipped
  as a straggler; an offer without the field is accepted on arrival.
- The exchange is bounded. If no matching offer arrives, the sub-game fails as in Section 13.

**Shared ids** — computed identically by both sides and order-independent (Appendix B):

- `game_id` is the two group ids sorted and joined by the literal string `"-vs-"`.
- `game_uid` is a UUID built from the first 16 bytes of a SHA-256 over `canonical(terms)`, a
  literal `"|"`, and the two sorted group ids joined by a literal `"|"`.
- `game_id` MAY be overridden by a mutually agreed label used as the artifact filename base. Both
  sides MUST then use the identical value, because `game_id` is part of the consensus hash
  (Section 11). `game_uid` is never overridden.

---

## 4. Movement & Barriers

- **[MATCH]** Legal move tokens are `N`, `S`, `E`, `W`, `STAY` only. A move to a neighbour is
  legal if and only if that cell is in bounds and not a barrier. `STAY` is always legal.
- **[MATCH]** Barriers are placed by the Cop only. A barrier turn foregoes movement: the Cop's
  move serialises as `STAY` and the barrier is declared separately in
  `barrier_placed = [row, col]`, never as a move token.
- **[MATCH]** Barriers block both agents; a barrier cell is impassable for everyone.
- **[MATCH]** Barrier legality: the target cell MUST be in bounds and not already a barrier, and
  at most `barriers_max` = 14 barriers may be placed per sub-game.

---

## 5. Capture Semantics

Both implementations MUST behave identically here, or results diverge.

**[MATCH] The Cop declares a capture-claim for its own post-move cell on every Cop turn**,
including `STAY` turns and barrier turns, with no gating. The claim is
`capture_claim = [row, col]`, the Cop's position after its action. It belongs to the protocol
layer, MUST NOT be chosen by strategy and MUST NOT be suppressed. A Thief never emits a
capture-claim.

**[MATCH] The barrier cell is not the capture-claim.** A barrier is carried in `barrier_placed`;
the claim is always the Cop's own cell.

**[MATCH] The Thief evaluates capture against its own true current cell.** All three conditions
are terminal and end the sub-game as a capture:

- **(A) Claim co-location** — the received `capture_claim` equals the Thief's current cell.
- **(B) Barrier on the Thief** — the declared `barrier_placed` cell equals the Thief's current
  cell.
- **(C) Thief trapped** — after the declared barrier is applied, the Thief has no passable
  orthogonal neighbour (every N/S/E/W neighbour is a barrier or off-board).

(B) and (C) are evaluated when the Cop declares a barrier; a barrier-less turn evaluates (A) only.

**[MATCH] Truthful response and concession:**

- The Thief answers on its next message with
  `claim_response = {"claim": [row, col], "caught": true|false}`, set truthfully by comparing the
  received claim or barrier against its real position.
- A caught Thief then holds — a sealed no-move `STAY` — and the sub-game ends. It MUST NOT make a
  further gameplay move.
- The Cop learns it has won on receiving `claim_response.caught == true`.
- Both the claim and the response are sealed into the signed per-turn records for the audit.

An implementation that gates or omits the claim, or that answers untruthfully, causes missed or
disputed captures.

---

## 6. Scoring

Scoring is fixed by the rules and is not negotiated.

| Outcome | Cop | Thief |
|---|---|---|
| `capture` | 20 | 5 |
| `survival` | 5 | 10 |
| `timeout` | 0 | 0 |
| `technical_loss` | 0 | 0 |
| `tamper_forfeit` | 0 | 0 |

- **Per sub-game:** award by role from the table.
- **Role alternation:** odd sub-games (1, 3, 5) play the natural role, even sub-games (2, 4, 6)
  the opposite.
- **Cumulative series:** sum per group across the six sub-games.
- **Series tie bonus:** `+2` is added once to each side, and only when the cumulative totals are
  equal. It is not a per-sub-game bonus.
- **Winner:** the group with the higher cumulative total; none when tied.
- Zeroed outcomes (`timeout`, `technical_loss`, `tamper_forfeit`) score 0/0 and never count as a
  scoring tie.

Worked tie example: if every sub-game ends in survival, each team is Cop three times and Thief
three times, giving `3×5 + 3×10 = 45` each; equal totals add `+2` to each, for 47–47.

---

## 7. MCP Transport & Server

- **Architecture:** symmetric push model with no central server. Each peer runs its own MCP server
  exposing four receive tools, and pushes messages to the other's server.
- **Endpoint path:** `/mcp`; public URL shape `https://<public-host>/mcp`.
- **[MATCH] Four tools**, with these exact tool and argument names:
  - `negotiate(message)` — signed agreement
  - `receive_turn(message)` — a turn message
  - `submit_audit(payload)` — end-of-sub-game reveal or consensus digest
  - `receive_control(message)` — control signal

  `submit_audit` takes **`payload`**; the other three take **`message`**.
- **[MATCH] No bearer authentication.** Neither side sends an `Authorization` header by default,
  and an endpoint MUST NOT require a bearer token.
- **[MATCH] Handlers MUST enqueue and return immediately.** A receive tool validates lightly,
  queues the message and returns `{"ok": true}`. Long computation inside the request handler
  causes request timeouts and can deadlock the push model.
- **[MATCH] Graceful shutdown.** A peer MUST keep serving until the remote peer's final
  `submit_audit` has been delivered, then shut down. Exiting immediately after gameplay makes the
  remote peer observe a failed final audit.
- **[LOCAL] Timeouts.** Each team chooses its own. Outbound calls SHOULD retry transient errors
  for a bounded window, and the per-turn wait before declaring a `timeout` SHOULD be generous
  (minutes). Waits for the end-of-sub-game audit and for the final consensus envelope are bounded
  and materially shorter, so both MUST be sent promptly: a late audit may be recorded as "no audit
  received" — unverified and not agreed — even when the gameplay itself was clean.

---

## 8. Network Readiness

A running local server does not prove the public endpoint is reachable. Both endpoints MUST be
reachable from the public internet before negotiation starts.

- Public routing or origin errors (HTTP 502 / 520 / 530 and similar) mean an edge or proxy was
  reached but could not obtain a healthy response from the origin behind it. The specific cause
  can only be read from the response body; it MUST NOT be inferred from the status code alone.
  Broken routing is fixed at the endpoint, never by changing gameplay or protocol.
- Ephemeral tunnels may change their public URL on restart. Treat the public URL as dynamic:
  publish the current URL immediately before the series, keep the tunnel up for its duration, and
  re-publish it after any restart.

Reachability check, run by each team against its own URL:

```
curl -sS -o /dev/null -w '%{http_code}\n' https://<public-host>/mcp
```

A `4xx` (typically `405` or `406`) indicates the endpoint is up and rejected a bare GET; a `502`,
`520`, `530`, connection refused or timeout indicates it is not ready.

---

## 9. Messages, Commit-Reveal & Digests

- **Canonical JSON**, used for every hash and signature:
  `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
- **Commit-reveal:** each turn payload is sealed as `commit = commit_of(payload, nonce)`
  (Appendix B). The commit is sent during play; the nonce is withheld until the end-of-sub-game
  audit.
- **Turn message fields:** `step`, `sender` (`"police"` / `"thief"`), `commit`, `hint`,
  `smell_grid` (`{"r,c": intensity}`), `timestamp`, `barrier_placed`, `capture_claim`,
  `claim_response`, `win_claim`. Required on parse: `step`, `sender`, `commit`. Optional fields MAY
  be sent explicitly as `null` or omitted, and receivers MUST tolerate either.
  - `win_claim` carries the Thief's `{"type": "survival"}` when it reaches the threshold.
- **Audit payload fields:** `sender`, `records`, `result_claim`, plus two optional fields,
  `consensus_sha` and `sub_game_number`. Optional fields are omitted entirely when absent rather
  than sent as `null`.
  - `consensus_sha` MUST be exactly 64 lowercase hex characters when present; any other value is
    ignored.
  - `sub_game_number` identifies the sub-game an audit belongs to (Section 10). Senders SHOULD
    include it. Receivers MUST accept envelopes that omit it, and MUST NOT require it.
- **End-of-sub-game mutual audit:** each side sends its full `records` with `result_claim`; the
  receiver re-hashes every record with its own serializer and checks that each revealed commit
  matches what was played. Both sides record whether the remote log verified untampered and
  whether both claimed the same outcome.

Appendix B gives literal, reproducible derivations.

---

## 10. Match Lifecycle & Final Audit

- **[MATCH]** An official series is exactly `num_games` = 6 sub-games, played in order 1→6 with
  role alternation (Section 6).
- **[MATCH]** Both teams MUST explicitly agree complementary starting roles before the series.
- A fresh handshake and a fresh sub-game runtime are used per sub-game; transport and servers are
  reused across the series.
- **Turn order:** the Thief sends the first turn of each sub-game; the peers then alternate.
- **A sub-game ends** on capture (Section 5), survival (the Thief reaches `max_steps`), `timeout`
  (the remote peer is silent past the per-turn deadline), or `technical_loss` (a protocol or
  ordering violation, which is classified rather than aborting the series).
- **[MATCH] Survival occurs at exactly `max_steps` = 35 completed steps** — not 34, not 36. The
  Thief raises `win_claim = {"type": "survival"}` when its step count reaches the threshold. Step
  34 completed without capture is not yet survival; step 35 completed without capture is survival.
  For scoring and consensus, a survival's `steps` is recorded as the threshold (35) by both peers.
- A peer MAY conclude survival as soon as the step count reaches `max_steps` without a capture,
  rather than waiting for the Thief's `win_claim`, and proceed directly to the audit exchange.
  Implementations MUST NOT depend on any message sent after the threshold being read, and MUST NOT
  declare survival before the threshold — silence before it is a `timeout`.

**Final audit and consensus exchange, after the last sub-game:**

1. Per-sub-game mutual audits have already occurred at the end of each sub-game. An audit envelope
   carrying `sub_game_number` is filed against that sub-game; an envelope belonging to a different
   sub-game (for example a straggler delivered across a role swap) MAY be skipped rather than
   filed against the current one. An envelope without the field is taken on arrival.
2. Each side computes the canonical series digest over the six rows (Section 11 / Appendix C).
3. **[MATCH] Explicit consensus exchange.** Send an audit envelope with:
   - `sender` = a wire role string (`"police"` or `"thief"`), never a group id;
   - `result_claim` = `"series_consensus"`;
   - `records` = `[]`;
   - `consensus_sha` = the 64-lowercase-hex series digest.

   Then wait, bounded, for the remote envelope. Its digest MUST be accepted only if all hold:
   `result_claim == "series_consensus"`, `records == []`, `consensus_sha` present and exactly 64
   lowercase hex, and `sender` is a wire role. Because roles alternate, a peer's natural role and
   its final-sub-game role differ over an even-length series, so a receiver MUST accept **either**
   of the remote peer's two wire roles. A `sender` that is not a wire role MUST be rejected.
   Straggler per-sub-game audits arriving in this window carry no `consensus_sha` and MUST NOT be
   mistaken for a consensus envelope.
4. Agreement is **confirmed** only when every remote log verified untampered, every sub-game
   result was mutually agreed, **and** a received remote digest equals the local one. A locally
   computed digest alone MUST NOT confirm agreement.

---

## 11. Canonical Consensus Object

This object is the one cross-team join beyond the signed terms, and MUST be computed identically
on both sides.

**[MATCH] Top-level object — exactly three keys:**

```
{ "game_id": <str>, "game_uid": <str>, "sub_games": [ ...6 rows, ordered g01→g06... ] }
```

**[MATCH] Each sub-game row — exactly five keys:**

```
{
  "sub_game_number": <int 1..6>,
  "result": "capture" | "survival" | "timeout" | "technical_loss" | "tamper_forfeit",
  "roles":  { "<groupA>": "police|thief", "<groupB>": "police|thief" },
  "score":  { "<groupA>": <int>,          "<groupB>": <int> },
  "winner_group": "<groupId>" | null
}
```

- `roles` and `score` are keyed by group id, not by `"cop"` / `"thief"`, so sorted-key JSON is
  byte-identical on both sides.
- `winner_group` is `null` on a per-sub-game score tie, otherwise the higher-scoring group id.
- Rows are ordered strictly by ascending `sub_game_number`.

**[MATCH] Serialization and hash:**

```python
import hashlib, json

canon = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
sha = hashlib.sha256(canon).hexdigest()
```

**Excluded from the canonical object** (present in the full report, but not hashed): steps, tie
metadata, timestamps, timezone, token usage, commit hashes, filenames, audit detail, capture
evidence, final totals and any local metadata.

Consequently the two teams' report files need not be byte-identical; only this object and its
digest must match.

---

## 12. Result Report

Each team produces and submits its own `result_<game_id>.json`. Two distinct requirements meet in
that file.

**[MATCH] What the two files MUST agree on:** `game_id`, `game_uid` and the six canonical rows
(`sub_game_number`, `result`, `roles`, `score`, `winner_group`) — and therefore the canonical
digest (Section 11) and the mutual-agreement outcome. Nothing else is compared.

**[REPORT] What each file MUST contain on its own:**

| Field | Location | Notes |
|---|---|---|
| game identification | `game_id`, `game_uid`, `report_type`, `schema_version` | filename is exactly `result_<game_id>.json` |
| both group ids | `groups` | spelled exactly as negotiated |
| six sub-game rows | `sub_games` | ordered 1→6 |
| roles, result, winner | per row: `roles`, `result`, `winner_group`, `tie` | keyed by group id |
| score | per row: `score`; series: `final_result.total_score` | Section 6, tie bonus included |
| per-sub-game commit | per row: `github_commit` = `{groupA: <40-hex>, groupB: <40-hex>}` | the commit each side played in that sub-game |
| tokens | per row: `tokens`; series: `final_result.tokens_total_series` | actual model-token consumption; `0` when none was used |
| four repository links | `links.github` = `{groupA: {cop, thief}, groupB: {cop, thief}}` | both teams' Cop and Thief repositories |
| identity, MCP, hardware | `group_details` per group: `group_id`, `members`, `repos`, `mcp_servers`, `llm_model`, `hardware_spec` | static declaration data for both groups |
| timestamps | `timezone`, `game_started_at`, `game_ended_at`; per row `started_at`, `ended_at` | |
| audit and log reference | per row: `audit` (`log_verified`, `tampered`, `result_agreed`), `log_files`, `steps` | per-sub-game mutual audit outcome |
| mutual agreement | `mutual_agreement`: `sha256`, `peer_sha256`, `sha_match`, `results_agreed`, `confirmed` | `confirmed` per Section 10 step 4 |
| final aggregate | `final_result`: `total_score`, `sub_games_won`, `ties`, `winner_group`, `series_tie`, `tokens_total_series` | |

Rules for these values:

- Four of them — the remote peer's two repository URLs, its per-sub-game 40-hex commit, its MCP
  addresses and its identity block — can only be filled from what the remote peer declares in the
  handshake (Section 3). Each side MUST therefore send its own in every sub-game handshake.
- A value the remote peer never declared MUST be left empty. It MUST NOT be inferred, guessed, or
  copied from another sub-game.

**[LOCAL] May differ between the two files:** timezone choice, exact timestamps, per-side token
totals, local audit bookkeeping and any additional local metadata. None of it is compared, and
none of it affects the canonical digest.

---

## 13. Failure & Recovery

| Situation | Behaviour | Replay |
|---|---|---|
| Remote peer silent past the per-turn deadline | sub-game result `timeout` (0/0) | the sub-game stands; do not rewrite it |
| Remote peer unreachable at negotiate or turn | outbound calls retry transient errors for a bounded window; if the peer does not return, that sub-game alone is recorded as `timeout` (0/0) and the series continues. A capture or survival MUST NOT be fabricated | restore reachability for the remaining sub-games; the dropped sub-game stands as `timeout` |
| Remote per-sub-game audit does not arrive in the audit window | that sub-game's audit is recorded as skipped and unverified (`result_agreed = false`); the gameplay result stands | audit promptly; a late audit cannot be re-filed |
| Transient HTTP 5xx | retried for the bounded window | fix the endpoint, then start a fresh series |
| Ordering or equivocation violation | classified as `technical_loss` (0/0) | that sub-game stands as `technical_loss` |
| Failure during the final audit or consensus exchange | consensus may not confirm; `sha_match` may be false | do not replay inside the completed series |
| Fewer than six clean sub-games | no valid complete result | run a new full series if a fresh official attempt is required |

**[MATCH] Completed sub-games are immutable.**

- Inside an existing series this is forbidden: a completed sub-game MUST NOT be modified, replaced
  or selectively replayed, and its artifacts MUST be preserved unchanged.
- A brand-new series is permitted: if consensus could not complete and a fresh official attempt is
  needed, run an entirely new six-sub-game series into a fresh output directory rather than
  patching or partially re-running the previous one.

There is no mechanism to re-exchange consensus against an already-completed result.

---

## 14. Interoperability Failure Modes

| Symptom | Likely cause | Check |
|---|---|---|
| Handshake or turns fail intermittently | unstable public endpoint or tunnel | keep the endpoint up for the whole series and monitor it |
| Remote peer reported unreachable although the local server runs | public endpoint not actually reachable | `curl` the public `/mcp` from outside before starting (Section 8) |
| Identity rejected | empty `members`, or a commit that is not 40 hex characters | Section 3 |
| Captures missed or disputed | divergent capture-claim handling | Section 5 |
| Failed final audit observed by the remote peer | server shut down before the audit drained | keep serving through the consensus exchange (Section 7) |
| `result_agreed` false although both sides played the same sub-game | an audit from another sub-game was consumed | tag audits with `sub_game_number` and audit promptly (Sections 9, 10) |
| Digests equal but consensus does not confirm | malformed consensus envelope: `sender` not a wire role, `records` non-empty, wrong `result_claim`, or a digest that is not 64 lowercase hex | Section 10 step 3 |
| Report files differ | expected local metadata differences | compare the canonical digest, not whole files (Section 11) |
| Authentication errors | one side requires a bearer token | no bearer authentication (Section 7) |
| `game_uid` or consensus digest mismatch | terms differ, or a different `game_id` or canonical object | Appendix A; identical `game_id`; group-keyed rows |

---

## 15. Compatibility Test (non-counted)

Both teams SHOULD run a short non-counted series before the official one.

- The number of sub-games actually played is a launch parameter. It does **not** change the signed
  `num_games`, which stays `6`; the handshake and signature remain the standard ones. A short run
  therefore signs the normal six-game terms and plays fewer sub-games by mutual agreement.
- **[MATCH] Both peers MUST launch with the same number of sub-games.** Each side loops its own
  count independently, so a mismatch leaves the longer side waiting. This is the one hard
  requirement of the short test.
- One sub-game exercises handshake, gameplay, audit and consensus; two sub-games additionally
  exercise both roles.
- Consensus, per-sub-game audit and the final digest exchange all operate correctly with fewer
  than six rows.
- Run it non-counted, with a throwaway `game_id` and a fresh output directory. It is a
  connectivity and schema check, not an official result.

It verifies endpoint reachability, terms agreement, identity exchange, authentication
compatibility, `game_id` and `game_uid` derivation, turn schema, the capture round trip, and the
consensus exchange.

---

## 16. Ready Template

```
READY

Group:                <group_id>
Members:              <non-empty list>
Cop repo:             <url>
Thief repo:           <url>
Cop runtime SHA:      <40-hex>
Thief runtime SHA:    <40-hex>
Public MCP endpoint:  https://<host>/mcp     (live, externally reachable, no bearer)
Starting role:        <cop | thief>          (complement of the other team)
Agreed game_id:       <agreed label>

14 signed terms match Appendix A (values and JSON types):         YES
35-step survival semantics:                                       YES
Capture-claim = Cop post-move cell every turn, conditions A/B/C:   YES
Transport /mcp, no required bearer authentication:                YES
Canonical consensus object + SHA-256 (Section 11):                YES
Final audit + explicit series_consensus digest exchange:          YES
Server stays alive through the final audit; graceful shutdown:    YES
Public endpoint externally reachable (curl-verified):             YES
```

---

## 17. Pre-Match Checklist

**Exchanged between the teams** (values sent at match time, and repeated in every sub-game
handshake per Section 3)

- [ ] non-empty `group_id`, both sides, exact spelling
- [ ] non-empty `members`
- [ ] public Cop and Thief repository URLs
- [ ] real 40-hex runtime commit for the running code
- [ ] `mcp_servers` map, live and externally reachable
- [ ] `game_id` agreed and identical; `game_uid` derives identically
- [ ] complementary starting roles agreed

**Configuration**

- [ ] exact values and JSON types from Appendix A

**Protocol**

- [ ] `capture_claim` = the Cop's post-move cell on every Cop turn; barrier ≠ claim; conditions
      A/B/C (Section 5)
- [ ] turn schema, with `step`, `sender` and `commit` required; commit-reveal with the nonce
      revealed at the audit
- [ ] role alternation; six-sub-game lifecycle; the Thief sends the first turn
- [ ] survival at exactly 35 completed steps

**Network**

- [ ] public `/mcp` externally reachable now, no required bearer
- [ ] handlers enqueue and return immediately
- [ ] graceful shutdown through the final audit

**Consensus**

- [ ] canonical object `{game_id, game_uid, sub_games}`, five keys per row, group-keyed `roles`
      and `score`
- [ ] serialization `sort_keys=True, ensure_ascii=False, separators=(",", ":")` then SHA-256
- [ ] explicit `series_consensus` exchange; agreement requires the received remote digest to equal
      the local one

**Immediately before the counted series**

- [ ] both endpoints verified reachable at that moment, and live URLs re-published if they changed
- [ ] the compatibility test of Section 15 passed, or both teams accept the risk
- [ ] Ready template exchanged
- [ ] fresh output directory on each side

---

## 18. Report Verification Checklist

Run this against the generated file before submitting it. Section 12 defines the required fields;
this list covers delivery and the conditions that are easy to get wrong.

- [ ] The filename is exactly `result_<game_id>.json`, using the agreed `game_id`.
- [ ] The file is valid, machine-readable JSON, submitted as an attachment, never as free text.
- [ ] It is generated after all six sub-games finished, from that run's own data — never from an
      older or partial artifact.
- [ ] Both teams submit their own report, and the reports do not contradict each other on the
      [MATCH] facts.
- [ ] Every field in the Section 12 table is present, and none is empty or a placeholder — except
      values the remote peer never declared, which stay empty rather than being invented.
- [ ] `github_commit` per sub-game is a real 40-hex value for each group.
- [ ] `tokens` per sub-game and `tokens_total_series` reflect actual consumption.
- [ ] The `+2` series tie bonus is applied once to each side, and only on equal cumulative totals.
- [ ] `mutual_agreement` records the local digest, the digest actually received from the remote
      peer, whether they matched, whether every sub-game result was agreed, and whether every
      remote log verified untampered — with `confirmed` true only when all hold.

---

## Appendix A — The 14 Signed Terms (exact)

```json
{
  "board_size": 7,
  "smell_grid_size": 5,
  "decay_per_step": 0.1,
  "emit_intensity": 0.9,
  "min_center_intensity": 0.5,
  "max_steps": 35,
  "barriers_max": 14,
  "setting": "Haifa",
  "hint_max_words": 15,
  "axis_origin_corner": "top-left",
  "axis_start_index": 0,
  "thief_start": [3, 3],
  "cop_start": [0, 0],
  "num_games": 6
}
```

## Appendix B — Cryptographic Derivations

Every digest below is reproducible from this pseudocode. The `|` characters are literal pipe bytes
(`0x7C`), all string inputs are encoded UTF-8, and every SHA-256 output is 64 lowercase hex
characters (`.hexdigest()`).

```python
import hashlib, json, secrets, uuid


def canonical(obj) -> str:
    # the one canonical form used for every hash and signature in this protocol
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fresh_nonce() -> str:
    return secrets.token_hex(16)  # exactly 32 lowercase hex chars


def commit_of(payload: dict, nonce: str) -> str:
    material = canonical(payload) + "|" + nonce  # single str; "|" is a literal pipe
    return hashlib.sha256(material.encode("utf-8")).hexdigest()  # 64 lowercase hex


# terms signature carried in each negotiation:
signature = commit_of(terms, nonce)  # SHA-256 over canonical(terms)+"|"+nonce

# shared ids (both peers compute identically; order-independent):
pair = sorted([group_a, group_b])  # e.g. ["teamA", "teamB"]
game_id = "-vs-".join(pair)  # "teamA-vs-teamB"
seed = canonical(terms) + "|" + "|".join(pair)  # canonical(terms) + "|" + "teamA|teamB"
digest = hashlib.sha256(seed.encode("utf-8")).digest()  # 32 RAW bytes (not hex)
game_uid = str(uuid.UUID(bytes=digest[:16]))  # UUID from the FIRST 16 bytes

# series consensus digest (over the canonical consensus object of Section 11):
consensus_sha = hashlib.sha256(canonical(consensus_obj).encode("utf-8")).hexdigest()
```

Notes: (1) `game_uid` uses the first 16 raw bytes of the SHA-256 digest (`.digest()[:16]`), not the
hex string. (2) Turn-record commits use `commit_of(payload, nonce)` with the same literal `"|"`.
(3) No newline, space or separator other than the literal characters shown is used.

## Appendix C — Canonical Consensus Example (synthetic)

Placeholder values only:

```json
{
  "game_id": "EXAMPLE001",
  "game_uid": "<derived-game-uid>",
  "sub_games": [
    {"sub_game_number": 1, "result": "survival", "roles": {"teamA": "thief",  "teamB": "police"}, "score": {"teamA": 10, "teamB": 5},  "winner_group": "teamA"},
    {"sub_game_number": 2, "result": "capture",  "roles": {"teamA": "police", "teamB": "thief"},  "score": {"teamA": 20, "teamB": 5},  "winner_group": "teamA"},
    {"sub_game_number": 3, "result": "survival", "roles": {"teamA": "thief",  "teamB": "police"}, "score": {"teamA": 10, "teamB": 5},  "winner_group": "teamA"},
    {"sub_game_number": 4, "result": "survival", "roles": {"teamA": "police", "teamB": "thief"},  "score": {"teamA": 5,  "teamB": 10}, "winner_group": "teamB"},
    {"sub_game_number": 5, "result": "capture",  "roles": {"teamA": "thief",  "teamB": "police"}, "score": {"teamA": 5,  "teamB": 20}, "winner_group": "teamB"},
    {"sub_game_number": 6, "result": "survival", "roles": {"teamA": "police", "teamB": "thief"},  "score": {"teamA": 5,  "teamB": 10}, "winner_group": "teamB"}
  ]
}
```

```
sha256 of canonical(object) = <64 lowercase hex, identical on both sides>
```

## Appendix D — Protocol Message Examples

Placeholder values only.

**Negotiation (per sub-game):**

```json
{ "terms": { /* the 14 signed terms */ }, "nonce": "<32-hex>", "signature": "<64-hex>",
  "group_id": "<local_group>", "role": "thief", "sub_game_number": 1,
  "game_uid": "<derived>", "identity": { "group_id": "<local_group>", "git_commit_hash": "<40-hex>",
  "github_commit": "<40-hex>", "members": ["<member-1>", "<member-2>"],
  "repos": { "cop": "https://<host>/<cop-repo>", "thief": "https://<host>/<thief-repo>" },
  "mcp_servers": { "cop": "https://<host>/mcp", "thief": "https://<host>/mcp" } } }
```

**Cop turn** (the claim is always present; a barrier is separate):

```json
{ "step": 4, "sender": "police", "commit": "<64-hex>", "hint": "<= 15 words",
  "smell_grid": {"0,0": 0.9, "0,1": 0.62}, "timestamp": "<iso-8601>",
  "barrier_placed": null, "capture_claim": [2,3], "claim_response": null, "win_claim": null }
```

**Thief reply** carrying a truthful claim answer and a survival claim at the threshold:

```json
{ "step": 35, "sender": "thief", "commit": "<64-hex>", "hint": "<= 15 words",
  "smell_grid": {"3,3": 0.42}, "claim_response": {"claim": [2,3], "caught": false},
  "win_claim": {"type": "survival"} }
```

**Per-sub-game audit** (`submit_audit`; `sub_game_number` optional):

```json
{ "sender": "thief", "records": [ /* every turn record with its revealed nonce */ ],
  "result_claim": "capture", "sub_game_number": 3 }
```

**End-of-series consensus envelope** (`submit_audit`):

```json
{ "sender": "thief", "records": [], "result_claim": "series_consensus", "consensus_sha": "<64-hex>" }
```

## Appendix E — Pheromones & Hints

- **Fixed 5×5 radial kernel**, indexed by `(|Δrow|, |Δcol|)` from the emitter and edge-clipped to
  in-bounds cells:

  ```
  (0,0)=0.90  (0,1)=(1,0)=0.62  (1,1)=0.42  (0,2)=(2,0)=0.20  (1,2)=(2,1)=0.14  (2,2)=0.04
  ```

- **Update per turn:** `τ_next = min(0.9, max(0, (1−ρ)·τ_old + δ))`, with ρ = `decay_per_step` =
  0.1 and cap 0.9.
- **On the wire:** the emitter's scent is sent as `smell_grid = {"r,c": intensity}`, carrying only
  cells above a small epsilon.
- **Hints:** free text, at most `hint_max_words` = 15 words. The `setting` term is the shared
  world or theme. Hint honesty is a per-team choice, not a protocol rule: hints MUST NOT be assumed
  truthful.

What must match: the four scent terms in the signed set (`smell_grid_size`, `decay_per_step`,
`emit_intensity`, `min_center_intensity`) and the `{"r,c": intensity}` wire shape. How a receiver
uses incoming scent is a local choice.
