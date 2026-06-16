#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.yml"
NETWORK="payment-bots-network"

git pull

# The compose stack joins this network as external, so it must exist beforehand.
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create --driver bridge "$NETWORK"

docker compose -f "$COMPOSE_FILE" down
docker compose -f "$COMPOSE_FILE" up -d --build
