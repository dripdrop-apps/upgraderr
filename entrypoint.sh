#!/bin/bash

set -euo pipefail

alembic upgrade head

uv run -m upgraderr run
