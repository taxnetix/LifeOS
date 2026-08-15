"""Entry point for `python -m lifeos.extract`.

A package needs this; running -m on a package does not execute __init__.py.
"""

import sys

from . import main

sys.exit(main())
