"""The README's block diagram of a running milestone (docs/img/scheme.png): the product's own Scheme renderer
(terminal_planner/tui/scheme.py) in its box mode, which needs about 76 x 58 cells, exported as SVG.

usage: PYTHONPATH=. python3.13 devtools/ui-lab/readme_scheme.py OUT.svg
then:  Chrome --headless --window-size=994,1490 --screenshot, `magick -fuzz 3% -trim`, `-colors 64 PNG8:` (as readme_gif.sh)
"""
import sys

from rich.console import Console

from terminal_planner import milestone
from terminal_planner.tui import scheme

OBSERVATION = {
    "preflight": {"state": "succeeded"}, "select_init": {"state": "succeeded"}, "select": {"state": "succeeded"},
    "select_verify": {"state": "succeeded"}, "worker": {"state": "succeeded", "timer": "2:10"},
    "acceptance_review": {"state": "running", "timer": "0:40"}, "code_review": {"state": "running", "timer": "0:40"},
    "review_loop": {"count": 1},
}

root = milestone.milestone_graph(1, 4)["root"]
drawn = scheme.render(root, OBSERVATION, 80, 58, limits={"review_loop": 4})
console = Console(record=True, width=80, color_system="truecolor", file=open("/dev/null", "w"))
console.print(drawn)
console.print(scheme.legend())
with open(sys.argv[1], "w") as out:
    out.write(console.export_svg(title="zplan · Scheme"))
