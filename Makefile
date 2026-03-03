venv:
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1

install:
	pip install -r requirements.txt

freeze:
	pip freeze > requirements.txt
