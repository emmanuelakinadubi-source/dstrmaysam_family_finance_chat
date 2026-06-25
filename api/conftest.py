import sys
import os

# Make `app.*` importable when pytest runs from the api/ directory
sys.path.insert(0, os.path.dirname(__file__))
