"""Ícones coloridos da barra de atalhos e dos menus, desenhados em tempo de execução (sem arquivos extras)."""
from PIL import Image, ImageDraw, ImageTk

from . import theme as t


def _draw(name):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    if name == "painel":
        colors = ("#0875C9", "#FF4B12", "#22A06B", "#F2B705")
        for (x, y), color in zip(((6, 6), (35, 6), (6, 35), (35, 35)), colors):
            d.rounded_rectangle((x, y, x + 23, y + 23), radius=4, fill=color)
    elif name == "folha":
        d.rounded_rectangle((10, 4, 54, 60), radius=4, fill="#FFFFFF", outline="#064B82", width=3)
        d.rectangle((10, 4, 54, 16), fill="#0875C9")
        for y in (24, 32, 40):
            d.line((18, y, 46, y), fill="#98A2B3", width=3)
        d.ellipse((30, 38, 58, 62), fill="#22A06B", outline="#14724A", width=2)
        d.text((39, 41), "$", fill="#FFFFFF")
    elif name == "energia":
        d.polygon([(30, 2), (8, 36), (26, 36), (18, 62), (44, 24), (27, 24), (38, 2)],
                  fill="#F2B705", outline="#A87C00")
        d.polygon([(50, 26), (40, 44), (60, 44)], fill="#1D8FE1")
        d.ellipse((40, 36, 60, 58), fill="#1D8FE1", outline="#0B5FA0", width=2)
    elif name == "backups":
        d.rounded_rectangle((8, 8, 56, 56), radius=5, fill="#0875C9", outline="#064B82", width=2)
        d.rectangle((20, 9, 44, 26), fill="#DCEBFA", outline="#064B82", width=2)
        d.rectangle((36, 12, 41, 23), fill="#064B82")
        d.rectangle((16, 34, 48, 55), fill="#FFFFFF", outline="#064B82", width=2)
        d.arc((22, 37, 42, 55), 200, 520, fill="#FF4B12", width=4)
    elif name == "admin":
        d.polygon([(32, 3), (56, 12), (54, 36), (32, 61), (10, 36), (8, 12)], fill="#064B82", outline="#043257")
        d.polygon([(32, 10), (49, 17), (48, 35), (32, 53)], fill="#0875C9")
        d.line((21, 32, 29, 41, 44, 23), fill="#FFFFFF", width=6)
    elif name == "sobre":
        d.ellipse((5, 5, 59, 59), fill="#0875C9", outline="#064B82", width=2)
        d.ellipse((28, 13, 36, 21), fill="#FFFFFF")
        d.rectangle((28, 26, 36, 50), fill="#FFFFFF")
    elif name == "bloquear":
        d.arc((16, 4, 48, 40), 180, 360, fill="#667085", width=7)
        d.line((16, 21, 16, 30), fill="#667085", width=7)
        d.line((48, 21, 48, 30), fill="#667085", width=7)
        d.rounded_rectangle((8, 28, 56, 60), radius=6, fill="#FF4B12", outline="#B83208", width=2)
        d.ellipse((27, 36, 37, 46), fill="#FFFFFF")
        d.line((32, 44, 32, 53), fill="#FFFFFF", width=4)
    elif name == "sair":
        d.rounded_rectangle((6, 6, 38, 58), radius=3, fill="#E2E8F0", outline="#667085", width=3)
        d.ellipse((28, 30, 33, 35), fill="#667085")
        d.line((30, 32, 56, 32), fill="#D92D20", width=7)
        d.polygon([(46, 20), (60, 32), (46, 44)], fill="#D92D20")
    elif name == "senha":
        d.ellipse((4, 18, 32, 46), fill="#F2B705", outline="#A87C00", width=2)
        d.ellipse((12, 27, 21, 36), fill="#FFFFFF")
        d.rectangle((30, 28, 60, 36), fill="#F2B705", outline="#A87C00")
        d.rectangle((48, 36, 54, 46), fill="#F2B705", outline="#A87C00")
    else:
        d.rounded_rectangle((8, 8, 56, 56), radius=6, fill=t.BORDER)
    return image


def photo(name, size, master, gap=0):
    image = _draw(name).resize((size, size), Image.Resampling.LANCZOS)
    if gap:
        padded = Image.new("RGBA", (size + gap, size), (0, 0, 0, 0))
        padded.paste(image, (0, 0))
        image = padded
    return ImageTk.PhotoImage(image, master=master)
