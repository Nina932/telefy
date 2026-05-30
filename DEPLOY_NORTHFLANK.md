# Deploy Telefy on Northflank

Northflank is a better fit than Back4app's temporary URL because public HTTP ports get a stable generated `code.run` HTTPS domain.

## 1. Link GitHub

Your Northflank team currently says:

```text
Your team doesn't have a version control platform linked.
```

Open:

```text
https://app.northflank.com/t/nyxcores-team
```

Then click:

```text
Link provider -> GitHub
```

Authorize access to:

```text
Nina932/telefy
```

## 2. Create the service

Create a new combined service in your existing project:

```text
Spotify Telegram Engine Control
```

Use:

```text
Repository: Nina932/telefy
Branch: main
Build type: Dockerfile
Dockerfile path: /Dockerfile
Build context / workdir: /
Port: 8080
Protocol: HTTP
Public: enabled
Instances: 1
```

The app listens on `0.0.0.0:8080` in Docker.

## 3. Runtime environment variables

Add these as runtime variables. Do not add them as build arguments.

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

Leave these unset for the first deploy if you do not know the Northflank URL yet:

```env
WEBAPP_URL=
SPOTIFY_REDIRECT_URI=
```

## 4. First deploy and get the stable URL

Deploy the service. Northflank will create a public HTTPS URL like:

```text
https://p01--telefy--xxxx.code.run
```

Northflank documentation says public HTTP ports are automatically assigned a generated `code.run` domain with TLS.

## 5. Update runtime URL variables

After you have the `code.run` URL, update runtime variables:

```env
WEBAPP_URL=https://your-northflank-url.code.run
SPOTIFY_REDIRECT_URI=https://your-northflank-url.code.run/callback
```

Redeploy or restart the service.

## 6. Update Spotify and BotFather

Spotify Developer Dashboard redirect URI:

```text
https://your-northflank-url.code.run/callback
```

BotFather menu button:

```text
https://your-northflank-url.code.run
```

## 7. Verify

Open:

```text
https://your-northflank-url.code.run/api/status
```

It should return JSON.

Then send `/start` to `@Telefy1_bot` and open the Mini App button.

## Northflank AI Agent prompt

Paste this into Northflank's AI Agent after GitHub is linked:

```text
Deploy the GitHub repository Nina932/telefy as a combined service in the project "Spotify Telegram Engine Control".

Use branch main.
Use Dockerfile build.
Dockerfile path: /Dockerfile.
Build context/workdir: /.
Expose public HTTP port 8080.
Use 1 instance on the free/sandbox compute plan if available.

Add these runtime environment variables, not build arguments:
APP_HOST=0.0.0.0
APP_PORT=8080
TELEGRAM_API_ID=<I will paste value>
TELEGRAM_API_HASH=<I will paste value>
TELEGRAM_BOT_TOKEN=<I will paste value>
TELEGRAM_PHONE=<I will paste value>
SPOTIFY_CLIENT_ID=<I will paste value>
SPOTIFY_CLIENT_SECRET=<I will paste value>
DEFAULT_BIO=Your default telegram bio goes here.
ORIGINAL_FIRST_NAME=Nino
ORIGINAL_LAST_NAME=Keshelava

After the service is deployed, show me the generated public code.run URL. I will then set:
WEBAPP_URL=https://generated-code-run-url
SPOTIFY_REDIRECT_URI=https://generated-code-run-url/callback
and redeploy/restart the service.
```
