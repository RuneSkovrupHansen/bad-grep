# bad-grep

A bad Python implementation of grep to test asynchronous programming patterns and their performance.

`bad-grep` searches one or more files (or stdin) for lines matching a regex pattern, with options for case-insensitive matching (`-i`), match counts (`-c`), and recursive directory search (`-r`). It offers three interchangeable search backends—synchronous, thread-based, and asyncio-based (`--mode`)—and exits with code 0 if any matches were found, 1 otherwise.


## Benchmarking

Synchronize uv to generate `.venv/`:

```python
uv sync
```

Generate the test files (2000 small files in `files/`):

```sh
./gen_files.sh
```

The differences between the search modes come from overlapping per-file I/O
latency, which is only visible on a **cold page cache**. Always drop the cache before each timed run, otherwise you are just measuring warm-cache overhead and the three modes look identical.

On macOS, use `hyperfine`'s `--prepare` to clear the cache before every run.
Because `purge` needs root, cache your sudo credentials first (otherwise the
hidden password prompt inside `--prepare` makes the run appear to hang):

```sh
sudo -v
hyperfine --warmup 1 --runs 10 --prepare 'sync && sudo purge' \
  '.venv/bin/python main.py -r -m sync  BENCHNEEDLE files' \
  '.venv/bin/python main.py -r -m async BENCHNEEDLE files' \
  '.venv/bin/python main.py -r -m thread BENCHNEEDLE files'
```

Many tiny files give the clearest signal, since per-file I/O latency dominates there and is what the async/thread modes can overlap.


## Results

The results show that the asynchronous implementation is the **slowest**. How could this be, `asyncio` is supposed to go fast, right?

There's a few reasons why the asynchronous implementation comes in dead last:

1. A lot of the work is disk + CPU bound, so we're not actually waiting a whole lot.

2. Regular file reads aren't truly asynchronous, they block the calling thread until data is delivered. `epoll` literally reports regular files as always readable, so there's no idle gap for the event loop to fill.

3. The current implementation awaits each line read, `async for line in stream`, which causes a signficiant amount of overhead. Each one round-trips through the event loop scheduler.

The asynchronous approach would be fantastic in a scenario where the wating **is** readiness-based.
