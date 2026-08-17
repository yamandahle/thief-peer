"""Cross-team standardized interop protocol adapter ("std_v1"): a third
wire vocabulary alongside "native" and "cop_v1", built against the "P2P
Cop-Thief Match Interoperability Specification" a course-wide standard
proposed so any two independently-built implementations can play a real
series against each other (rule 31: several distinct opponents, not just
one already-coordinated pairing).

Distinct from "cop_v1" (interop/cop_wire.py etc.) in real, incompatible
ways -- different tool names (negotiate/receive_turn/submit_audit/
receive_control vs. her receive_commit/receive_reveal/...), a different
flat 14-key signed-terms shape, a different commit_of formula (nonce
concatenated after a literal "|", never embedded in the hashed JSON), and
an explicit SHA-256 series-consensus digest exchange neither existing
protocol has. Never assume the two interop packages share any wire-level
behavior just because both talk to a "Cop"-role peer.
"""
