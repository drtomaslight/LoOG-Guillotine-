#!/bin/bash
gunicorn app:app --timeout 120 --workers 2 --worker-class gthread --threads 4
