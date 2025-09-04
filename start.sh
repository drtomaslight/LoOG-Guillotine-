#!/bin/bash
gunicorn app:app --timeout 300 --workers 1 --threads 4 --log-level debug
