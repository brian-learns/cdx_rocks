REQUIRED_EXECUTABLES = uv rm find

.PHONY: help check test clean testpackages checkdeps loaddata

help:
	@echo ""
	@echo "  make loaddata   Load api data from hugging face"
	@echo "  make check      Run ultra-fast static testing pipeline (ruff, bandit, vulture, etc.)"
	@echo "  make test       Run static checks followed immediately by pytest"
	@echo "  make clean      Wipe out test tool cache tracking footprints"
	@echo "  make init       Initialize new project with uv and test setup"

loaddata: rocksdb_index all_warc_paths.txt.zst

rocksdb_index:
	uvx hf sync hf://buckets/brian-learns/cc-news-cdx-server-storage rocksdb_index

all_warc_paths.txt.zst:
	uvx hf download hf://datasets/brian-learns/cdx-cc-news/all_warc_paths.txt.zst --local-dir .

check:
	@echo "\n— [An extremely fast Python linter and code formatter](https://docs.astral.sh/ruff/)"
	uv run ruff check app/ src/ --fix
	uv run ruff format app/ src/ --check

	@echo "\n— [AST based security scanner](https://bandit.readthedocs.io/en/latest/)"
	uv run bandit -c pyproject.toml -r app/ src/

	@echo "\n— [Find dead Python code](https://github.com/jendrikseipp/vulture)"
	uv run vulture app/ src/ --min-confidence 80

	@echo "\n— [A tool for refurbishing and modernizing Python codebases](https://github.com/dosisod/refurb)"
	uv run refurb app/ src/

	@echo "\n— [An extremely fast Python type checker and language server]( https://docs.astral.sh/ty/)"
	#uv run ty check app/ src/

	@echo "\n— [Interrogate a codebase for docstring coverage](https://interrogate.readthedocs.io/en/latest/)"
	#uv run interrogate app/ src/

test: check
	uv run pytest -v --durations=5

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .vulture_cache .uv
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

init: checkdeps pyproject.toml testpackages

checkdeps:
	@$(foreach exec,$(REQUIRED_EXECUTABLES),\
		command -v $(exec) >/dev/null 2>&1 || { echo "Error: $(exec) is required."; exit 1; };)
	@echo "All required commands are available."

testpackages:
	uv add --dev ruff bandit vulture refurb ty pytest #interrogate

export GIT_CEILING_DIRECTORIES	# can influence `uv init` behaviour
pyproject.toml:
	uv init --package .
