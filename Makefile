PYTHON ?= /storage/share/python/environments/Anaconda3/envs/cogpy/bin/python
PYTEST_PYTHON ?= /storage/share/python/environments/Anaconda3/envs/labpy/bin/python
PUBLISH ?= /storage2/arash/infra/bin/publish_pypi.sh
DATALAD ?= /storage/share/python/environments/Anaconda3/envs/cogpy/bin/datalad
MSG ?= Update biblio
NODE ?= /home/arash/.nvm/versions/node/v24.14.0/bin/node

RUNTIME_PATH := $(patsubst %/,%,$(dir $(DATALAD))):$(patsubst %/,%,$(dir $(PYTHON))):$(patsubst %/,%,$(dir $(PYTEST_PYTHON))):$(patsubst %/,%,$(dir $(PUBLISH)))
export PATH := $(RUNTIME_PATH):$(PATH)

.PHONY: help urls dev test test-all docs docs-serve ui-serve build-frontend build check clean save push publish publish-test

help:
	@printf '%s\n' \
		'make dev              # install editable package with dev extras' \
		'make urls             # print repository and GitHub Pages URLs' \
		'make test             # run focused test suite' \
		'make test-all         # run all tests' \
		'make docs             # build MkDocs site strictly' \
		'make docs-serve       # serve MkDocs locally' \
		'make ui-serve         # serve the local FastAPI bibliography UI' \
		'make build-frontend   # build the React UI into src/biblio/static/' \
		'make build            # build wheel and sdist (run build-frontend first)' \
		'make check            # run twine check on dist artifacts' \
		'make clean            # remove local build artifacts' \
		'make save MSG="..."   # datalad save with a custom message' \
		'make push             # datalad push --to github' \
		'make publish          # publish to PyPI via personal helper' \
		'make publish-test     # publish to TestPyPI via personal helper'

urls:
	@printf '%s\n' \
		'GitHub: https://github.com/arashshahidi1997/biblio' \
		'Pages:  https://arashshahidi1997.github.io/biblio/' \
		'PyPI:   https://pypi.org/project/biblio-tools/'

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	PYTHONPATH=src $(PYTEST_PYTHON) -m pytest tests/test_biblio.py tests/test_biblio_openalex.py tests/test_biblio_site.py tests/test_smart_collections.py tests/test_concepts_compare_reading.py -q

test-all:
	PYTHONPATH=src $(PYTEST_PYTHON) -m pytest tests -q

docs:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve

ui-serve:
	PYTHONPATH=src $(PYTHON) -m biblio.cli ui serve

build-frontend:
	cd frontend && $(NODE) node_modules/.bin/vite build

build:
	$(PYTHON) -m build

check:
	$(PYTHON) -m twine check dist/*

clean:
	rm -rf build dist site .pytest_cache .mypy_cache src/*.egg-info src/biblio_tools.egg-info

save:
	$(DATALAD) save -m "$(MSG)"

push:
	$(DATALAD) push --to github

publish:
	$(PUBLISH) .

publish-test:
	$(PUBLISH) --test .

-include .projio/projio.mk
