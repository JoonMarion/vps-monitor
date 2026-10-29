#!/usr/bin/env bash
# First install / resume on Ubuntu 24.04 with native Nginx and PostgreSQL.
set -Eeuo pipefail
umask 077

DOMAIN=vps-monitor.freemyip.com
if [[ $# -gt 0 ]]; then
    [[ $# -eq 2 && $1 == --domain ]] || { printf 'Uso: sudo bash deploy/install.sh [--domain nome.dominio]\n' >&2; exit 2; }
    DOMAIN=${2,,}
fi
readonly DOMAIN
readonly SITE_AVAILABLE="/etc/nginx/sites-available/$DOMAIN"
readonly SITE_ENABLED="/etc/nginx/sites-enabled/$DOMAIN"
readonly EXPECTED_IP=89.117.75.166
readonly APP=/opt/vps-monitor
readonly CONFIG=/etc/vps-monitor
readonly STATE=/etc/vps-monitor/installer-managed
readonly SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
BACKUP=

die() { printf '\nERRO: %s\n' "$*" >&2; exit 1; }
say() { printf '\n>>> %s\n' "$*"; }
pg() { runuser -u postgres -- psql -X -w -h /var/run/postgresql -p 5432 -v ON_ERROR_STOP=1 "$@"; }
failed() {
    local result=$?
    printf '\nInstalacao interrompida (codigo %s). Corrija o erro acima e execute novamente.\n' "$result" >&2
    if [[ -n "$BACKUP" ]]; then printf 'Backup desta tentativa: %s\n' "$BACKUP" >&2; fi
    exit "$result"
}

preflight() {
    [[ $EUID -eq 0 ]] || die 'Execute com sudo bash deploy/install.sh.'
    [[ -r /etc/os-release ]] || die 'Sistema operacional nao identificado.'
    . /etc/os-release
    [[ $ID == ubuntu && $VERSION_ID == 24.04 && $(uname -m) == x86_64 ]] || die 'Este pacote requer Ubuntu 24.04 x86-64.'
    [[ $(python3 -c 'import sys; print("%s.%s" % sys.version_info[:2])') == 3.12 ]] || die 'Este lock requer Python 3.12.'
    python3 - "$DOMAIN" <<'PY'
import ipaddress, re, sys
domain = sys.argv[1]
label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
if len(domain) > 253 or not re.fullmatch(rf'{label}(?:\.{label})+', domain):
    raise SystemExit('Dominio invalido. Use apenas o hostname completo, sem https, porta ou caminho.')
try:
    ipaddress.ip_address(domain)
except ValueError:
    pass
else:
    raise SystemExit('Informe um dominio publico, nao um endereco IP.')
PY
    for command in nginx systemctl runuser psql getent tar; do
        command -v "$command" >/dev/null || die "Comando necessario ausente: $command. Nginx/PostgreSQL devem estar instalados no host."
    done
    unset PGHOST PGHOSTADDR PGDATABASE PGUSER PGPASSWORD PGSERVICE PGSERVICEFILE PGOPTIONS
    systemctl is-active --quiet nginx || die 'O Nginx existente precisa estar ativo.'
    nginx -t
    pg -d postgres -Atqc 'SELECT 1' >/dev/null
    [[ $(pg -d postgres -Atqc 'SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL') == 0 ]] || die 'O pg_hba.conf ja possui erros. Corrija-os antes do deploy.'
    local nginx_user nginx_group nginx_config
    nginx_config=$(nginx -T 2>/dev/null)
    nginx_user=$(printf '%s\n' "$nginx_config" | awk '$1=="user" && !seen {gsub(/;/, "", $2); print $2; seen=1}')
    nginx_group=$(printf '%s\n' "$nginx_config" | awk '$1=="user" && NF>=3 && !seen {gsub(/;/, "", $3); print $3; seen=1}')
    [[ $nginx_user == www-data ]] || die 'O unit fornecido requer Nginx como www-data; adapte o grupo antes de instalar.'
    [[ -z $nginx_group || $nginx_group == www-data ]] || die 'Grupo do Nginx diferente de www-data; adapte o unit.'
    if command -v certbot >/dev/null; then
        [[ $(command -v certbot) == /usr/bin/certbot ]] || die 'Certbot existente fora do pacote Ubuntu; integre a renovacao pelo mecanismo atual.'
    fi
    [[ -f "$SOURCE/back-end/requirements-production.lock" && -f "$SOURCE/front-end/dist/index.html" ]] || die 'Pacote incompleto: faltam dependencias ou frontend compilado.'
    if find "$SOURCE/back-end" "$SOURCE/front-end" "$SOURCE/deploy" -type l -print -quit | grep -q .; then
        die 'O pacote nao deve conter links simbolicos.'
    fi
    if [[ -e $STATE ]]; then
        [[ ! -L $STATE && $(stat -c %u "$STATE") == 0 && $(cat "$STATE") == "$DOMAIN" ]] || die 'Marcador de instalacao invalido.'
        return
    fi
    local target
    for target in "$APP" "$CONFIG" /etc/systemd/system/vps-monitor.service \
        /etc/nginx/conf.d/vps-monitor-limits.conf /etc/nginx/snippets/vps-monitor-proxy.conf \
        "$SITE_AVAILABLE" "$SITE_ENABLED"; do
        [[ ! -e $target && ! -L $target ]] || die "Ja existe: $target. O instalador nao assume controle de uma instalacao anterior."
    done
    if getent passwd vps-monitor >/dev/null || getent group vps-monitor >/dev/null; then
        die 'O usuario/grupo vps-monitor ja existe. Revise a instalacao anterior.'
    fi
    [[ $(pg -d postgres -Atqc "SELECT count(*) FROM pg_database WHERE datname='vps_monitor'") == 0 ]] || die 'O banco vps_monitor ja existe; utilize o roteiro de atualizacao/integracao.'
    [[ $(pg -d postgres -Atqc "SELECT count(*) FROM pg_roles WHERE rolname IN ('vps-monitor','vps_monitor_owner')") == 0 ]] || die 'Roles do monitor ja existem; revise a instalacao anterior.'
    if printf '%s\n' "$nginx_config" | awk -v host="$DOMAIN" '$1=="server_name" {for (i=2;i<=NF;i++) {gsub(/;/,"",$i); if ($i==host) found=1}} END {exit !found}'; then
        die 'O dominio ja possui configuracao no Nginx. Integre pelo site existente.'
    fi
}

configure_dns() {
    local resolved attempt
    resolved=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)
    [[ $resolved == "$EXPECTED_IP" ]] && return
    if [[ $DOMAIN != *.freemyip.com ]]; then
        die "Configure o registro A de $DOMAIN diretamente para $EXPECTED_IP antes de executar."
    fi
    say "Apontando $DOMAIN para $EXPECTED_IP pelo FreeMyIP"
    python3 "$SOURCE/deploy/freemyip.py" --domain "$DOMAIN" --ip "$EXPECTED_IP"
    say 'Aguardando o DNS ficar disponivel (ate 2 minutos)'
    for attempt in {1..40}; do
        resolved=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)
        [[ $resolved == "$EXPECTED_IP" ]] && return
        sleep 3
    done
    die 'O provedor aceitou a atualizacao, mas o DNS local ainda nao refletiu a mudanca. Aguarde o cache e execute novamente.'
}

prepare() {
    say 'Salvando backups e preparando arquivos'
    install -d -m 700 /root/vps-monitor-backups
    BACKUP=$(mktemp -d /root/vps-monitor-backups/install.XXXXXXXX)
    tar -czf "$BACKUP/nginx.tar.gz" -C /etc nginx
    local hba
    hba=$(pg -d postgres -Atqc 'SHOW hba_file')
    cp --preserve=mode,ownership "$hba" "$BACKUP/pg_hba.conf"
    if [[ -f "$CONFIG/vps-monitor.env" ]]; then cp "$CONFIG/vps-monitor.env" "$BACKUP/vps-monitor.env"; fi
    install -d -m 700 "$CONFIG"
    printf '%s\n' "$DOMAIN" > "$STATE"
    if ! getent passwd vps-monitor >/dev/null; then
        useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin vps-monitor
    fi
    [[ $(id -u vps-monitor) != 0 && $(getent passwd vps-monitor | cut -d: -f7) == /usr/sbin/nologin ]] || die 'Usuario de servico com atributos inesperados.'
    export NEEDRESTART_MODE=l
    apt-get update
    apt-get install -y --no-upgrade --no-install-recommends python3-venv certbot ca-certificates curl
    install -d -o root -g root -m 755 "$APP"
    cp -a "$SOURCE/back-end" "$SOURCE/front-end" "$SOURCE/deploy" "$APP/"
    find "$APP/back-end" "$APP/front-end" "$APP/deploy" -type d -exec chmod 755 {} +
    find "$APP/back-end" "$APP/front-end" "$APP/deploy" -type f -exec chmod 644 {} +
    (
        umask 022
        python3 -m venv "$APP/.venv"
        "$APP/.venv/bin/python" -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r "$APP/back-end/requirements-production.lock"
    )
}

database() {
    say 'Criando/verificando banco exclusivo e permissoes'
    pg -d postgres <<'SQL'
SELECT 'CREATE ROLE vps_monitor_owner NOLOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vps_monitor_owner') \gexec
SELECT 'CREATE ROLE "vps-monitor" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='vps-monitor') \gexec
SELECT 'CREATE DATABASE vps_monitor OWNER vps_monitor_owner' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='vps_monitor') \gexec
SQL
    [[ $(pg -d postgres -Atqc "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='vps_monitor'") == vps_monitor_owner ]] || die 'Proprietario do banco diferente do esperado.'
    [[ $(pg -d postgres -Atqc "SELECT count(*) FROM pg_roles WHERE (rolname='vps_monitor_owner' AND (rolcanlogin OR rolsuper)) OR (rolname='vps-monitor' AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))") == 0 ]] || die 'Atributos das roles diferentes do esperado.'
    [[ $(pg -d postgres -Atqc "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='vps-monitor')") == 0 ]] || die 'A role do aplicativo possui associacoes inesperadas.'
    pg -d vps_monitor <<'SQL'
REVOKE ALL ON DATABASE vps_monitor FROM PUBLIC;
GRANT CONNECT ON DATABASE vps_monitor TO "vps-monitor";
ALTER SCHEMA public OWNER TO vps_monitor_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO "vps-monitor";
SQL
    local hba
    hba=$(pg -d postgres -Atqc 'SHOW hba_file')
    python3 - "$hba" <<'PY'
import os, stat, sys, tempfile
from pathlib import Path
path = Path(sys.argv[1]).resolve(strict=True)
original = path.stat()
rule = 'local   vps_monitor   "vps-monitor"   peer'
content = path.read_text()
if rule not in content.splitlines():
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.vps-monitor-', delete=False) as output:
        temp = output.name
        output.write('# VPS Monitor: only this database and OS user.\n' + rule + '\n' + content)
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), stat.S_IMODE(original.st_mode))
        os.fchown(output.fileno(), original.st_uid, original.st_gid)
    os.replace(temp, path)
