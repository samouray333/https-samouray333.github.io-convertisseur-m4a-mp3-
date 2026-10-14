"""Lanceur de PodCast Studio."""

import multiprocessing
import sys

from podcaststudio.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
