# Expert Agent MCP Server Makefile

# Variables
PYTHON := python3
PIP := pip3
TEST_FLAGS := -v
COVERAGE_FLAGS := --cov=src --cov-report=term-missing

# Default target
.PHONY: help
help:
	@echo "Expert Agent MCP Server - Development Tasks"
	@echo ""
	@echo "Usage:"
	@echo "  make install           Install dependencies"
	@echo "  make dev               Install development dependencies"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests"
	@echo "  make test-integration  Run integration tests"
	@echo "  make test-functional   Run functional tests"
	@echo "  make coverage          Run tests with coverage"
	@echo "  make lint              Run code linting"
	@echo "  make format            Format code with black"
	@echo "  make typecheck         Run type checking with mypy"
	@echo "  make docker-build      Build Docker images (using docker-compose)"
	@echo "  make docker-build-sh   Build Docker images (using scripts/docker-build.sh)"
	@echo "  make docker-up         Start services with docker-compose"
	@echo "  make docker-down       Stop services with docker-compose"
	@echo "  make clean             Clean build artifacts"

# Install dependencies
.PHONY: install
install:
	$(PIP) install -r requirements.txt

# Install development dependencies
.PHONY: dev
dev:
	$(PIP) install -r requirements.txt
	$(PIP) install black flake8 mypy pytest

# Run all tests
.PHONY: test
test:
	$(PYTHON) -m pytest $(TEST_FLAGS)

# Run unit tests
.PHONY: test-unit
test-unit:
	$(PYTHON) -m pytest $(TEST_FLAGS) -m unit

# Run integration tests
.PHONY: test-integration
test-integration:
	$(PYTHON) -m pytest $(TEST_FLAGS) -m integration

# Run functional tests
.PHONY: test-functional
test-functional:
	$(PYTHON) -m pytest $(TEST_FLAGS) -m functional

# Run tests with coverage
.PHONY: coverage
coverage:
	$(PYTHON) -m pytest $(TEST_FLAGS) $(COVERAGE_FLAGS)

# Run code linting
.PHONY: lint
lint:
	flake8 src tests

# Format code with black
.PHONY: format
format:
	black src tests

# Run type checking with mypy
.PHONY: typecheck
typecheck:
	mypy src

# Build Docker images (using docker-compose)
.PHONY: docker-build
docker-build:
	docker-compose build

# Build Docker images (using scripts/docker-build.sh)
.PHONY: docker-build-sh
docker-build-sh:
	./scripts/docker-build.sh

# Start services with docker-compose
.PHONY: docker-up
docker-up:
	docker-compose up -d

# Stop services with docker-compose
.PHONY: docker-down
docker-down:
	docker-compose down

# Clean build artifacts
.PHONY: clean
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .mypy_cache/
	rm -rf .pytest_cache/
