#!/bin/bash
gunicorn app:app --config gunicorn_config.py
