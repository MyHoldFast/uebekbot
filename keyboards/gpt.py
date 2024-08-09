from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

models = [
    ("gpt-4o-mini"),
    ("claude-3-haiku"),
    ("llama-3-70b"),
    ("mixtral-8x7b")
]

def get_gpt_keyboard(model: str):
    keyboard = []
    row = []
    for model_name in models:
        text = "✓ " + model_name if model == model_name else model_name
        row.append(InlineKeyboardButton(text=text, callback_data=model_name))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)