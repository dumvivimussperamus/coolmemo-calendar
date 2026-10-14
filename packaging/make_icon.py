from PIL import Image, ImageDraw, ImageFont

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((24, 24, S - 24, S - 24), radius=96, fill="#fff6ef", outline="#367060", width=14)
d.rounded_rectangle((24, 24, S - 24, 190), radius=96, fill="#e96b5a")
d.rectangle((24, 120, S - 24, 190), fill="#e96b5a")
for x in (150, S - 150):
    d.rounded_rectangle((x - 18, 0, x + 18, 90), radius=18, fill="#367060")
try:
    font = ImageFont.truetype("malgunbd.ttf", 230)
except OSError:
    font = ImageFont.load_default()
d.text((S / 2, 345), "31", font=font, fill="#367060", anchor="mm")
img.save("app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
