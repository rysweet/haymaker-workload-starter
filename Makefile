.PHONY: install test lint deploy clean azure-setup azure-deploy

install:  ## Install all deps from GitHub + the workload in dev mode
	pip install "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git"
	pip install "amplihack @ git+https://github.com/rysweet/amplihack.git"
	pip install "amplihack-memory-lib @ git+https://github.com/rysweet/amplihack-memory-lib.git"
	pip install -e ".[dev]"

test:  ## Run pytest
	pytest -q

lint:  ## Run ruff check + format check
	ruff check src/ tests/
	ruff format --check src/ tests/

deploy:  ## Deploy with haymaker using the example goal
	haymaker deploy my-workload \
		--config goal_file=goals/example-file-organizer.md \
		--yes

clean:  ## Remove .haymaker/ and __pycache__
	rm -rf .haymaker/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

azure-setup:  ## Run scripts/setup-oidc.sh (one-time Azure OIDC setup)
	./scripts/setup-oidc.sh

azure-deploy:  ## Trigger GitHub Actions deploy workflow
	gh workflow run deploy.yml -f environment=dev
