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
ICON_SIZE_NIGHT = 30
TEMP_SIZE_DAY = 30
TEMP_SIZE_NIGHT = 25
CLOUD_Y_OFFSET = -10

DAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

WEATHER_CODES = {
    0: "Ясное небо",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Туман с изморозью",
    51: "Слабая морось",
    53: "Умеренная морось",
    55: "Сильная морось",
    56: "Слабая ледяная морось",
    57: "Сильная ледяная морось",
    61: "Небольшой дождь",
    63: "Умеренный дождь",
    65: "Сильный дождь",
    66: "Слабый ледяной дождь",
    67: "Сильный ледяной дождь",
    71: "Небольшой снег",
    73: "Умеренный снег",
    75: "Сильный снег",
    77: "Снежная крупа",
    80: "Кратковременный дождь",
    81: "Ливневый дождь",
    82: "Сильный ливень",
    85: "Слабый снегопад",
    86: "Сильный снегопад",
    95: "Гроза",
    96: "Гроза с градом",
    99: "Сильная гроза с градом"
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


def wind_arrow(deg):
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
    idx = round(deg / 45) % 8
    return arrows[idx]


def draw_moon(img, center, size, color, angle=-25):
    x, y = center
    moon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(moon)

    d.ellipse((0, 0, size, size), fill=color)
    cut = int(size * 0.4)
    d.ellipse((-cut, 0, size - cut, size), fill=(0, 0, 0, 0))

    moon = moon.rotate(angle, resample=Image.BICUBIC, expand=True)
    w, h = moon.size
    img.alpha_composite(moon, (int(x - w / 2), int(y - h / 2)))


def icon_by_code(code, is_night=False):
    if code in (0, 1):
        return "moon" if is_night else "☀"
    if code in (2, 3):
        return "☁"
    if code in (45, 48):
        return "≋"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "☂"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄"
    if code in (95, 96, 99):
        return "⚡"
    return "☁"


def iy(y, icon):
    return y + CLOUD_Y_OFFSET if icon == "☁" else y


async def get_coordinates(city: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 5, "addressdetails": 1},
            headers={
                "User-Agent": "weather-sticker-bot/1.0",
                "Accept-Encoding": "gzip, deflate"
            },
            timeout=10
        ) as r:
            data = await r.json()

    if not data:
        raise ValueError(city)

    place_types = [
        "city", "town", "village", "hamlet", "isolated_dwelling", 
        "farm", "allotments", "neighbourhood", "suburb", "quarter", 
        "borough", "municipality", "administrative"
    ]
    
    for item in data:
        if item.get("class") == "place" and item.get("type") in place_types:
            address = item.get("address")
            if address and "city" in address:
                city_name = address["city"]
            else:
                city_name = item["display_name"].split(",")[0]
            
            return float(item["lat"]), float(item["lon"]), city_name

    i = data[0]
    address = i.get("address")
    if address and "city" in address:
        city_name = address["city"]
    else:
        city_name = i["display_name"].split(",")[0]
    
    return float(i["lat"]), float(i["lon"]), city_name


