# Report output format

The default report is human-readable and has one `name: value` row per input row.

The report is also consumed by streaming tools. The `--json` mode is therefore
newline-delimited JSON (NDJSON): emit one JSON object per input row, in input
order, without wrapping the objects in an outer array.
