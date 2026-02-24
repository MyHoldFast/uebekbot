
import gettext
#pybabel compile -d locales
LOCALES_DIR = 'locales'
DEFAULT_LANGUAGE = 'ru'
LANGUAGES =  ['ru', 'uk', 'en', 'es']

def get_localization(language_code):
    lang = language_code if language_code in LANGUAGES else DEFAULT_LANGUAGE
    translation = gettext.translation('messages', localedir=LOCALES_DIR, languages=[lang])
    translation.install()
    return translation.gettext
