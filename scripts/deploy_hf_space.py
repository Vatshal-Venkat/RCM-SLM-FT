"""Deploy the backend to a Hugging Face Docker Space.

Stages only what the API needs (backend code, the GGUF model, knowledge/, scripts/ and the files
in deploy/hf-space/) and uploads it. Hugging Face then builds the Docker image and starts the API
at https://<owner>-<space>.hf.space. Unchanged files, including the 1.1 GB model after the first
upload, are not sent again.

One-time setup: create a write token at https://huggingface.co/settings/tokens, then either
`hf auth login` or set HF_TOKEN.

Usage (from backend/, after venv/Scripts/activate):
    python ../scripts/deploy_hf_space.py --space <owner>/rcm-intelligence-api \\
        --cors-origin https://<your-app>.vercel.app
    python ../scripts/deploy_hf_space.py --space <owner>/rcm-intelligence-api --dry-run   # stage only

Optional: --database-url <Neon URL> stores DATABASE_URL as a Space secret (the image already
ships a SQLite copy of the synthetic data, so a database is not required).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MODEL = BACKEND / "models" / "rcm_qwen3_1.7b_q4_k_m.gguf"
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def stage(dest: Path) -> list[Path]:
    """Copy the deployable files into `dest`. Never includes .env, venvs, data/ or tests."""
    shutil.copytree(ROOT / "deploy" / "hf-space", dest, dirs_exist_ok=True)
    shutil.copytree(BACKEND / "app", dest / "backend" / "app", ignore=SKIP)
    shutil.copy2(BACKEND / "requirements.txt", dest / "backend" / "requirements.txt")
    shutil.copytree(ROOT / "knowledge", dest / "knowledge", ignore=SKIP)
    shutil.copytree(ROOT / "scripts", dest / "scripts", ignore=SKIP)
    model_dest = dest / "backend" / "models" / MODEL.name
    model_dest.parent.mkdir(parents=True)
    try:
        os.link(MODEL, model_dest)  # same drive: no 1.1 GB copy
    except OSError:
        shutil.copy2(MODEL, model_dest)
    return sorted(p for p in dest.rglob("*") if p.is_file())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--space", required=True, help="owner/name of the Space, e.g. veltris/rcm-intelligence-api")
    p.add_argument("--cors-origin", action="append", default=[],
                   help="frontend origin allowed to call the API (repeatable), e.g. https://app.vercel.app")
    p.add_argument("--cors-origin-regex", help=r"also allow origins matching this regex (Vercel previews)")
    p.add_argument("--database-url", help="optional PostgreSQL/Neon URL, stored as a Space secret")
    p.add_argument("--private", action="store_true",
                   help="create the Space as private (browsers then cannot call the API without a token)")
    p.add_argument("--dry-run", action="store_true", help="stage the files and list them without uploading")
    args = p.parse_args()

    if not MODEL.is_file():
        sys.exit(f"Model not found: {MODEL}")

    with tempfile.TemporaryDirectory(prefix="hf-space-") as tmp:
        files = stage(Path(tmp))
        size = sum(f.stat().st_size for f in files)
        print(f"Staged {len(files)} files ({size / 1e9:.2f} GB) in {tmp}")
        if args.dry_run:
            for f in files:
                print("  ", f.relative_to(tmp).as_posix())
            return

        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
        if args.cors_origin:
            api.add_space_variable(args.space, "CORS_ORIGINS", json.dumps(args.cors_origin))
        if args.cors_origin_regex:
            api.add_space_variable(args.space, "CORS_ORIGIN_REGEX", args.cors_origin_regex)
        if args.database_url:
            api.add_space_secret(args.space, "DATABASE_URL", args.database_url)
        api.upload_folder(
            repo_id=args.space, repo_type="space", folder_path=tmp,
            commit_message="Deploy RCM Intelligence API",
            # Remove code and knowledge files that were deleted locally; the model is re-sent only if changed.
            delete_patterns=["backend/app/**", "knowledge/**", "scripts/**"],
        )
    owner, name = args.space.split("/")
    print(f"\nUploaded. Build logs: https://huggingface.co/spaces/{args.space}")
    print(f"API URL (once built):  https://{owner}-{name}.hf.space".lower().replace("_", "-"))


if __name__ == "__main__":
    main()
