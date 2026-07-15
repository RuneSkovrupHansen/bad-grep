import argparse
import asyncio
from dataclasses import dataclass
from enum import IntEnum
import os
import re
import sys

from aiofile import async_open


class ExitCode(IntEnum):
    """The exit codes."""

    MATCH = 0
    NO_MATCH = 1


@dataclass
class SearchResult:
    """The outcome of searching a single file."""

    path: str
    matches: list[str]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="bad-grep",
        description="A bad Python implementation of grep.",
    )
    parser.add_argument(
        "pattern",
        help="the pattern to search for",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="one or more files or directories to search (defaults to stdin)",
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="ignore case distinctions in the pattern",
    )
    parser.add_argument(
        "-c",
        "--count",
        action="store_true",
        help="print only a count of matching lines per file",
    )
    parser.add_argument(
        "-r",
        "-R",
        "--recursive",
        action="store_true",
        help="recursively search directories",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=("sync", "async", "thread"),
        default="sync",
        help="the search implementation to use (default: sync)",
    )
    return parser


def iter_files(paths, recursive):
    """Yield file paths from the given list of files/directories."""
    for path in paths:
        if os.path.isdir(path) and recursive:
            for root, _, names in os.walk(path):
                for name in sorted(names):
                    yield os.path.join(root, name)
        else:
            yield path

# Synchronous

def search_stream(stream, regex, name, show_name):
    """Search a single open text stream; return the formatted matching lines."""
    matches = []
    for line in stream:
        line = line.rstrip("\n")
        if regex.search(line):
            prefix = f"{name}:" if show_name else ""
            matches.append(f"{prefix}{line}")
    return matches


def search_file(path, regex, show_name):
    """Search a single file; return a SearchResult."""
    with open(path, "r", encoding="utf-8") as handle:
        matches = search_stream(handle, regex, path, show_name)
        return SearchResult(path=path, matches=matches)


def synchronous_search(files, regex, show_name):
    """Search each file one at a time, in order."""
    return [search_file(path, regex, show_name) for path in files]

# Threaded

async def _threaded_search(files, regex, show_name):
    # search_file does blocking file I/O, so we offload each call to a worker
    # thread with to_thread. create_task can't help here: it only schedules
    # coroutines and a blocking call would still stall the event loop.
    tasks = [
        asyncio.to_thread(search_file, path, regex, show_name) for path in files
    ]
    return await asyncio.gather(*tasks)


def threaded_search(files, regex, show_name):
    """Search all files concurrently, preserving input order in the results."""
    return asyncio.run(_threaded_search(files, regex, show_name))

# Asynchronous

async def async_search_stream(stream, regex, name, show_name):
    """Search a single open text stream; return the formatted matching lines."""
    matches = []
    async for line in stream:
        line = line.rstrip("\n")
        if regex.search(line):
            prefix = f"{name}:" if show_name else ""
            matches.append(f"{prefix}{line}")
    return matches

async def async_search_file(path, regex, show_name):
    """Search a single file; return a SearchResult."""
    async with async_open(path, "r", encoding="utf-8") as handle:
        matches = await async_search_stream(handle, regex, path, show_name)
        return SearchResult(path=path, matches=matches)


async def _asynchronous_search(files, regex, show_name):
    tasks = [
        asyncio.create_task(async_search_file(path, regex, show_name)) for path in files
    ]
    return await asyncio.gather(*tasks)


def asynchronous_search(files, regex, show_name):
    return asyncio.run(_asynchronous_search(files, regex, show_name))


def main() -> ExitCode:
    args = build_parser().parse_args()

    flags = re.IGNORECASE if args.ignore_case else 0
    regex = re.compile(args.pattern, flags)

    # Handle stdin default
    if not args.files:
        matches = search_stream(sys.stdin, regex, "(standard input)", False)
        if args.count:
            print(len(matches))
        else:
            for line in matches:
                print(line)
        return ExitCode.MATCH if matches else ExitCode.NO_MATCH

    files = list(iter_files(args.files, args.recursive))

    show_name = len(files) > 1 or args.recursive
    exit_code = ExitCode.NO_MATCH

    if args.mode == "async":
        results = asynchronous_search(files, regex, show_name)
    elif args.mode == "thread":
        results = threaded_search(files, regex, show_name)
    else:
        results = synchronous_search(files, regex, show_name)

    for result in results:
        if args.count:
            if show_name:
                print(f"{result.path}:{len(result.matches)}")
            else:
                print(len(result.matches))
        else:
            for line in result.matches:
                print(line)
        if result.matches:
            exit_code = ExitCode.MATCH

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
