"""Lanceur de Leçon Studio."""

import multiprocessing
import sys

from leconstudio.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
