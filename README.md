# UebekBot

**python3.10** is required to run

This project is a bot that performs several functions, including:

- **/summary**: A short summary of a YouTube video, Wikipedia article, or Habr material, as well as just a long message via replay
- **/ocr**: Text recognition in images.
- **/stt**: Translation of voice messages into text.
- **/gpt**: Chat with AI based on GPT, as well as in combination with an image and a request - a request to Google Gemini
- **/neuro**: A request to Yandex Neuro.
- **/qwen**: A request to the neural network chat.qwenlm.ai.
- **/qwenimg**: Image generation via the neural network chat.qwenlm.ai.
- **/gemimg**: Image generation via Google Gemini.

## Models

The project uses some models provided by [gpt4free](https://github.com/xtekky/gpt4free)

Some features require the following services:

- **/summary**: This feature requires Yandex OAuth Token (it's free).
- **/ocr**: This feature requires access to Yandex Cloud.