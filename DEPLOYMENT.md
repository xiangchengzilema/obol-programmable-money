# Obol deployment

Obol is deployed as one Flask service. The same process serves:

- `/` and all frontend assets
- `/api/*`
- `/x402/articles/<id>`

## Safety model

The public judge-facing deployment must run in **mock settlement mode**. Its
WSGI entrypoint defaults `OBOL_PUBLIC_DEMO=1`, which forces
`OBOL_FORCE_MOCK=1` before the application imports. Do not add Circle, OpenAI,
or wallet credentials to the public Railway service.

Live Arc Testnet evidence is generated only from the local, ignored
`backend/.env` and then documented with non-secret transaction proof. This
keeps an anonymous website from being able to spend from a testnet wallet.

## Railway deployment

The repository includes `railway.json`, `.python-version`, `Procfile`, and
`backend/wsgi.py`.

1. In Railway, choose **New Project → Deploy from GitHub repo**.
2. Select `xiangchengzilema/obol-programmable-money`.
3. Let Railway use the checked-in `railway.json`.
4. Add these non-secret variables:

   ```env
   OBOL_PUBLIC_DEMO=1
   OBOL_AUTO_SEED=1
   OBOL_DISABLE_DEMO_RESET=1
   FLASK_DEBUG=0
   ```

5. Under **Networking**, generate a public domain.
6. Optionally attach a Volume at `/data` and set:

   ```env
   OBOL_DB_PATH=/data/obol.db
   ```

The configured production command is:

```bash
gunicorn --chdir backend --workers 1 --threads 4 --timeout 120 \
  --bind 0.0.0.0:$PORT wsgi:app
```

One worker avoids concurrent SQLite migrations and seed races. Threads still
allow concurrent judge requests.

## Local modes

Safe local mock demo:

```powershell
$env:OBOL_FORCE_MOCK = "1"
Set-Location backend
python app.py
```

Local Circle/Arc Testnet mode:

```powershell
Set-Location backend
python app.py
```

The second command loads the ignored `backend/.env` when present. Never commit
that file.

## Verification

After every deployment:

```text
GET  /                       -> 200
GET  /api/health             -> mode is mock on the public site
GET  /api/stats              -> seeded creators and articles are present
GET  /x402/articles/1        -> 402
POST /api/agent/run          -> 201 and never exceeds its policy
```

Also open the public URL in an incognito browser and complete one agent run.
If a Volume is attached, restart the service and confirm `/api/stats` still
contains data.

## Secrets

- Keep `.env`, Circle recovery data, wallet metadata, databases, and logs local.
- Set secrets in a private host dashboard only when a private authenticated
  deployment exists.
- The public WSGI entrypoint intentionally overrides live settlement to mock.
- Run the repository secret scan before every push.
