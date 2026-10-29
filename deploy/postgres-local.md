# Banco dedicado no PostgreSQL que já existe na VPS

Use este complemento à etapa 3 de `ubuntu24.md` quando PostgreSQL e Nginx estão instalados diretamente no Ubuntu. O serviço da aplicação usa o usuário Linux `vps-monitor`; a autenticação peer identifica esse usuário pelo kernel através do socket local. A aplicação não precisa de uma senha de PostgreSQL.

O banco do computador usa `localhost` e é outra instância. Estes comandos criam uma **produção vazia**. As contas e VPS locais não são transferidas automaticamente. Preserve o banco local e seu backup; uma transferência posterior deve considerar a versão de PostgreSQL e preservar a VPS_ENCRYPTION_KEY usada nos registros importados. O computador local usa PostgreSQL 17, portanto não presuma que um dump completo será restaurável em uma versão anterior.

## Verificações iniciais

```bash
sudo -u postgres psql -d postgres -c 'SELECT version();'
sudo -u postgres psql -d postgres -c 'SHOW unix_socket_directories;'
```

O socket usado abaixo é `/var/run/postgresql`, padrão no Ubuntu. Se o PostgreSQL estiver em Docker, tiver autenticação administrativa diferente, usar outra porta/cluster ou outro diretório de sockets, adapte o procedimento antes de executá-lo. Não reinstale ou substitua a instância existente.

Primeiro prepare a aplicação e o usuário Linux conforme a etapa 2 do guia principal. Crie as roles e o novo banco:

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres <<'SQL'
CREATE ROLE vps_monitor_owner NOLOGIN;
CREATE ROLE "vps-monitor" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL;
CREATE DATABASE vps_monitor OWNER vps_monitor_owner;
REVOKE ALL ON DATABASE vps_monitor FROM PUBLIC;
GRANT CONNECT ON DATABASE vps_monitor TO "vps-monitor";
SQL
```

Se alguma role ou o banco já existir, o comando interrompe com erro. Revise a instalação existente; não use DROP para repetir o roteiro.

Restrinja apenas o schema do novo banco:

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -d vps_monitor <<'SQL'
ALTER SCHEMA public OWNER TO vps_monitor_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO "vps-monitor";
SQL
```

## Autenticação exclusiva por socket

Confira as regras existentes. Se já houver uma regra `local all all peer` que atenda a esta conexão, não é necessário mudar o arquivo. Caso contrário, acrescente a regra específica a seguir **antes de regras locais genéricas**, preservando todas as demais linhas:

```bash
VPS_MONITOR_HBA=$(sudo -u postgres psql -d postgres -Atqc 'SHOW hba_file')
sudo cp --no-clobber --preserve=mode,ownership "$VPS_MONITOR_HBA" "${VPS_MONITOR_HBA}.before-vps-monitor"
sudoedit "$VPS_MONITOR_HBA"
```

Linha a acrescentar:

```text
local   vps_monitor   "vps-monitor"   peer
```

Valide o arquivo:

```bash
sudo -u postgres psql -d postgres -c 'SELECT line_number, error FROM pg_hba_file_rules WHERE error IS NOT NULL;'
```

O resultado deve ser **zero linhas**. Se houver erros, corrija-os antes de prosseguir. Depois, recarregue a configuração:

```bash
sudo -u postgres psql -d postgres -c 'SELECT pg_reload_conf();'
```

Não é necessário reiniciar o PostgreSQL nem mudar `listen_addresses` ou as regras dos outros usuários. A role da aplicação tem senha nula e a regra acima se aplica apenas ao novo banco e ao usuário indicado.

## Inicializar o schema com a role proprietária

Depois de instalar o pacote e as dependências em `/opt/vps-monitor`:

```bash
sudo -u postgres /opt/vps-monitor/.venv/bin/python /opt/vps-monitor/deploy/init_local_postgres.py
sudo -u postgres psql -v ON_ERROR_STOP=1 -d vps_monitor <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users, public.vps_servers TO "vps-monitor";
SQL
```

O inicializador importa os modelos da aplicação e cria as tabelas dentro de uma transação sob `vps_monitor_owner`. O usuário permanente não recebe CREATE, ALTER, DROP ou associação à role proprietária.

Teste com o mesmo usuário Linux utilizado no unit systemd:

```bash
sudo -u vps-monitor psql -h /var/run/postgresql -U vps-monitor -d vps_monitor -c 'SELECT current_user, current_database();'
```

Esperado: usuário `vps-monitor`, banco `vps_monitor`, sem pedido de senha.

## Ambiente da aplicação

No arquivo protegido `/etc/vps-monitor/vps-monitor.env`, use:

```text
DATABASE_URL='postgresql://vps-monitor@/vps_monitor?host=/var/run/postgresql'
```

Mantenha `APP_ENV=production`, `AUTO_CREATE_TABLES=false`, os cookies seguros e os demais valores do modelo. Para um banco novo independente, gere chaves novas. Se for importar as VPS do computador, preserve a chave Fernet original para esses registros antes de começar a cadastrar dados com outra chave.

Continue a partir da etapa 4 de `ubuntu24.md`: systemd, Nginx, HTTPS e validações. Não altere a porta pública do banco ou o firewall dos outros sistemas como parte deste procedimento.

Referências: [autenticação peer](https://www.postgresql.org/docs/current/auth-peer.html), [regras de autenticação e validação](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html).
