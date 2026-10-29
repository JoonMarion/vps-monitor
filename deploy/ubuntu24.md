# Deploy seguro em Ubuntu 24.04 com Nginx existente

Destino informado: **vps-monitor.net**, VPS **89.117.75.166**. Este roteiro adiciona um serviço próprio ao Nginx instalado no host. Se o Nginx for gerenciado por Docker, Coolify ou outro painel, integre pelo painel: os caminhos e o socket deste roteiro precisam ser adaptados.

Fluxo: navegador → HTTPS/Nginx → socket Unix → Gunicorn/Flask → PostgreSQL e SSH. O frontend já compilado é servido pela aplicação. Node, Vite e o servidor Flask de desenvolvimento não rodam em produção.

## 1. Antes de publicar

- Aponte o registro DNS **A de `vps-monitor.net` para `89.117.75.166`**. Só configure AAAA se o IPv6 da VPS estiver correto. Este pacote não configura `www`.
- O `.env.example` anterior continha uma conexão real de banco. Troque a senha desse acesso se o arquivo foi versionado/compartilhado; substituí-lo não apaga o histórico. Atualize o `.env` local depois da troca. Use um usuário de banco exclusivo para a aplicação.
- Se reutilizar o banco já utilizado localmente, preserve a **VPS_ENCRYPTION_KEY atual**. Gerar outra impede abrir as credenciais SSH existentes. A SECRET_KEY pode ser nova; isso encerra sessões antigas.
- Faça backup do banco e da configuração Nginx. Guarde o backup de credenciais/chaves fora da pasta pública, criptografado e com acesso restrito.
- Use uma conta administrativa com sudo e autenticação SSH por chave para o deploy. O usuário do serviço será separado, sem sudo e sem login interativo.

No computador local, dentro da pasta do projeto:

```powershell
cd front-end
npm.cmd ci
npm.cmd run lint
npm.cmd run build
cd ..
.\back-end\.venv\Scripts\python.exe deploy\build_package.py
scp .artifacts/vps-monitor-release.tar.gz .artifacts/vps-monitor-release.tar.gz.sha256 SEU_USUARIO_ADMIN@89.117.75.166:~/
```

O empacotador inclui apenas os arquivos autorizados, o build e os modelos de produção. `.env`, `.git`, arquivos de chaves, ambientes Python e `servers.json` ficam fora do pacote. Não copie o `.env` inteiro para uma pasta servida pelo Nginx.

## 2. Verificar a VPS e preparar a instalação

Entre por SSH, verificando a identidade da VPS pelo console do provedor antes de aceitar uma chave nova:

```bash
ssh SEU_USUARIO_ADMIN@89.117.75.166
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo ss -lntup
sudo ufw status verbose
sudo nginx -T 2>/dev/null | grep -E '^[[:space:]]*user |server_name.*vps-monitor\.net'
```

O serviço fornecido usa o grupo `www-data`, padrão do Nginx no Ubuntu. Se o worker do seu Nginx usar outro grupo, ajuste `Group=` no unit antes de instalar. Se `vps-monitor.net` já estiver configurado, revise esse site antes de criar outro com o mesmo nome.

Instale os componentes que faltarem. A instalação ou atualização de pacotes numa VPS compartilhada deve ocorrer em uma janela de manutenção:

```bash
sudo apt update
sudo apt install --no-install-recommends python3-venv certbot ca-certificates
sudo tar -czf /root/nginx-before-vps-monitor.tar.gz -C /etc nginx
sudo chmod 600 /root/nginx-before-vps-monitor.tar.gz
sha256sum -c ~/vps-monitor-release.tar.gz.sha256
```

Verifique se já existe uma instalação antes de usar `/opt/vps-monitor`. Para a primeira instalação:

```bash
sudo useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin vps-monitor
sudo install -d -o root -g root -m 755 /opt/vps-monitor
sudo tar -xzf ~/vps-monitor-release.tar.gz --no-same-owner -C /opt/vps-monitor
sudo python3 -m venv /opt/vps-monitor/.venv
sudo /opt/vps-monitor/.venv/bin/python -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r /opt/vps-monitor/back-end/requirements-production.lock
```

