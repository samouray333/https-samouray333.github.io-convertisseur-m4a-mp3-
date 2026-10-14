"""Lanceur de Polyglotte Studio."""

import multiprocessing
import sys

from polyglottestudio.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
