# The same drawing, two ways

**By hand (Python).** You choose every number:

```python
from penarm import Plotter

with Plotter() as p:
    p.draw_polyline([[40, 10], [60, 50], [80, 10], [50, 30], [70, 30]])   # a crooked "A"
    p.draw_shape("star", cx=140, cy=32, size=40, sides=7)
    p.draw_arc(cx=40, cy=32, radius=15, start_deg=0, end_deg=180)
```

**By asking the LLM** (the MCP server is connected, see the README):

> Draw a small house with a sun next to it, as one continuous line. Preview first.

The LLM calls `canvas_info`, designs the lines, previews with `dry_run=true`, fixes anything that falls outside the canvas and draws. It uses the very same `Plotter` methods you called above. The creative part (what to draw and how to turn it into coordinates) is what you stopped doing.