O lock fornecido é destinado a **Ubuntu 24.04 x86-64 / Python 3.12**. Confira `uname -m` e `python3 --version`; para ARM ou outra versão de Python, gere e audite um lock compatível. O código e o ambiente devem continuar pertencendo a root, legíveis e sem permissão de escrita para `vps-monitor`. As dependências foram atualizadas após a auditoria; a versão nova do Paramiko exige algoritmos SSH modernos, incluindo SHA-2 para assinaturas RSA.

## 3. Configurar o banco e os segredos

Use um banco dedicado. Para banco remoto, habilite verificação TLS de identidade, usando a CA indicada pelo provedor. Exemplo de formato:

```text
DATABASE_URL='postgresql://vps_monitor_app:SENHA_URL_ENCODED@HOST_DO_BANCO:5432/vps_monitor?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
```

`verify-full` verifica a cadeia de certificados e o hostname. Caso o provedor use uma CA própria, instale a CA pública correta e ajuste `sslrootcert`. Não desative a verificação para contornar um erro de certificado. No firewall do provedor do banco, restrinja o acesso ao IP de saída da VPS. A porta do banco não precisa ser aberta ao público nesta VPS.

Crie o arquivo protegido:

```bash
sudo install -d -o root -g root -m 700 /etc/vps-monitor
sudo install -o root -g root -m 600 /opt/vps-monitor/deploy/.env.production.example /etc/vps-monitor/vps-monitor.env
sudoedit /etc/vps-monitor/vps-monitor.env
```

Preencha DATABASE_URL, SECRET_KEY e VPS_ENCRYPTION_KEY. Mantenha os valores de produção do modelo, inclusive `APP_ENV=production`, `FLASK_DEBUG=false`, `SESSION_COOKIE_SECURE=true`, `BEHIND_PROXY=true`, `TRUSTED_HOSTS=vps-monitor.net` e `AUTO_CREATE_TABLES=false`. Coloque a URL entre aspas simples para que o arquivo também possa ser carregado no shell administrativo abaixo.

Para gerar uma SECRET_KEY, execute no terminal privado e transfira o resultado para o arquivo protegido:

```bash
openssl rand -hex 32
```

**Somente para um banco novo**, gere uma VPS_ENCRYPTION_KEY:

