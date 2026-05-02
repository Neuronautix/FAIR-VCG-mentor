"""
Shared vocabulary constants used by both the profiler inference layer
and the VCG wizard / orchestrator.  Import from here; do not redefine.
"""

CONTROL_KEYWORDS = [
    "vehicle", "ctrl", "control", "saline", "placebo",
    "sham", "wt", "wildtype", "veh", "untreated", "naive",
]

IDENTIFIER_PATTERNS = [
    r'.*_id$', r'.*_ID$', r'^id$', r'^ID$', r'.*identifier.*',
    r'.*subject.*id.*', r'.*animal.*id.*', r'.*sample.*id.*',
    r'.*mouse.*id.*', r'.*rat.*id.*', r'.*patient.*id.*',
]
