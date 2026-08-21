.PHONY: map test validate clean

PYTHON ?= python3

map:
	$(PYTHON) pipeline/run.py --fail-on-scrub

test:
	$(PYTHON) -m unittest discover -s tests -v

validate:
	$(PYTHON) pipeline/validate.py

clean:
	rm -f out/normalized.json out/map.json out/orgmap.html \
	      out/scrub_report.json out/validate_report.json out/similarity.npy
