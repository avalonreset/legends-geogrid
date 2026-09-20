"""Regenerate the synthetic non-square georeferenced fixture; no network.

The upper 1280x640 pixels are an EPSG:4326 coordinate diagram; the bottom
64 pixels are non-geographic credits, reserved by credit_strip_px in config.
This image contains no real map-provider material.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import reportlab


def generate(path):
    image = Image.new('RGB', (1280, 704), '#102434')
    draw = ImageDraw.Draw(image)
    font_path = Path(reportlab.__file__).parent/'fonts/Vera.ttf'
    font = ImageFont.truetype(str(font_path), 26)
    credit_font = ImageFont.truetype(str(font_path), 28)
    west, south, east, north = -101.28, 40.76, -100.25, 41.37
    for i in range(1,4):
        x,y = 1280*i//4,640*i//4
        draw.line((x,0,x,639), fill='#375061', width=3)
        draw.line((0,y,1279,y), fill='#375061', width=3)
        draw.text((x+10,12), f'{west+(east-west)*i/4:.4f}', font=font, fill='#A9BDCA')
        draw.text((12,y+8), f'{north-(north-south)*i/4:.4f}', font=font, fill='#A9BDCA')
    draw.text((28,585), 'SYNTHETIC COORDINATE DIAGRAM / NO STREETS', font=font, fill='#A9BDCA')
    draw.rectangle((0,640,1279,703), fill='#E8E3C8')
    draw.text((24,657), 'Synthetic test artwork | Project MIT license | No real cartography', font=credit_font, fill='#08131E')
    image.save(path)


if __name__ == '__main__':
    generate(Path(__file__).with_name('synthetic-georeferenced.png'))
