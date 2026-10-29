"""Render this application's Nginx templates for one validated public hostname."""

import argparse
import ipaddress
import re
from pathlib import Path


def validate_domain(domain):
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if len(domain) > 253 or not re.fullmatch(rf"{label}(?:\.{label})+", domain):
        raise ValueError("Use um hostname completo, sem protocolo, porta ou caminho.")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return domain
    raise ValueError("Informe um dominio, nao um IP.")


def render(domain, output):
    validate_domain(domain)
    source = Path(__file__).resolve().parent / "nginx"
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ("bootstrap.conf", "site.conf"):
        content = (source / name).read_text(encoding="utf-8")
        (output / name).write_text(content.replace("vps-monitor.net", domain), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, type=lambda value: validate_domain(value.lower()))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    render(args.domain, args.output)
