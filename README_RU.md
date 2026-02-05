# UebekBot

[![Python >= 3.10](https://raw.githubusercontent.com/MyHoldFast/uebekbot/refs/heads/main/static/python.svg)](#)

[![](https://raw.githubusercontent.com/MyHoldFast/uebekbot/refs/heads/main/static/telegram.svg)](https://t.me/uebekbot)

Этот проект представляет собой бота, который выполняет несколько функций, включая:

- **/summary**: Краткая выжимка из видео на YouTube, статей из Википедии или материалов с Habr, а так же просто длинного сообщения через реплай
- **/forecast**: Прогноз погоды
- **/ocr**: Распознавание текста на изображениях.
- **/stt**: Перевод голосовых сообщений в текст.
- **/tts**: Перевод текста в аудио.
- **/gpt**: Чат с AI на базе GPT, а так же в сочетании с изображением и запросом - запрос к Google Gemini
- **/neuro**: Запрос к Yandex Neuro.
- **/qwen**: Запрос к нейросети сhat.qwenlm.ai.
- **/qwenimg**: Генерация изображения через нейросеть сhat.qwenlm.ai.
- **/flux**: Генерация изображения через Flux 2-max
- **/gemimg**: Генерация/редактирование изображения через Google Gemini.
- **/shazam**: Распознавание аудиотреков через Shazam
- **/rephrase**: Расличные методы перефразирования текста

Для работы некоторых функций требуются следующие сервисы:

- **/summary**: Для этой функции требуется Yandex OAuth Token (он бесплатный).
- **/ocr**: Для этой функции необходим доступ к Yandex Cloud.
