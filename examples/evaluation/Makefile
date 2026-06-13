# Regenerate the large scalability load-test fixtures.
#
# These files are NOT committed (see .gitignore) because they are big, fully
# deterministic outputs of generate_loadtest.py. Regenerate them on demand:
#
#     make -C examples/evaluation loadtests   # write the 1k + 10k fixtures
#     make -C examples/evaluation smoke       # regenerate + parse-check them
#     make -C examples/evaluation clean       # remove the generated fixtures
#
# `smoke` is the regression guard for the trailing-comma generator bug: it
# regenerates and runs the real parser, so a malformed fixture fails the build.

EX_DIR := ../../vaked/examples
PY     := python3

.PHONY: loadtests smoke clean

loadtests:
	$(PY) generate_loadtest.py --workers 1024  --out $(EX_DIR)/swe-swarm-1k-workers.vaked
	$(PY) generate_loadtest.py --workers 10000 --out $(EX_DIR)/swe-swarm-10k-workers.vaked

smoke: loadtests
	cd ../.. && $(PY) -m vakedc parse vaked/examples/swe-swarm-1k-workers.vaked
	cd ../.. && $(PY) -m vakedc parse vaked/examples/swe-swarm-10k-workers.vaked
	@echo "smoke OK: both load-test fixtures parse"

clean:
	rm -f $(EX_DIR)/swe-swarm-1k-workers.vaked $(EX_DIR)/swe-swarm-10k-workers.vaked