PY
    if [[ $(pg -d postgres -Atqc 'SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL') != 0 ]]; then
        cp --preserve=mode,ownership "$BACKUP/pg_hba.conf" "$hba"
        die 'Validacao do pg_hba.conf falhou; arquivo anterior restaurado.'
    fi
    pg -d postgres -Atqc 'SELECT pg_reload_conf()'
    runuser -u postgres -- "$APP/.venv/bin/python" "$APP/deploy/init_local_postgres.py"
    pg -d vps_monitor -c 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users, public.vps_servers TO "vps-monitor";'
    runuser -u vps-monitor -- psql -X -w -h /var/run/postgresql -p 5432 -U vps-monitor -d vps_monitor -c 'SELECT current_user, current_database();'
}

environment() {
    say 'Configurando segredos privados (valores existentes serao preservados)'
    "$APP/.venv/bin/python" - "$CONFIG/vps-monitor.env" "$DOMAIN" <<'PY'
import os, re, secrets, sys, tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values
path = Path(sys.argv[1])
values = dotenv_values(path) if path.exists() else {}
secret = values.get('SECRET_KEY') or secrets.token_hex(32)
if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
    raise RuntimeError('SECRET_KEY existente requer revisao; nao foi substituida.')
key = values.get('VPS_ENCRYPTION_KEY') or Fernet.generate_key().decode()
Fernet(key)
settings = {
    'APP_ENV': 'production', 'FLASK_DEBUG': 'false',
    'DATABASE_URL': 'postgresql://vps-monitor@/vps_monitor?host=/var/run/postgresql',
    'SECRET_KEY': secret, 'VPS_ENCRYPTION_KEY': key,
    'SESSION_COOKIE_SECURE': 'true', 'BEHIND_PROXY': 'true',
    'TRUSTED_HOSTS': sys.argv[2], 'AUTO_CREATE_TABLES': 'false',
    'MAX_VPS_PER_USER': values.get('MAX_VPS_PER_USER') or '10',
    'SSH_ALLOWED_PORTS': values.get('SSH_ALLOWED_PORTS') or '22',
}
with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.env-', delete=False) as output:
    temp = output.name
    os.fchmod(output.fileno(), 0o600)
    for name, value in settings.items():
        if '\n' in value or '\r' in value or "'" in value:
            raise RuntimeError(f'Valor invalido: {name}')
        output.write(f"{name}='{value}'\n")
    output.flush()
    os.fsync(output.fileno())
os.replace(temp, path)
PY
    install -m 644 "$APP/deploy/vps-monitor.service" /etc/systemd/system/vps-monitor.service
    systemd-analyze verify /etc/systemd/system/vps-monitor.service
    systemctl daemon-reload
    systemctl enable vps-monitor
    systemctl restart vps-monitor
    local attempt response
    for attempt in {1..20}; do
        response=$(runuser -u www-data -- curl -s -o /dev/null -w '%{http_code}' --unix-socket /run/vps-monitor/gunicorn.sock -H "Host: $DOMAIN" -H 'X-Forwarded-Proto: https' http://localhost/api/auth/me || true)
        [[ $response == 200 ]] && return
        sleep 1
    done
    journalctl -u vps-monitor -n 30 --no-pager
    die 'O backend nao passou na verificacao pelo socket.'
}

nginx_site() {
    local source=$1 snapshot target name
    local -a paths=(/etc/nginx/conf.d/vps-monitor-limits.conf /etc/nginx/snippets/vps-monitor-proxy.conf "$SITE_AVAILABLE" "$SITE_ENABLED")
    snapshot=$(mktemp -d "$BACKUP/nginx-transaction.XXXXXXXX")
    for target in "${paths[@]}"; do
        name=${target//\//_}
        if [[ -e $target || -L $target ]]; then cp -aP "$target" "$snapshot/$name"; fi
    done
    install -d -m 755 /etc/nginx/snippets /var/www/vps-monitor-acme
    if install -m 644 "$APP/deploy/nginx/limits.conf" "${paths[0]}" &&
        install -m 644 "$APP/deploy/nginx/proxy.conf" "${paths[1]}" &&
        install -m 644 "$source" "${paths[2]}" &&
        { [[ -L ${paths[3]} && $(readlink "${paths[3]}") == "${paths[2]}" ]] || ln -s "${paths[2]}" "${paths[3]}"; } &&
        nginx -t && systemctl reload nginx; then
        return
    fi
    # Restore only this application's four paths; other sites are untouched.
    for target in "${paths[@]}"; do
        name=${target//\//_}
        rm -f -- "$target"
        if [[ -e $snapshot/$name || -L $snapshot/$name ]]; then cp -aP "$snapshot/$name" "$target"; fi
    done
    nginx -t && systemctl reload nginx || true
    die 'Configuracao Nginx recusada; arquivos desta aplicacao foram restaurados.'
}

https() {
    say 'Configurando dominio e certificado HTTPS'
    "$APP/.venv/bin/python" "$APP/deploy/render_nginx.py" --domain "$DOMAIN" --output "$BACKUP/rendered-nginx"
    if [[ -s /etc/letsencrypt/live/$DOMAIN/fullchain.pem && -s /etc/letsencrypt/live/$DOMAIN/privkey.pem ]]; then
        nginx_site "$BACKUP/rendered-nginx/site.conf"
    else
        nginx_site "$BACKUP/rendered-nginx/bootstrap.conf"
    fi
    certbot certonly --webroot -w /var/www/vps-monitor-acme -d "$DOMAIN" --cert-name "$DOMAIN" --keep-until-expiring
    nginx_site "$BACKUP/rendered-nginx/site.conf"
    install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
    printf '#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/vps-monitor-reload-nginx
    chmod 755 /etc/letsencrypt/renewal-hooks/deploy/vps-monitor-reload-nginx
    systemctl enable --now certbot.timer
    certbot renew --cert-name "$DOMAIN" --dry-run
    [[ $(curl -s -o /dev/null -w '%{http_code}' --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/") == 200 ]] || die 'A pagina HTTPS nao passou na verificacao.'
    [[ $(curl -s -o /dev/null -w '%{http_code}' --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/api/vps") == 401 ]] || die 'A API deve exigir login.'
    [[ $(curl -s -o /dev/null -w '%{http_code}' --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/.env") == 404 ]] || die 'A verificacao de arquivos privados falhou.'
}

main() {
    trap failed ERR
    cd /
    say 'Verificando compatibilidade e instalacoes existentes'
    preflight
    configure_dns
    prepare
    database
    environment
    https
    say "Deploy concluido: https://$DOMAIN"
    printf 'Backups privados: %s\nSegredos: %s/vps-monitor.env (root, 600)\n' "$BACKUP" "$CONFIG"
    printf 'Crie sua conta no painel. O banco de producao e novo; dados locais nao foram importados.\n'
    if [[ -r /etc/ssh/ssh_host_ed25519_key.pub ]]; then
        printf '\nIdentidade SSH desta VPS (para o cadastro no monitor):\n'
        ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256 || true
    fi
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
