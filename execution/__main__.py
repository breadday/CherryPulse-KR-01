"""Run only the isolated virtual demonstration: python -m execution."""

import sys

from execution.demo import run

_ = sys.stdout.write(run().model_dump_json() + "\n")
