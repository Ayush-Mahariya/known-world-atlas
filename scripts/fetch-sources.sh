#!/usr/bin/env bash
# Download the large source files that are not committed to the repo.
#
# The shapefiles are small and vendored; these two are not. Both are optional in
# the sense that the pipeline degrades gracefully — but without the AWOIAF dump
# you lose the deepest lore source (215 of 223 articles).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UA="KnownWorldAtlas/0.1 (personal fan mapping project)"

fetch() {
  local url="$1" dest="$2" label="$3"
  if [[ -f "$dest" ]]; then
    echo "  have $label"
    return
  fi
  echo "  fetching $label..."
  mkdir -p "$(dirname "$dest")"
  curl -sSL --fail -A "$UA" -o "$dest" "$url"
  echo "    $(du -h "$dest" | cut -f1)"
}

echo "sources:"

# A Wiki of Ice and Fire, community XML dump (CC BY-SA). The live site is behind
# Cloudflare bot protection; this archived dump is the sanctioned way in.
fetch "https://archive.org/download/wiki-awoiafwesterosorg/awoiafwesterosorg-20150709-history.xml.7z" \
      "$ROOT/data/raw/awoiaf-dump.7z" "AWOIAF wiki dump (14 MB)"

# Reference rasters — for eyeballing the vector data, not rendered by the app.
fetch "https://atlasoficeandfireblog.wordpress.com/wp-content/uploads/2019/12/asoiaf-known-world-new-mountains.jpg" \
      "$ROOT/data/raw/basemaps/asoiaf-known-world-atlas-10000px.jpg" \
      "Atlas of Ice and Fire world map (8 MB)"
fetch "https://commons.wikimedia.org/wiki/Special:FilePath/Westeros_Map.png" \
      "$ROOT/data/raw/basemaps/westeros-commons.png" "Wikimedia Westeros map (3 MB)"

echo
echo "the shapefiles are vendored in data/raw/game_of_thrones_shapes/"
echo "if they are missing, re-fetch with:"
echo "  curl -sSL -o /tmp/got.zip https://cdn.patricktriest.com/shapefiles/game_of_thrones_shapes.zip"
echo "  unzip -o /tmp/got.zip -x '__MACOSX/*' -d $ROOT/data/raw/"
