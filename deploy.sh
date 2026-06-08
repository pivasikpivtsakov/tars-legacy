#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.yml"

git pull

docker compose -f "$COMPOSE_FILE" down
docker compose -f "$COMPOSE_FILE" up -d
