.PHONY: help install serve build

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install documentation dependencies
	pip install -r requirements.txt

serve: install ## Serve documentation locally
	mkdocs serve

build: install ## Build documentation with strict mode
	mkdocs build --strict
