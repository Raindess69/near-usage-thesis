PY ?= python3

.PHONY: all fetch fetch-http build verify test clean-cache

all: fetch build          ## refetch every raw input, then rebuild everything

fetch:                    ## public APIs + archival RPC -> data/raw/ (RPC is rate limited: 10-30 min)
	$(PY) -m nut fetch

fetch-http:               ## refresh only the HTTP sources, keep the RPC snapshot (about 10 seconds)
	$(PY) -m nut fetch --skip-rpc

build:                    ## offline: data/raw/ -> data/processed/, docs/ (dashboard + charts), THESIS.md
	$(PY) -m nut build

verify:                   ## rebuild in a temp dir and compare with committed outputs
	$(PY) -m nut verify

test:                     ## offline unit tests
	$(PY) -m unittest discover -s tests -v

clean-cache:
	rm -rf .cache
