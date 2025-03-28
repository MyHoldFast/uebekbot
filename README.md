# UebekBot

Для запуска требуется **python3.10**

Этот проект представляет собой бота, который выполняет несколько функций, включая:

- **/summary**: Краткая выжимка из видео на YouTube, статей из Википедии или материалов с Habr, а так же просто длинного сообщения через реплай
- **/ocr**: Распознавание текста на изображениях.
- **/stt**: Перевод голосовых сообщений в текст.
- **/gpt**: Чат с AI на базе GPT, а так же в сочетании с изображением и запросом - запрос к Google Gemini
- **/neuro**: Запрос к Yandex Neuro.
- **/qwen**: Запрос к нейросети сhat.qwenlm.ai.
- **/qwenimg**: Генерация изображения через нейросеть сhat.qwenlm.ai.
- **/gemimg**: Генерация изображения через Google Gemini.

## Модели

В проекте используются некоторые модели, предоставляемые [gpt4free](https://github.com/xtekky/gpt4free)

Для работы некоторых функций требуются следующие сервисы:

- **/summary**: Для этой функции требуется Yandex OAuth Token (он бесплатный).
- **/ocr**: Для этой функции необходим доступ к Yandex Cloud.