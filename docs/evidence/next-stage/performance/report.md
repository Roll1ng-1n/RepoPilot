# Checkpoint schema 3 performance and recovery (#34)

Measured on the same WSL ext4 host with 10,000 Git-visible files. See JSON for machine, fixture and implementation hashes. Baseline is the saved pre-optimization artifacts implementation. Each size has five saves of the same immutable history: one cold and four warm. Every rewritten checkpoint, trace append and unique object byte is counted; no extrapolation to all runtime boundaries.

| Results × output | Median save before/after (s) | p95 before/after (s) | Total bytes before/after | Median reduction | Byte reduction |
|---|---:|---:|---:|---:|---:|
| 100 × 102400 | 0.102 / 0.047 | 0.131 / 0.776 | 51393662 / 10568097 | 54.1% | 79.4% |
| 500 × 102400 | 0.267 / 0.100 | 0.285 / 3.744 | 256937658 / 52798881 | 62.5% | 79.5% |
| 1000 × 102400 | 0.435 / 0.156 | 0.591 / 7.423 | 513867661 / 105587378 | 64.1% | 79.5% |
| 100 × 1048576 | 0.438 / 0.115 | 0.480 / 1.024 | 524481650 / 105186189 | 73.8% | 79.9% |
| 500 × 1048576 | 2.841 / 0.400 | 3.498 / 5.427 | 2622377636 / 525889377 | 85.9% | 79.9% |
| 1000 × 1048576 | 4.354 / 0.763 | 5.590 / 10.681 | 5244747637 / 1051768374 | 82.5% | 79.9% |

The longest 1 MiB history exceeds the 30% target on median and actual cumulative bytes. Cold object creation is slower (13.14s in that case), and p95 reflects this first write. Five samples give a noisy tail estimate; this fixture measures repeated durability saves, not a full long model trajectory. Repository scans are unchanged. No CI wall-clock threshold is added. Baseline cold independent stores and the preliminary optimization measurement remain separate original records.

## Format and durability

Disk schema 3 replaces strings of at least 16 Ki characters with null placeholders and a content_objects manifest (state path, SHA256, byte length). Redacted UTF-8 content is stored in objects/<sha256>.utf8. Objects are atomically written and fsynced, then their directory is fsynced; every referenced object is checked before publishing the checkpoint atomically. Immutable string identity is cached with a bounded strong-reference cache; repository state is never cached. Loading hydrates complete history. Schema 1/2 remain readable. Benchmark artifact copies include objects.

In-flight before-execution and after-result durability, approval/pause/terminal saves, repository fingerprints and resume checks remain. The complete run bundle must include objects; copying checkpoint.json alone is insufficient.

## Failure and recovery

Missing, truncated, altered, symlinked or invalid-path objects raise explicit errors. A failed pre-publication object check leaves the previous checkpoint intact. A crash may leave unreferenced objects; they do not cause calls to be replayed. Preserve the full run directory, restore a damaged object only from a matching verified backup, then inspect before resuming. Never fabricate unknown tool results or rerun an uncertain write. See test_checkpoint_storage.py and test_reliability_v2.py for interrupted publication and execution boundaries.

Validation: 300 RepoPilot tests passed including Docker; stage4-tests.txt. Reproduce measurements with measure.py --mode baseline / --mode optimized. The saved checkpoint-baseline.py.txt is the baseline implementation input.

后续 5802016 在读取/缓存写入路径补充对象目录 symlink 检查，定向损坏引用回归 9 passed。性能 JSON 的 implementation_sha256 明确对应测量时源码；未将后续 guard 改写为测量时实现。