```bash
/opt/vps-monitor/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

**Para o banco que já contém VPS salvas, copie a VPS_ENCRYPTION_KEY existente do `.env` local pelo canal seguro, preservando seu valor.** Guarde uma cópia criptografada dessa chave separada do backup do banco. Nunca envie os valores em mensagens, tickets ou commits.

Se as tabelas já existem, não é necessário recriá-las. Para banco novo, inicialize explicitamente com uma credencial proprietária/de migração, informada sem aparecer no histórico do shell:

```bash
sudo -i
set -a
. /etc/vps-monitor/vps-monitor.env
set +a
read -r -s -p 'URL do banco com permissão de criar tabelas: ' DATABASE_URL
printf '\n'
export DATABASE_URL
cd /opt/vps-monitor/back-end
/opt/vps-monitor/.venv/bin/flask --app app init-db
unset DATABASE_URL
exit
```

O usuário permanente do `DATABASE_URL` deve ter apenas conexão, uso do schema e SELECT/INSERT/UPDATE/DELETE nas tabelas `users` e `vps_servers`. Não use a conta proprietária, superuser ou com permissão de criar bancos. No console administrativo do banco, adapte estes grants ao banco dedicado e à role já criada pelo provedor:

```sql
GRANT CONNECT ON DATABASE vps_monitor TO vps_monitor_app;
GRANT USAGE ON SCHEMA public TO vps_monitor_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users, public.vps_servers TO vps_monitor_app;
```

Não aplique mudanças globais de permissões em bancos dos outros sistemas. Como os IDs são UUIDs gerados pela aplicação, estas tabelas não exigem sequências.

## 4. Iniciar apenas o serviço do monitor

```bash
sudo install -o root -g root -m 644 /opt/vps-monitor/deploy/vps-monitor.service /etc/systemd/system/vps-monitor.service
sudo systemd-analyze verify /etc/systemd/system/vps-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now vps-monitor
sudo systemctl status vps-monitor --no-pager
sudo journalctl -u vps-monitor -n 60 --no-pager
```

O processo roda como `vps-monitor`, sem privilégios administrativos; o Nginx acessa o socket pelo grupo `www-data`. O unit restringe escrita no sistema, acesso às pastas pessoais, capacidades, memória e quantidade de tarefas. Não permite que a aplicação edite o próprio código. A memória inicial fica limitada a 1 GiB para proteger os outros serviços; ajuste somente depois de observar o consumo.

Teste pelo socket, usando o hostname aceito pela aplicação:

```bash
sudo -u www-data curl --unix-socket /run/vps-monitor/gunicorn.sock -H 'Host: vps-monitor.net' -H 'X-Forwarded-Proto: https' -o /dev/null -w '%{http_code}\n' http://localhost/api/auth/me
```

O resultado esperado é **200**. A aplicação não abre porta TCP; 5000, 5055 e 5173 não precisam de regras de entrada.

## 5. Acrescentar o domínio ao Nginx e emitir HTTPS

Mantenha os arquivos dos outros sites. Primeiro instale os snippets específicos desta aplicação:

```bash
sudo install -d -o root -g root -m 755 /var/www/vps-monitor-acme /etc/nginx/snippets
sudo install -o root -g root -m 644 /opt/vps-monitor/deploy/nginx/limits.conf /etc/nginx/conf.d/vps-monitor-limits.conf
sudo install -o root -g root -m 644 /opt/vps-monitor/deploy/nginx/proxy.conf /etc/nginx/snippets/vps-monitor-proxy.conf
sudo install -o root -g root -m 644 /opt/vps-monitor/deploy/nginx/bootstrap.conf /etc/nginx/sites-available/vps-monitor.net
sudo ln -s /etc/nginx/sites-available/vps-monitor.net /etc/nginx/sites-enabled/vps-monitor.net
sudo nginx -t && sudo systemctl reload nginx
```

A configuração temporária serve apenas o desafio de certificado; a aplicação ainda não recebe credenciais por HTTP. Com o DNS propagado e a porta 80 alcançável:

```bash
sudo certbot certonly --webroot -w /var/www/vps-monitor-acme -d vps-monitor.net
```

O comando solicitará seu e-mail e a aceitação dos termos. Se já existir um certificado válido para esse domínio, confira o caminho antes de emitir outro. O arquivo final usa `/etc/letsencrypt/live/vps-monitor.net/`; adapte-o se o nome do certificado existente for diferente.

Ative o site HTTPS somente depois da emissão:

```bash
sudo install -o root -g root -m 644 /opt/vps-monitor/deploy/nginx/site.conf /etc/nginx/sites-available/vps-monitor.net
sudo nginx -t && sudo systemctl reload nginx
```

O virtual host limita tentativas de login/cadastro, frequência da coleta e conexões simultâneas. Os limites por IP são uma defesa inicial; ajuste-os se houver muitos usuários legítimos atrás do mesmo IP. Nginx devolve 429 em JSON quando necessário. A rota de diagnóstico SSH fica indisponível pela Internet.

Habilite a renovação e recarregue o Nginx após certificados renovados:

```bash
sudo install -d -o root -g root -m 755 /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\n/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx\n' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/vps-monitor-reload-nginx >/dev/null
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/vps-monitor-reload-nginx
sudo systemctl enable --now certbot.timer
sudo certbot renew --cert-name vps-monitor.net --dry-run
```

Use o nome real mostrado por `sudo certbot certificates` caso seja diferente. Verifique se já existe renovação centralizada para os demais sites e integre o hook ao mecanismo atual. `reload` aplica a configuração validada sem parar os sites.

## 6. Confirmar cada VPS antes de enviar credenciais

Em produção, cada VPS cadastrada exige a fingerprint SHA256 da chave de host SSH. A verificação acontece antes da autenticação e recusa outra identidade, em vez de aceitar automaticamente qualquer servidor que responder pelo IP.

No **console do provedor da VPS monitorada**, confira a chave oferecida pelo servidor, normalmente Ed25519:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Cole apenas a parte `SHA256:...` em **Identidade SSH da VPS** no formulário. Se o servidor usar outra chave de host, confirme a fingerprint desse tipo correspondente pelo console confiável. Uma fingerprint obtida apenas por `ssh-keyscan` na mesma conexão que você está tentando validar não comprova a identidade.

VPS antigas sem fingerprint continuam no banco, mas a coleta em produção será recusada. Anote seus dados e cadastre-as com a identidade confirmada antes de remover o cadastro anterior. O limite inicial é de 10 VPS por conta; se estiver no limite, faça essa substituição com cuidado ou ajuste temporariamente a quota pelo ambiente administrativo.

Use, em cada VPS monitorada, uma conta dedicada `monitor`, sem sudo, e uma chave exclusiva para o monitor. Os comandos de coleta não precisam de root. No `authorized_keys` dessa conta, considere a opção `restrict` e `from="89.117.75.166"` quando esse for o IP de saída confirmado do serviço. Não reutilize sua chave administrativa.

O arquivo de produção permite inicialmente apenas a porta SSH 22. Se alguma VPS usar outra porta, adicione-a explicitamente a `SSH_ALLOWED_PORTS`, por exemplo `22,2222`, e reinicie somente o serviço `vps-monitor`. Endereços locais e privados são recusados pela API.

## 7. Verificar a publicação e preservar os outros sistemas

```bash
curl -I http://vps-monitor.net
curl -I https://vps-monitor.net
curl -i https://vps-monitor.net/api/vps
curl -I https://vps-monitor.net/.env
sudo ss -lntup
sudo systemctl status vps-monitor --no-pager
sudo systemd-analyze security vps-monitor.service
```

Resultados esperados: redirecionamento HTTP para HTTPS, certificado confiável, API de VPS sem sessão retornando 401, `.env` retornando 404 e ausência de novas portas TCP da aplicação. Pelo navegador, confira o cookie `__Host-vps_monitor_session` com Secure, HttpOnly, SameSite=Lax e Path=/; teste duas contas e confirme o isolamento. O Nginx publica CSP, HSTS e demais headers.

Teste também os sites já hospedados após o reload. Se houver falha na nova configuração, desative somente o link `/etc/nginx/sites-enabled/vps-monitor.net` e valide/recarregue o Nginx; preserve os arquivos dos outros sites. Desabilite o serviço `vps-monitor` para uma reversão completa da nova aplicação. Não restaure todo o backup de Nginx sobre mudanças posteriores sem revisá-las.

No firewall existente, revise regras e mantenha as portas necessárias aos sistemas atuais. Para este aplicativo, apenas 80/443 e o SSH administrativo precisam estar acessíveis. Não execute `ufw reset`, nem habilite uma política global nova sem inventariar as portas existentes e testar acesso ao console do provedor. Nunca desative login por senha/root antes de testar uma segunda sessão administrativa com chave; essa alteração afeta todos os administradores da VPS.

Agende atualizações de segurança e backups criptografados fora da VPS; teste restauração do banco **e** da chave Fernet. Faça uma avaliação de carga antes de liberar o cadastro em escala: os limites fornecidos são iniciais e não substituem monitoramento de abuso, disponibilidade e recursos.

## Atualizações

Gere um pacote novo e mantenha o anterior para rollback. Extraia em uma área de preparação root e revise antes de substituir `/opt/vps-monitor`; não sobrescreva `/etc/vps-monitor/vps-monitor.env`. Atualize as dependências pelo lock com hashes, execute eventuais migrações com a role apropriada e reinicie apenas `vps-monitor`. Mudanças no Nginx exigem `nginx -t` antes de `reload`. Preserve a chave de criptografia em todas as versões.

## Referências oficiais

- [Gunicorn e systemd](https://gunicorn.org/deploy/)
- [Flask atrás de proxy](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/)
- [Limites de requisições do Nginx](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)
- [Certbot: webroot e renovação](https://eff-certbot.readthedocs.io/en/stable/using.html)
- [PostgreSQL: verificação TLS](https://www.postgresql.org/docs/current/libpq-ssl.html)
- [Paramiko: políticas de chave do servidor](https://docs.paramiko.org/en/stable/api/client.html)
- [Ubuntu: OpenSSH](https://documentation.ubuntu.com/server/how-to/security/openssh-server/)
