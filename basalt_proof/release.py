"""Single source of truth for active Basalt release identity.

Historical documentation may retain older release names. Runtime surfaces must import
this module rather than embedding version or phase strings.
"""

VERSION = "3.0.0rc4"
DISPLAY_VERSION = "3.0.0 RC4"
PRODUCT_NAME = "Basalt v3 Production Candidate"
WORKSPACE_NAME = "Basalt v3 Production Workspace"
RELEASE_CHANNEL = "RELEASE CANDIDATE"
PHASE = 7
PHASE_NAME = "Production Basalt v1"
API_SERVER_VERSION = "BasaltCommandCenter/3.0-rc4"


def release_metadata() -> dict[str, object]:
    return {
        "version": VERSION,
        "display_version": DISPLAY_VERSION,
        "product": PRODUCT_NAME,
        "channel": RELEASE_CHANNEL,
        "phase": PHASE,
        "phase_name": PHASE_NAME,
    }
