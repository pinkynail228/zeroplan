"""Convert a black-on-white image into terminal art (braille or half blocks)."""
import sys
from PIL import Image, ImageOps


def load(path, threshold):
    img = Image.open(path).convert("LA")
    bg = Image.new("LA", img.size, (255, 255))
    bg.paste(img, mask=img.split()[1])
    gray = bg.convert("L")
    bbox = ImageOps.invert(gray).point(lambda v: 255 if v > 255 - threshold else 0).getbbox()
    return gray.crop(bbox) if bbox else gray


def braille(gray, cols, threshold):
    w = cols * 2
    h = round(gray.height * w / gray.width / 4) * 4
    px = gray.resize((w, h), Image.LANCZOS).load()
    dots = ((0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
            (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80))
    rows = []
    for y in range(0, h, 4):
        row = ""
        for x in range(0, w, 2):
            bits = sum(b for dx, dy, b in dots if px[x + dx, y + dy] < threshold)
            row += chr(0x2800 + bits) if bits else " "
        rows.append(row.rstrip())
    return rows


def halfblock(gray, cols, threshold):
    h = round(gray.height * cols / gray.width / 2) * 2
    px = gray.resize((cols, h), Image.LANCZOS).load()
    chars = {(0, 0): " ", (1, 0): "▀", (0, 1): "▄", (1, 1): "█"}
    return ["".join(chars[(px[x, y] < threshold, px[x, y + 1] < threshold)]
                    for x in range(cols)).rstrip() for y in range(0, h, 2)]


if __name__ == "__main__":
    path, mode, cols, threshold = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    gray = load(path, threshold)
    print("\n".join((braille if mode == "braille" else halfblock)(gray, cols, threshold)))
