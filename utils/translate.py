import aiohttp, os

API_KEY_TR = os.getenv("YANDEX_TR_API")

async def translate_text(text, source_lang='auto', target_lang='ru'):
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": text
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=params) as response:
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
        "Authorization": "Api-Key {0}".format(API_KEY_TR)
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
