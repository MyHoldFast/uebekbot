import aiohttp
from collections import defaultdict
from datetime import datetime
from io import BytesIO

from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, BufferedInputFile

from utils.command_states import check_command_enabled
from utils.typing_indicator import TypingIndicator
from utils.dbmanager import DB
from localization import DEFAULT_LANGUAGE, get_localization

from PIL import Image, ImageDraw, ImageFont

WIDTH = HEIGHT = 512
FONT_PATH = "res/DejaVuSans-Bold.ttf"
BG_IMAGE = "res/bg.webp"

ICON_SIZE_DAY = 38
ICON_SIZE_NIGHT = 38
TEMP_SIZE_DAY = 30
TEMP_SIZE_NIGHT = 25
CLOUD_Y_OFFSET = -10

DAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

WEATHER_CODES = {
    0: "Ясно", 1: "Ясно", 2: "Переменная облачность", 3: "Пасмурно",
    45: "Туман", 48: "Туман",
    51: "Дождь", 53: "Дождь", 55: "Дождь",
    61: "Дождь", 63: "Дождь", 65: "Дождь",
    71: "Снег", 73: "Снег", 75: "Снег",
    80: "Ливень", 81: "Ливень", 82: "Ливень",
    85: "Снег", 86: "Снег", 95: "Гроза"
}

router = Router()
city_db, CityQuery = DB("db/user_cities.json").get_db()


def fit_text(draw, text, w, h, s):
    while s > 10:
        f = ImageFont.truetype(FONT_PATH, s)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] <= w and b[3] <= h:
            return f
        s -= 1
    return ImageFont.truetype(FONT_PATH, 12)

def format_temp(t):
    t = round(t)
    return f"+{t}°C" if t > 0 else f"{t}°C"

def icon_by_code(c):
    if c in (0, 1): return "☀"
    if c in (2, 3): return "☁"
    if c in (45, 48): return "≋"
    if c in (51, 53, 55, 61, 63, 65, 80, 81, 82): return "☂"
    if c in (71, 73, 75, 85, 86): return "❄"
    if c == 95: return "⚡"
    return "☁"

def iy(y, i):
    return y + CLOUD_Y_OFFSET if i == "☁" else y


async def get_coordinates(city: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1, "accept-language": "auto"},
            headers={"User-Agent": "weather-sticker-bot/1.0"},
            timeout=10
        ) as r:
            data = await r.json()

    if not data:
        raise ValueError(city)

    i = data[0]
    return float(i["lat"]), float(i["lon"]), i["display_name"].split(",")[0]

async def get_weather(lat, lon):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "hourly": "temperature_2m,weathercode",
                "timezone": "auto"
            },
            timeout=10
        ) as r:
            return await r.json()

def build_data(city, data):
    days = defaultdict(list)

    for t, temp, code in zip(
        data["hourly"]["time"],
        data["hourly"]["temperature_2m"],
        data["hourly"]["weathercode"]
    ):
        d, h = t.split("T")
        days[d].append((int(h[:2]), temp, code))

    forecast = []
    for d in sorted(days)[1:6]:
        day = [(t, c) for h, t, c in days[d] if 10 <= h <= 17]
        night = [(t, c) for h, t, c in days[d] if h <= 6 or h >= 22]
        if not day or not night:
            continue

        dc = max([c for _, c in day], key=[c for _, c in day].count)
        nc = max([c for _, c in night], key=[c for _, c in night].count)

        forecast.append({
            "day": DAYS_RU[datetime.fromisoformat(d).weekday()],
            "day_temp": round(sum(t for t, _ in day) / len(day)),
            "night_temp": round(sum(t for t, _ in night) / len(night)),
            "day_icon": icon_by_code(dc),
            "night_icon": icon_by_code(nc)
        })

    cur = data["current_weather"]

    return {
        "city": city,
        "temp": round(cur["temperature"]),
        "icon": icon_by_code(cur["weathercode"]),
        "desc": WEATHER_CODES.get(cur["weathercode"], "—"),
        "forecast": forecast
    }


