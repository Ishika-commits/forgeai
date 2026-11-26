#!/usr/bin/env bash
# Runs both demos unattended and writes everything to runs/.
set -e
MODEL="${FORGE_MODEL:-qwen2.5:3b}"
python demos/make_demo_docs.py
python forge.py --brief demos/crew_rest/brief.txt  --docs demos/crew_rest/docs  --out runs/crew_rest  --auto --model "$MODEL" --tournament
python forge.py --brief demos/port_costs/brief.txt --docs demos/port_costs/docs --out runs/port_costs --auto --model "$MODEL" --tournament
