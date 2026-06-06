.PHONY: setup db db-down test lint compare

setup:
	pip install -e ".[dev]"

db:
	docker compose up -d

db-down:
	docker compose down

test:
	pytest -q

lint:
	ruff check .

# 사용법: make compare PDF=data/samples/ir_2023.pdf
compare:
	python -m src.parse.compare $(PDF)
