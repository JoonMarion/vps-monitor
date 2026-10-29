"""Build a deployable archive from an explicit allowlist; never copy .env/.git."""

import hashlib
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "back-end/app.py", "back-end/auth.py", "back-end/database.py", "back-end/monitoring.py",
    "back-end/requirements.txt", "back-end/requirements-production.txt", "back-end/requirements-production.lock",
    "deploy/gunicorn.conf.py", "deploy/vps-monitor.service", "deploy/.env.production.example",
    "deploy/nginx/limits.conf", "deploy/nginx/proxy.conf", "deploy/nginx/bootstrap.conf", "deploy/nginx/site.conf",
    "deploy/ubuntu24.md",
)


def build():
    files = [ROOT / name for name in FILES]
    frontend = ROOT / "front-end" / "dist"
    if not (frontend / "index.html").is_file():
        raise RuntimeError("Gere o frontend primeiro: cd front-end; npm.cmd ci; npm.cmd run build")
    files.extend(path for path in frontend.rglob("*") if path.is_file())
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError(f"Arquivo ausente ou inválido para o pacote: {path.relative_to(ROOT)}")
    output = ROOT / ".artifacts" / "vps-monitor-release.tar.gz"
    output.parent.mkdir(exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(files):
            info = archive.gettarinfo(str(path), arcname=path.relative_to(ROOT).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            with path.open("rb") as source:
                archive.addfile(info, source)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Pacote: {output}")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    build()
