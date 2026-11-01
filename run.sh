#!/bin/bash

set -euo pipefail

. venv/bin/activate
PYTHONPATH=src python -m investment_tracker
