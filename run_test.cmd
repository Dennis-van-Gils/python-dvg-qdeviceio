@echo off
rem REMEMBER TO HAVE THIS PACKAGE INSTALLED LOCALLY USING: pip install -e .
rem IF YOU WANT TO RUN PYTEST LOCALLY
rem pytest --cov-report term-missing --cov=src --cov-append -vv
pytest --cov-report term-missing --cov=src -vv
rem coverage combine
coverage html
start htmlcov/index.html