async def get_weather(lat, lon):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "hourly": "temperature_2m,weathercode,pressure_msl",
                "timezone": "auto",
                "windspeed_unit": "ms"
            },
            headers={
                "Accept-Encoding": "gzip, deflate"
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
            "day_icon": icon_by_code(dc, False),
            "night_icon": icon_by_code(nc, True)
        })

    cur = data["current_weather"]
    hour = int(cur["time"].split("T")[1][:2])
    is_night = hour < 6 or hour >= 21

    current_time = cur["time"]
    pressure = None
    try:
        time_idx = data["hourly"]["time"].index(current_time)
        pressure = round(data["hourly"]["pressure_msl"][time_idx])
    except (ValueError, IndexError):
        if data["hourly"]["time"]:
            pressure = round(data["hourly"]["pressure_msl"][0])

    current_date = cur["time"].split("T")[0]
    today_hours = days.get(current_date, [])
    
    today_summary = None
    if today_hours:
        day_data = [(t, c) for h, t, c in today_hours if 10 <= h <= 17]
        night_data = [(t, c) for h, t, c in today_hours if h >= 22 or h < 6]
        
        if day_data and night_data:
            day_codes = [c for _, c in day_data]
            night_codes = [c for _, c in night_data]
            day_icon = icon_by_code(max(set(day_codes), key=day_codes.count), False)
            night_icon = icon_by_code(max(set(night_codes), key=night_codes.count), True)
            
            today_summary = {
                "day_temp": round(sum(t for t, _ in day_data) / len(day_data)),
                "night_temp": round(sum(t for t, _ in night_data) / len(night_data)),
                "day_icon": day_icon,
                "night_icon": night_icon
            }

    return {
        "city": city,
        "temp": round(cur["temperature"]),
        "icon": icon_by_code(cur["weathercode"], is_night),
        "desc": WEATHER_CODES.get(cur["weathercode"], "—"),
        "wind_speed": round(cur.get("windspeed", 0), 1),
        "wind_dir": cur.get("winddirection", 0),
        "pressure": pressure,
        "today_summary": today_summary,
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

    dr.text((WIDTH // 2, 33), d["city"], font=cf, anchor="mm", fill="white")
    dr.text((WIDTH // 2, 80), d["desc"], font=df, anchor="mm", fill="#bbb")

    CURRENT_BLOCK_Y = 145
    CURRENT_SUMMARY_GAP = 60
    RIGHT_WIND_PRESS_GAP = 35
    SEPARATOR_ALPHA = 50
    
    SUMMARY_ICON_SIZE = 32
    SUMMARY_MOON_SIZE = 28
    SUMMARY_TEMP_SIZE = 28

    left_col_center_x = 170
    right_center_x = 425
    separator_x = 340
    
    top_y = CURRENT_BLOCK_Y
    bottom_y = top_y + RIGHT_WIND_PRESS_GAP
    summary_y = top_y + CURRENT_SUMMARY_GAP
    
    sep_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sep_draw = ImageDraw.Draw(sep_layer)
    sep_draw.line([(separator_x, top_y - 10), (separator_x, bottom_y + 10)], 
                  fill=(255, 255, 255, SEPARATOR_ALPHA), width=2)
    img = Image.alpha_composite(img, sep_layer)
    
    dr = ImageDraw.Draw(img)
    
    ifo = ImageFont.truetype(FONT_PATH, 70)
    tf = ImageFont.truetype(FONT_PATH, 70)
    temp_text = format_temp(d["temp"])
    
    icon_size_cur = 42
    icon_bbox = dr.textbbox((0, 0), d["icon"], font=ifo) if d["icon"] != "moon" else (0, 0, icon_size_cur, icon_size_cur)
    icon_width = icon_bbox[2]
    
    total_width = icon_width + 10 + dr.textbbox((0, 0), temp_text, font=tf)[2]
    start_x = left_col_center_x - total_width // 2
    
    cur_icon_x = start_x + icon_width // 2
    if d["icon"] == "moon":
        draw_moon(img, (cur_icon_x, top_y), icon_size_cur, (255, 255, 255, 255))
    else:
        dr.text((cur_icon_x, iy(top_y, d["icon"])), d["icon"], font=ifo, anchor="mm", fill="white")
    
    dr.text((start_x + icon_width + 10, top_y), temp_text, font=tf, anchor="lm", fill="white")
    
    if d.get("today_summary"):
        sf = ImageFont.truetype(FONT_PATH, SUMMARY_TEMP_SIZE)
        icon_font = ImageFont.truetype(FONT_PATH, SUMMARY_ICON_SIZE)
        
        ts = d["today_summary"]
        
        day_icon = ts["day_icon"]
        night_icon = ts["night_icon"]
        day_temp = format_temp(ts["day_temp"])
        night_temp = format_temp(ts["night_temp"])
        
        day_icon_size = SUMMARY_MOON_SIZE if day_icon == "moon" else dr.textbbox((0, 0), day_icon, font=icon_font)[2]
        night_icon_size = SUMMARY_MOON_SIZE if night_icon == "moon" else dr.textbbox((0, 0), night_icon, font=icon_font)[2]
        
        day_temp_w = dr.textbbox((0, 0), day_temp, font=sf)[2]
        night_temp_w = dr.textbbox((0, 0), night_temp, font=sf)[2]
        
        slash_w = dr.textbbox((0, 0), " / ", font=sf)[2]
        
        total_summary_width = day_icon_size + 8 + day_temp_w + slash_w + night_icon_size + 8 + night_temp_w
        summary_start_x = left_col_center_x - total_summary_width // 2
        
        day_icon_x = summary_start_x + day_icon_size // 2
        if day_icon == "moon":
            draw_moon(img, (day_icon_x, summary_y), SUMMARY_MOON_SIZE, (255, 255, 255, 255))
        else:
            dr.text((day_icon_x, iy(summary_y, day_icon)), day_icon, font=icon_font, anchor="mm", fill="white")
        
        dr.text((summary_start_x + day_icon_size + 8, summary_y), day_temp, font=sf, anchor="lm", fill="white")
        
        slash_x = summary_start_x + day_icon_size + 8 + day_temp_w
        dr.text((slash_x, summary_y), " / ", font=sf, anchor="lm", fill="#888")
        
        night_icon_x = slash_x + slash_w + night_icon_size // 2
        if night_icon == "moon":
            draw_moon(img, (night_icon_x, summary_y), SUMMARY_MOON_SIZE, (200, 200, 200, 255))
        else:
            dr.text((night_icon_x, iy(summary_y, night_icon)), night_icon, font=icon_font, anchor="mm", fill="white")
        
        dr.text((slash_x + slash_w + night_icon_size + 8, summary_y), night_temp, font=sf, anchor="lm", fill="white")
    
    wf = ImageFont.truetype(FONT_PATH, 25)
    wind_text = f"{wind_arrow(d['wind_dir'])} {d['wind_speed']} м/с"
    dr.text((right_center_x, top_y), wind_text, font=wf, anchor="mm", fill="white")
    
    if d.get("pressure"):
        pf = ImageFont.truetype(FONT_PATH, 25)
        pressure_text = f"{d['pressure']} гПа"
        dr.text((right_center_x, bottom_y), pressure_text, font=pf, anchor="mm", fill="white")

    cw, by = WIDTH // 5, 300

    sep = Image.new("RGBA", (WIDTH, HEIGHT))
    sd = ImageDraw.Draw(sep)

    for i in range(1, 5):
        x = cw * i
        sd.line([(x, by - 50), (x, by + 140)], fill=(255, 255, 255, 50))

    for i in range(5):
        sd.line([(cw * i + 20, by + 66), (cw * (i + 1) - 20, by + 66)], fill=(255, 255, 255, 70))

    img = Image.alpha_composite(img, sep)
    dr = ImageDraw.Draw(img)

    dif = ImageFont.truetype(FONT_PATH, ICON_SIZE_DAY)
    nif = ImageFont.truetype(FONT_PATH, ICON_SIZE_NIGHT)
    dtf = ImageFont.truetype(FONT_PATH, TEMP_SIZE_DAY)
    ntf = ImageFont.truetype(FONT_PATH, TEMP_SIZE_NIGHT)
    df2 = ImageFont.truetype(FONT_PATH, 26)

    for i, f in enumerate(d["forecast"]):
        x = cw * i + cw // 2
        dr.text((x, by - 38), f["day"], font=df2, anchor="mm", fill="#bbb")

        if f["day_icon"] == "moon":
            draw_moon(img, (x, by), ICON_SIZE_DAY, (255, 255, 255, 255))
        else:
            dr.text((x, iy(by, f["day_icon"])), f["day_icon"], font=dif, anchor="mm", fill="white")

        dr.text((x, by + 36), format_temp(f["day_temp"]), font=dtf, anchor="mm", fill="white")

        if f["night_icon"] == "moon":
            draw_moon(img, (x, by + 80), 25, (200, 200, 200, 255))
        else:
            dr.text((x, iy(by + 80, f["night_icon"])), f["night_icon"], font=nif, anchor="mm", fill="#ccc")

        dr.text((x, by + 110), format_temp(f["night_temp"]), font=ntf, anchor="mm", fill="#ccc")

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
                {"uid": user_id, "city": city},
                CityQuery().uid == user_id
            )

            await message.reply_sticker(
                BufferedInputFile(sticker.read(), filename="weather.webp")
            )

        except ValueError:
            await message.reply(_("forecast_city_not_found"))
        except Exception as e:
            await message.reply(_("forecast_error") + f" ({e})")