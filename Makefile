.PHONY: setup validate audit test brief clean

PY ?= python3

setup:
	$(PY) -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -e ".[dev]"

validate:
	$(PY) -m aadesk.cli validate

audit: validate
	$(PY) -m aadesk.cli audit data/examples/logframe_example.csv --outdir output \
	  --title "Somalia–Yemen multi-country results framework"

test:
	$(PY) -m pytest

brief: audit
	@echo "open output/brief.html"

clean:
	rm -rf output/scorecard.csv output/assessments.json output/brief.html output/powerbi
