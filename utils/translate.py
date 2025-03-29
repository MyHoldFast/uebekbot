import aiohttp, os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://translate.google.com/",
}


async def translate_text(text, source_lang='auto', target_lang='ru'):
    url = "https://translate.flossboxin.org.in/translate"
    headers = {"Content-Type": "application/json"}
    payload = {
        "q": text, 
        "source": source_lang, 
        "target": target_lang,  
        "format": "text", 
        "alternatives": 0,  
        "api_key": ""  
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("translatedText") 
            else:
                error_message = await response.text()
                raise Exception(f"Error {response.status}: {error_message}")

async def translate_text_google(text, source_lang='auto', target_lang='ru'):
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": text
    }

    proxy = os.getenv("PROXY")
    headers = HEADERS.copy()

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=params, proxy=proxy, headers=headers) as response:
            data = await response.json()
            if data and data[0]:
                return ''.join(item[0] for item in data[0])
            else:
                return ""
            
async def translate_text_ya(texts, target_language):
    body = {
        "targetLanguageCode": target_language,
        "texts": texts
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Api-Key {0}".format(os.getenv("YANDEX_TR_API"))
    }

    async with aiohttp.ClientSession() as session:
        async with session.post('https://translate.api.cloud.yandex.net/translate/v2/translate', json=body, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                translations = data['translations']
                for translation in translations:
                    return (translation['text'])
            else:
                return ""
