# Deployment

| Part | Host | Cost |
|---|---|---|
| Frontend (Next.js) | Vercel | Free (Hobby) |
| Backend (FastAPI + model) | Hugging Face Docker Space, CPU basic | Free |
| Database | SQLite inside the backend image; Neon optional | Free |

The backend needs about 3 GB of RAM (measured with the model, embedding and reranker models
loaded). Render's free and starter plans have 512 MB, which is why it runs on a Space
(16 GB, 2 vCPU).

## 1. Backend: Hugging Face Space

1. Create a Hugging Face account and a **write** token at https://huggingface.co/settings/tokens.
2. From `backend/` with the venv active:

   ```powershell
   venv\Scripts\activate
   hf auth login        # paste the token once
   python ../scripts/deploy_hf_space.py --space <hf-username>/rcm-intelligence-api
   ```

   The first run uploads the 1.1 GB model; later runs send only changed files.
3. Watch the build at `https://huggingface.co/spaces/<hf-username>/rcm-intelligence-api`
   (first build roughly 10-15 minutes). When it shows **Running**, check
   `https://<hf-username>-rcm-intelligence-api.hf.space/health` reports `"status":"ok"`.

The Space must be **public** so browsers can call it. That also makes its files, including the
fine-tuned model, downloadable by anyone.

## 2. Frontend: Vercel

1. Push the repo to GitHub, then **Add New → Project** in Vercel and import it.
2. Set **Root Directory** to `frontend` (framework: Next.js, detected automatically).
3. Add the environment variable
   `NEXT_PUBLIC_API_BASE_URL = https://<hf-username>-rcm-intelligence-api.hf.space`
   (no trailing slash), then **Deploy**.

## 3. Allow the frontend to call the backend (CORS)

Re-run the deploy script with the Vercel URL. It stores it as a Space variable, which restarts
the Space:

```powershell
python ../scripts/deploy_hf_space.py --space <hf-username>/rcm-intelligence-api `
  --cors-origin https://<your-project>.vercel.app `
  --cors-origin-regex "https://<your-project>(-[a-z0-9-]+)?\.vercel\.app"
```

The regex also allows Vercel preview deployments. The same two values can be set by hand under
the Space's **Settings → Variables** as `CORS_ORIGINS` (JSON list) and `CORS_ORIGIN_REGEX`.

## Optional: Neon instead of the built-in SQLite

The API only reads the database, and the image already contains the synthetic data, so Neon is
not required. To use it anyway:

1. Create a Neon project and copy its connection string.
2. Seed it once from your machine (same data as the image and the Presenter's Guide):

   ```powershell
   $env:DATABASE_URL = "<neon connection string>"
   python ../scripts/seed_database.py --reset --as-of 2026-10-06
   Remove-Item Env:DATABASE_URL
   ```

3. Store it as a Space secret: re-run the deploy script with `--database-url "<neon connection string>"`.

Neon's free tier suspends after a few idle minutes, so the first query after a pause is slower.

## Things to know

- **Answers are slower than on a laptop:** the Space has 2 vCPUs, so expect roughly 30-90 s per
  answer. They stream, so text appears as it is generated.
- **Sleeps when idle:** a free Space sleeps after about 48 hours without visits. The next visit
  restarts it, which takes a few minutes while the model loads.
- **Rate limits** are per visitor (20 chat requests per minute by default; `RATE_LIMIT_*` variables).
