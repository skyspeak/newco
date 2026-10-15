.PHONY: map poc lines bridge test validate clean

PYTHON ?= python3

map:
	$(PYTHON) pipeline/run.py --fail-on-scrub

bridge:
	$(PYTHON) pipeline/bridge.py

poc:
	$(PYTHON) pipeline/poc_unbundle.py

lines:
	$(PYTHON) pipeline/poc_unbundle.py

test:
	$(PYTHON) -m unittest discover -s tests -v

validate:
	$(PYTHON) pipeline/validate.py

clean:
	rm -f out/normalized.json out/map.json out/orgmap.html \
	      out/scrub_report.json out/validate_report.json out/similarity.npy \
	      out/poc_unbundle.json out/poc_unbundle.html \
	      out/poc_bridge.json out/poc_bridge.html \
	      out/lines.json
