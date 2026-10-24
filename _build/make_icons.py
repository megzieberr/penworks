# Placeholder PenWorks icons (she picks the real one in U7): a graphite square, a white page, an ink-blue ribbon.
from PIL import Image, ImageDraw
import pathlib

OUT = pathlib.Path(r"C:\Users\megzi\Desktop\Claude Code Projects\penworks\icons")
OUT.mkdir(exist_ok=True)

def icon(size, maskable=False):
    s = 4  # draw big, then shrink for smooth edges
    S = size * s
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if maskable:
        d.rectangle([0, 0, S, S], fill="#262A30")
        inset = 0.26
    else:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill="#262A30")
        inset = 0.2
    w = S * (1 - 2 * inset) * 0.78
    h = w * 1.414
    x0 = (S - w) / 2
    y0 = (S - h) / 2
    d.rectangle([x0, y0, x0 + w, y0 + h], fill="#FFFFFF")
    for i in range(1, 6):  # faint lines on the page
        y = y0 + h * (0.22 + i * 0.12)
        d.line([x0 + w * 0.14, y, x0 + w * 0.86, y], fill="#D3D7DE", width=max(2, int(S * 0.008)))
    rw = w * 0.16
    rx = x0 + w * 0.68
    rh = h * 0.30
    d.polygon([(rx, y0), (rx + rw, y0), (rx + rw, y0 + rh), (rx + rw / 2, y0 + rh * 0.8), (rx, y0 + rh)], fill="#2F4BB8")
    return im.resize((size, size), Image.LANCZOS)

icon(192).save(OUT / "icon-192.png")
icon(512).save(OUT / "icon-512.png")
icon(512, True).save(OUT / "icon-512-maskable.png")
print("icons written")
