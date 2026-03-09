PYTHON ?= /storage/share/python/environments/Anaconda3/envs/cogpy/bin/python
PYTEST_PYTHON ?= /storage/share/python/environments/Anaconda3/envs/labpy/bin/python
PUBLISH ?= /storage2/arash/infra/bin/publish_pypi.sh

.PHONY: help urls dev test test-all docs docs-serve build check clean publish publish-test

help:
	@printf '%s\n' \
		'make dev         # install editable package with dev extras' \
		'make urls        # print repository and GitHub Pages URLs' \
		'make test        # run focused test suite' \
		'make test-all    # run all tests' \
		'make docs        # build MkDocs site strictly' \
		'make docs-serve  # serve MkDocs locally' \
		'make build       # build wheel and sdist' \
		'make check       # run twine check on dist artifacts' \
		'make clean       # remove local build artifacts' \
		'make publish     # publish to PyPI via personal helper' \
		'make publish-test # publish to TestPyPI via personal helper'

urls:
	@printf '%s\n' \
		'GitHub: https://github.com/arashshahidi1997/biblio' \
		'Pages:  https://arashshahidi1997.github.io/biblio/'

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	PYTHONPATH=src $(PYTEST_PYTHON) -m pytest tests/test_biblio.py tests/test_biblio_openalex.py tests/test_biblio_site.py -q

test-all:
	PYTHONPATH=src $(PYTEST_PYTHON) -m pytest tests -q

docs:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve

build:
	$(PYTHON) -m build

check:
	$(PYTHON) -m twine check dist/*

clean:
	rm -rf build dist site .pytest_cache .mypy_cache src/*.egg-info src/biblio_tools.egg-info

publish:
	$(PUBLISH) .

publish-test:
	$(PUBLISH) --test .
