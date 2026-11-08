"""Jade Rain Matrix: a calm digital-rain wallpaper renderer for Omarchy."""

import os

# One BLAS thread per process. The renderer forks a pool; extra threads
# oversubscribe and can deadlock across fork.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

__version__ = "0.2.0"
