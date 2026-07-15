#!/usr/bin/env bash
#
# Generate benchmark files for bad-grep.
#
#   2000 files ~4 KB each (~8 MB total)
#
# The mode differences (sync vs async vs thread) come from overlapping per-file
# I/O latency, so MANY small files on a cold cache is the informative case.
#
# Files contain real words so that pattern searching is meaningful. A known
# needle ("BENCHNEEDLE") is sprinkled in at a fixed rate so every file has
# some matches to find.
#
# Usage: ./gen_files.sh [output_dir]   (default: ./files)

set -euo pipefail

OUT="${1:-files}"
NEEDLE="BENCHNEEDLE"

# Pick a word source: the system dictionary if present, else synthesize one.
if [[ -r /usr/share/dict/words ]]; then
    WORDS=/usr/share/dict/words
else
    WORDS="$(mktemp)"
    # Fallback: base64 noise split into short "words".
    head -c 2m /dev/urandom | base64 | fold -w 8 > "$WORDS"
fi

# Build the augmented source block once: the word list with the needle injected
# roughly every 300 lines so that every generated file contains matches.
SOURCE="$(mktemp)"
trap 'rm -f "$SOURCE" "${WORDS_TMP:-}"' EXIT
[[ "$WORDS" == /usr/share/dict/words ]] || WORDS_TMP="$WORDS"
awk -v needle="$NEEDLE" '
    { print }
    NR % 300 == 0 { print needle " line " NR + 1 }
' "$WORDS" > "$SOURCE"

# make_file <path> <target_bytes>
# Streams the augmented source repeatedly and truncates to exactly target_bytes.
make_file() {
    local path="$1" target="$2"
    # head closes the pipe once it has enough bytes; cat then gets SIGPIPE and
    # the loop ends. Precise to the byte (may cut the final line, which is fine).
    # Run with pipefail off so the expected SIGPIPE on cat doesn't abort us.
    ( set +o pipefail
      { while :; do cat "$SOURCE"; done; } 2>/dev/null | head -c "$target" > "$path" )
}

gen_dir() {
    local dir="$1" count="$2" bytes="$3"
    echo "Generating $count files of ~$((bytes / 1024)) KB in $dir/ ..."
    mkdir -p "$dir"
    for ((i = 1; i <= count; i++)); do
        make_file "$dir/file_$(printf '%04d' "$i").txt" "$bytes"
    done
}

gen_dir "$OUT" 2000 $((4 * 1024))          # ~4 KB

echo
echo "Done. Size:"
du -sh "$OUT"
