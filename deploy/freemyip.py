"""Update one FreeMyIP hostname without exposing its token in argv or logs."""

import argparse
import getpass
import http.client
import ipaddress
import ssl
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

from render_nginx import validate_domain


class UpdateError(Exception):
    pass


def extract_token(update_url, domain):
    if len(update_url) > 8192:
        raise UpdateError("A URL de atualizacao e muito longa.")
    try:
        url = urlsplit(update_url.strip())
        params = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=16)
    except ValueError:
        raise UpdateError("URL invalida. Cole a URL HTTPS de atualizacao do FreeMyIP.") from None
    if (url.scheme, url.netloc, url.path) != ("https", "freemyip.com", "/update") or url.fragment:
        raise UpdateError("Use a URL https://freemyip.com/update fornecida pelo FreeMyIP.")
    if params.get("domain") != [domain]:
        raise UpdateError("O dominio da URL nao corresponde ao dominio escolhido para o monitor.")
    tokens = params.get("token", [])
    if len(tokens) != 1 or not tokens[0]:
        raise UpdateError("A URL precisa conter um unico token valido.")
    return tokens[0]


def update_dns(domain, ip, token):
    # Rebuild from an allowlist. Never forward delete, txt or redirect parameters.
    query = urlencode({"token": token, "domain": domain, "myip": ip})
    connection = http.client.HTTPSConnection("freemyip.com", timeout=20, context=ssl.create_default_context())
    try:
        connection.request("GET", "/update?" + query)
        response = connection.getresponse()
        body = response.read(1024).strip()
        if response.status != 200 or body != b"OK":
            raise UpdateError("O FreeMyIP recusou a atualizacao. Confira a URL e o token no site.")
    except (OSError, http.client.HTTPException, ValueError):
        raise UpdateError("Nao foi possivel atualizar o FreeMyIP por HTTPS. Tente novamente.") from None
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--ip", required=True)
    args = parser.parse_args(argv)
    try:
        domain = validate_domain(args.domain.lower())
        address = ipaddress.ip_address(args.ip)
        if not domain.endswith(".freemyip.com") or address.version != 4 or not address.is_global:
            raise UpdateError("Informe um hostname FreeMyIP e o IPv4 publico da VPS.")
        if not sys.stdin.isatty():
            raise UpdateError("Execute em um terminal SSH interativo para colar a URL de forma oculta.")
        url = getpass.getpass("Cole a URL REAL de atualizacao do FreeMyIP (ficara oculta): ")
        token = extract_token(url, domain)
        update_dns(domain, str(address), token)
    except (UpdateError, ValueError, EOFError):
        # Error messages never include the supplied URL, token or HTTP response body.
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, UpdateError) else "Entrada invalida. Confira o dominio, o IP e a URL do FreeMyIP."
        print(message, file=sys.stderr)
        return 1
    print(f"OK: {domain} apontado para {address}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
