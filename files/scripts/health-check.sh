#!/bin/bash
set -e
for port in 8081 8082 8083 8084 8085; do
  if curl -fsS "http://localhost:$port/health" > /dev/null 2>&1; then
    echo "Port $port: OK"
  else
    echo "Port $port: FAIL"
  fi
done
