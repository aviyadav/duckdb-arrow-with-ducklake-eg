PYTHON ?= uv run python
DATE ?= 2026-09-15

.PHONY: install generate compact stats-small stats-compact bench-small bench-compact demo clean

install:
	uv pip install -r requirements.txt

generate:
	$(PYTHON) scripts/generate_synthetic_vpc_logs.py \
		--date $(DATE) \
		--out-dir data/raw \
		--clean \
		--file-count 1440 \
		--total-rows 1385692 \
		--total-gb 7.36 \
		--schema slim \
		--compression zstd

compact:
	$(PYTHON) scripts/compact_daily.py \
		--date $(DATE) \
		--input-dir data/raw \
		--output-dir data/compacted

stats-small:
	$(PYTHON) scripts/file_stats.py \
		--glob 'data/raw/*_vpcflowlogs_*.parquet'

stats-compact:
	$(PYTHON) scripts/file_stats.py \
		--glob 'data/compacted/daily-$(DATE).parquet'

bench-small:
	$(PYTHON) scripts/benchmark_query.py \
		'data/raw/*_vpcflowlogs_*.parquet' \
		--runs 3

bench-compact:
	$(PYTHON) scripts/benchmark_query.py \
		'data/compacted/daily-$(DATE).parquet' \
		--runs 3

demo: generate stats-small compact stats-compact bench-small bench-compact

clean:
	rm -rf data/raw/*.parquet data/compacted/*.parquet
