# Deploy Telefy on Back4app Containers

Back4app Containers can run this app as a Docker container. The app must be pushed to a GitHub repository, then connected in the Back4app dashboard.

## Important limitation

The current app stores user data in local SQLite and Telethon session data. On container hosts, local files may not be durable across rebuilds/redeploys unless the platform provides persistent storage. For a quick free deployment, this is acceptable for testing. For real production, move user/session storage to a hosted database or attach persistent storage if Back4app offers it for your plan.

## 1. Create a GitHub repo

Create a new private GitHub repository, for example:

```text
telefy
```

Push only the code files. Do not commit `.env`, `database.db`, `secret.key`, `.session` files, or token caches.

From this folder:

```powershell
git init
git add main.py database.py dashboard.html requirements.txt Dockerfile .dockerignore .gitignore .env.example DEPLOY_BACK4APP.md
git commit -m "Prepare Back4app container deploy"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/telefy.git
git push -u origin main
```

## 2. Create the Back4app app

In Back4app:

1. Open Containers.
2. Create a new app.
3. Connect your GitHub account.
4. Select the `telefy` repository.
5. Use the root folder as the app path.
6. Let Back4app build from the `Dockerfile`.

## 3. Add environment variables

In the Back4app app settings, add:

```env
TELEGRAM_API_ID=your_value
TELEGRAM_API_HASH=your_value
TELEGRAM_BOT_TOKEN=your_value
TELEGRAM_PHONE=your_value

SPOTIFY_CLIENT_ID=your_value
SPOTIFY_CLIENT_SECRET=your_value

APP_HOST=0.0.0.0
APP_PORT=8080

DEFAULT_BIO=Your default telegram bio goes here.
ORIGINAL_FIRST_NAME=Nino
ORIGINAL_LAST_NAME=Keshelava
```

After the first deploy, Back4app gives you a public HTTPS URL. Set these two env vars to that URL:

```env
WEBAPP_URL=https://your-back4app-url
SPOTIFY_REDIRECT_URI=https://your-back4app-url/callback
```

Then redeploy/restart the container.

## 4. Update Spotify and BotFather

Spotify Developer Dashboard redirect URI:

```text
https://your-back4app-url/callback
```

BotFather menu button:

```text
https://your-back4app-url
```

## 5. Verify

Open:

```text
https://your-back4app-url/api/status
```

It should return JSON. Then send `/start` to your Telegram bot and open the Mini App.
