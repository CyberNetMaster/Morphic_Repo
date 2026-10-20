"""Morphic: material-aware 2D topology optimization for printed parts."""

import os

# S9b: MKL (used by PyPardiso) runs Intel OpenMP threads that by default spin-wait for 200 ms
# after every parallel call. In the optimizer that spinning competes with the Python thread
# (filter and projection calls between solves) and made those calls about 4x slower. A block
# time of 0 lets idle threads sleep at once. It changes no arithmetic. It must be set before
# MKL loads, which is why it lives here. A value set by the user in the environment wins.
os.environ.setdefault("KMP_BLOCKTIME", "0")

__version__ = "0.1.0"
