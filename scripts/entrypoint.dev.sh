#!/bin/bash

echo "Collecting static files..."
cd ..
python src/manage.py collectstatic --noinput

echo "Static files collected successfully!"