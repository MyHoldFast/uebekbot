# UebekBot

Этот проект представляет собой бота, который выполняет несколько функций, включая:

- **/summary**: Краткая выжимка из видео на YouTube, статей из Википедии или материалов с Habr, а так же просто длинного сообщения через реплай
- **/ocr**: Распознавание текста на изображениях.
- **/stt**: Перевод голосовых сообщений в текст.
- **/gpt**: Чат с AI на базе GPT.

## Модели

В проекте используются следующие модели, предоставляемые DuckDuckGo:

- `gpt-4o-mini`
- `claude-3-haiku`
- `llama-3.1-70b`
- `mixtral-8x7b`

Для работы некоторых функций требуются следующие сервисы:

- **/summary**: Для этой функции требуется Yandex OAuth Token (он бесплатный).
- **/ocr**: Для этой функции необходим доступ к Yandex Cloud.