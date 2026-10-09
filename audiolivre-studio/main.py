"""Lanceur d'AudioLivre Studio."""

import multiprocessing
import sys

from audiolivre.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
