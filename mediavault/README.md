# MediaVault Telegram Bot

Telegram bot with a dark inline-button interface. It accepts audio/video files sent by the user, converts them to MP3 or MP4 with FFmpeg, and returns the result in the same Telegram chat.

## Features
- aiogram 3 bot with /start, /help, /history and /cancel
- MP3 conversion from user-uploaded audio/video
- MP4 conversion from user-uploaded video
- Temporary local processing and Telegram delivery
- Render health endpoint at /health
- Docker deployment with FFmpeg

## Limitations
The bot does not download from YouTube or bypass DRM, login, paywalls, platform restrictions, or access controls. Incoming Telegram file size is limited by the Telegram Bot API and the configured MAX_UPLOAD_MB. Render free instances may sleep and use ephemeral storage; history is in-memory and resets on restart.

## Deploy
1. Revoke any token that has been shared in a chat. Create a replacement with BotFather.
2. Push this folder to GitHub. Never commit .env or a bot token.
3. In Render choose New → Blueprint and connect this repository.
4. Set BOT_TOKEN in the Render service Environment settings using the newly rotated token.
5. Deploy, then open the service URL + /health; expected JSON is {"status":"ok","service":"mediavault"}.
6. Open your bot in Telegram and send /start.

## Local run
Install Python 3.11+, FFmpeg, and requirements from requirements.txt. Set BOT_TOKEN in the environment, then run python bot.py.
