"""Shared constants for template scoring and paper-template UX flows."""

MAX_ADDITIONAL_TERMS = 20
MAX_MATCH_REASON_TERMS = 4

# Extra-term boosts should be helpful but secondary to core extraction signals.
# 0.06 means ~1-3 matched terms provide a small tie-breaker bonus.
ADDITIONAL_TERM_SCORE_MULTIPLIER = 0.06
ADDITIONAL_TERM_SCORE_CAP = 0.2
