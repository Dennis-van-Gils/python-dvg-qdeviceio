@echo off
rem pytest --cov-report term-missing --cov=src --cov-append -vv
pytest --cov-report term-missing --cov=src -vv
rem coverage combine
coverage html
start htmlcov/index.html