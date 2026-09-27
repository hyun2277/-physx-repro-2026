"""Load the isolated adapter only when explicitly enabled by the runner."""

import os

if os.environ.get("PHYSX_TILE_ENABLE") == "1":
    from channel_tiled_spconv import install

    install()
