PYTHON := .venv/bin/python

.PHONY: test test-integration publish help

help:
	@echo "Targets:"
	@echo "  make test                                                          Run the unit test suite"
	@echo "  make test-integration                                              Run integration tests (needs converter running)"
	@echo "  make publish path=FILE title=TITLE [parent_id=ID] [doc_id=ID]      Upload a markdown file"

test:
	@$(PYTHON) -m pytest

test-integration:
	@$(PYTHON) -m pytest -m integration

publish:
ifndef path
	$(error path is required — usage: make publish path=<file> title=<title> [parent_id=<id>] [doc_id=<id>])
endif
ifndef title
	$(error title is required — usage: make publish path=<file> title=<title> [parent_id=<id>] [doc_id=<id>])
endif
	@$(PYTHON) main.py "$(path)" "$(title)" "$(parent_id)" "$(doc_id)"
