"""Cop-repo interop adapter: translates between this repo's own native wire
vocabulary and the Cop repo's actual, independently-built MCP surface
(`https://github.com/Nagham1023/yamanagh-cop`).

Scope: Step-0, scent-map, per-turn commit/reveal/barrier/capture routing,
auto `receive_capture_response`, Final Reveal exchange, and (rules 19/36 /
Ch.5.3.2) mutual Hcommit audit both ways — she returns her audit of us on
`receive_final_reveal`, and we audit her from recorded commits plus her
Final Reveal nonces (`interop/cop_peer_audit.py`).
"""