def draw_card(d) -> BytesIO:
    bg = Image.open(BG_IMAGE).convert("RGBA").resize((WIDTH, HEIGHT))
    img = Image.new("RGBA", (WIDTH, HEIGHT), "#0c1020")
    img = Image.alpha_composite(img, bg)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 80))
    img = Image.alpha_composite(img, overlay)
    dr = ImageDraw.Draw(img)

    cf = fit_text(dr, d["city"], 480, 48, 46)
    df = fit_text(dr, d["desc"], 480, 36, 30)

    dr.text((WIDTH//2, 33), d["city"], font=cf, anchor="mm", fill="white")
    dr.text((WIDTH//2, 85), d["desc"], font=df, anchor="mm", fill="#bbb")

    ifo = ImageFont.truetype(FONT_PATH, 90)
    tf = ImageFont.truetype(FONT_PATH, 90)

    ib = dr.textbbox((0, 0), d["icon"], font=ifo)
    tb = dr.textbbox((0, 0), format_temp(d["temp"]), font=tf)
    sx = WIDTH//2 - (ib[2] + tb[2] + 20)//2

    dr.text((sx, iy(155, d["icon"])), d["icon"], font=ifo, anchor="lm", fill="white")
    dr.text((sx + ib[2] + 20, 155), format_temp(d["temp"]), font=tf, anchor="lm", fill="white")

    cw, by = WIDTH//5, 280

    sep = Image.new("RGBA", (WIDTH, HEIGHT))
    sd = ImageDraw.Draw(sep)

    for i in range(1, 5):
        x = cw * i
        sd.line([(x, by-50), (x, by+140)], fill=(255, 255, 255, 50))

    for i in range(5):
        sd.line([(cw*i+20, by+66), (cw*(i+1)-20, by+66)], fill=(255, 255, 255, 70))

    img = Image.alpha_composite(img, sep)
    dr = ImageDraw.Draw(img)

    dif = ImageFont.truetype(FONT_PATH, ICON_SIZE_DAY)
    nif = ImageFont.truetype(FONT_PATH, ICON_SIZE_NIGHT)
    dtf = ImageFont.truetype(FONT_PATH, TEMP_SIZE_DAY)
    ntf = ImageFont.truetype(FONT_PATH, TEMP_SIZE_NIGHT)
    df2 = ImageFont.truetype(FONT_PATH, 26)

    for i, f in enumerate(d["forecast"]):
        x = cw*i + cw//2
        dr.text((x, by-38), f["day"], font=df2, anchor="mm", fill="#bbb")
        dr.text((x, iy(by, f["day_icon"])), f["day_icon"], font=dif, anchor="mm", fill="white")
        dr.text((x, by+36), format_temp(f["day_temp"]), font=dtf, anchor="mm", fill="white")
        dr.text((x, iy(by+86, f["night_icon"])), f["night_icon"], font=nif, anchor="mm", fill="#ccc")
        dr.text((x, by+116), format_temp(f["night_temp"]), font=ntf, anchor="mm", fill="#ccc")

    buf = BytesIO()
    img.convert("RGB").save(buf, "WEBP", quality=95)
    buf.seek(0)
    return buf


@router.message(Command("forecast", ignore_case=True))
@check_command_enabled("forecast")
async def forecast_command(message: Message, command: CommandObject, bot: Bot):
    user_language = message.from_user.language_code or DEFAULT_LANGUAGE
    _ = get_localization(user_language)

    user_id = message.from_user.id
    city = command.args.strip() if command.args else None

    if not city:
        saved = city_db.get(CityQuery().uid == user_id)
        if not saved:
            await message.reply(_("forecast_help"), parse_mode="Markdown")
            return
        city = saved["city"]

    async with TypingIndicator(bot=bot, chat_id=message.chat.id):
        try:
            lat, lon, name = await get_coordinates(city)
            weather = await get_weather(lat, lon)
            data = build_data(name, weather)

            sticker = draw_card(data)

            city_db.upsert(
                {"uid": user_id, "city": name},
                CityQuery().uid == user_id
            )

            await message.reply_sticker(
                BufferedInputFile(sticker.read(), filename="weather.webp")
            )

        except ValueError:
            await message.reply(_("forecast_city_not_found"))
        except Exception as e:
            await message.reply(_("forecast_error") + f" ({e})")
