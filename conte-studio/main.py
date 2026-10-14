"""Lanceur de Conte Studio."""

import multiprocessing
import sys

from contestudio.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
