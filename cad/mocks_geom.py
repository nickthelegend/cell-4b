"""Switch footprint, shared by the mock and by the baffle that must clear it.

Lives in its own module because parts.py cannot import mocks.py (mocks.py
imports parts.py), and the baffle's notch has to come from the same numbers as
the switch body or the two will drift.
"""
from shapely.geometry import box

import spec as S

SWITCH_CY = -S.ENV_Y / 2 + S.WALL + S.SWITCH_W / 2 + 0.4
# The BODY sits wholly outside the cartridge channel -- only the lever enters
# it. Putting the body's inner edge at the lever's reach drove 5 mm of switch
# housing straight through the cartridge.
# Which side of the slot the switch body sits on. It moved to -X so the
# optical head's az-305 lug has somewhere to land; the cartridge channel is
# symmetric about x=0, so this is a sign flip and nothing else.
# See FINDINGS.md section 9.
SWITCH_SIDE = -1.0
SWITCH_CX = SWITCH_SIDE * ((S.CART_W + 2 * S.FIT) / 2 + S.FIT + S.SWITCH_L / 2)


def switch_footprint(pad=0.0):
    """XY outline of the switch body, in case coordinates."""
    return box(SWITCH_CX - S.SWITCH_L / 2 - pad, SWITCH_CY - S.SWITCH_W / 2 - pad,
               SWITCH_CX + S.SWITCH_L / 2 + pad, SWITCH_CY + S.SWITCH_W / 2 + pad)
