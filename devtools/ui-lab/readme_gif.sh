#!/bin/sh
# README GIF: the SVG frames from readme_gif.py -> PNG (headless Chrome, the same renderer as GitHub's browser) -> GIF.
# Usage: devtools/ui-lab/readme_gif.sh FRAMES_DIR OUT.gif [WIDTH]
set -eu
dir=$(cd "$1" && pwd); out=$2; width=${3:-960}
chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
list="$dir/frames.txt"; : > "$list"
python3 -c 'import json,sys; [print(n, s) for n, s in json.load(open(sys.argv[1]))]' "$dir/timeline.json" |
while read -r name seconds; do
  png="$dir/${name%.svg}.png"
  "$chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --window-size=1482,1026 \
    --screenshot="$png" "file://$dir/$name" >/dev/null 2>&1
  magick "$png" -fuzz 3% -trim +repage "$png"  # the white page around the terminal window
  printf "file '%s'\nduration %s\n" "$png" "$seconds" >> "$list"
done
last=$(tail -2 "$list" | head -1); echo "$last" >> "$list"  # concat honours the last duration only if the file repeats
ffmpeg -loglevel error -y -f concat -safe 0 -i "$list" \
  -vf "scale=$width:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff:max_colors=96[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" \
  -loop 0 "$out"
ls -l "$out"
