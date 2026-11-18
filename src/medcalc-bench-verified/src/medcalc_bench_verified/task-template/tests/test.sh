#!/bin/bash
set -eu
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
/usr/local/bin/python -I /tests/grade.py
