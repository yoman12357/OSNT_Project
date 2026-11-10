#!/usr/bin/env python3
"""Arrange rendered PDF pages into labelled sheets for visual verification."""
from pathlib import Path
from PIL import Image, ImageDraw

directory = Path(__file__).resolve().parent / "pdf-preview"
pages = sorted(directory.glob("page-*.png"))
for start in range(0, len(pages), 4):
    sheet = Image.new("RGB", (1560, 2240), "#cbd5dc")
    draw = ImageDraw.Draw(sheet)
    for offset, page in enumerate(pages[start:start+4]):
        picture = Image.open(page).convert("RGB")
        picture.thumbnail((760, 1075))
        x = 10 + (offset % 2) * 780
        y = 30 + (offset // 2) * 1120
        sheet.paste(picture, (x, y))
        draw.text((x + 6, y - 20), f"PDF page {start+offset+1}", fill="black")
    sheet.save(directory / f"contact-{start//4+1}.png")
print(f"Created {(len(pages)+3)//4} contact sheets from {len(pages)} rendered pages")
