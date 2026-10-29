# Deploy em três ações

Este fluxo usa Ubuntu 24.04 x86-64/Python 3.12, Nginx como www-data e PostgreSQL instalados diretamente no host. A instância PostgreSQL deve aceitar administração local como usuário Linux postgres em /var/run/postgresql:5432. Para Docker, painéis ou configurações diferentes, use os roteiros detalhados e adapte a integração.

É uma primeira instalação com banco de produção vazio. Os dados do computador não são importados. O instalador gera novas chaves privadas para a aplicação; se a intenção for migrar as VPS locais, planeje a preservação da chave Fernet antes de importar dados.

1. Reserve **vps-monitor.freemyip.com** no FreeMyIP e guarde a URL de atualização em um gerenciador de senhas. O token real será solicitado diretamente no terminal da VPS, com entrada oculta, se o DNS ainda não apontar para **89.117.75.166**. O pacote não contém o token.

2. No PowerShell, na raiz do projeto, substitua SEU_USUARIO_ADMIN pelo usuário com acesso SSH e sudo:

```powershell
scp .artifacts/vps-monitor-release.tar.gz .artifacts/vps-monitor-release.tar.gz.sha256 SEU_USUARIO_ADMIN@89.117.75.166:~/
ssh SEU_USUARIO_ADMIN@89.117.75.166
```

3. No terminal da VPS, execute o bloco completo:

```bash
cd ~ &&
sha256sum -c vps-monitor-release.tar.gz.sha256 &&
VPS_MONITOR_STAGE=$(sudo mktemp -d /root/vps-monitor-installer.XXXXXXXX) &&
sudo tar -xzf "$PWD/vps-monitor-release.tar.gz" --no-same-owner -C "$VPS_MONITOR_STAGE" &&
sudo bash "$VPS_MONITOR_STAGE/deploy/install.sh" --domain vps-monitor.freemyip.com
```

Quando solicitado, cole a URL real do FreeMyIP: ela ficará oculta. O instalador envia a requisição somente ao endpoint HTTPS do FreeMyIP e força `myip=89.117.75.166`, sem salvar o token em arquivo ou argumento de processo. Depois informe seu e-mail e aceite os termos do emissor quando o Certbot solicitar. Ao terminar, acesse **https://vps-monitor.freemyip.com** e crie sua conta. O instalador mostra a fingerprint SSH desta VPS para seu cadastro.

Para outro hostname, use o endereço completo com `--domain`. O instalador configura server_name, certificado, redirecionamento e TRUSTED_HOSTS para esse hostname. Para nomes FreeMyIP ainda sem o apontamento correto, ele pede a URL por entrada oculta e atualiza somente o nome escolhido. Para domínios próprios, como `vps-monitor.net`, o DNS deve estar configurado no provedor antes da execução. Os arquivos do site existente `meu-ponto.freemyip.com` pertencem ao outro sistema e são preservados.

O FreeMyIP exige ao menos uma atualização por ano, mesmo com IP fixo. Guarde a URL e renove o apontamento periodicamente. Para fazer apenas essa atualização na VPS, execute `sudo python3 /opt/vps-monitor/deploy/freemyip.py --domain vps-monitor.freemyip.com --ip 89.117.75.166`; a URL será pedida de forma oculta novamente. O instalador não agenda nem guarda essa credencial. [Documentação oficial](https://freemyip.com/help).

O instalador faz verificações de compatibilidade e DNS, checksum é conferido antes da extração, salva backups privados de Nginx/pg_hba.conf, cria usuário sem login/sudo e banco/roles exclusivos, instala dependências com hashes, preserva segredos em retomadas, configura uma única regra peer para o banco novo, inicia o serviço, adiciona somente os arquivos do domínio, valida/recarrega Nginx, emite HTTPS, testa renovação e verifica HTTPS/401/404. Ele não muda regras de firewall, não executa DROP e recusa assumir instalações preexistentes sem seu marcador de gerenciamento.

Se houver uma falha, leia o erro e corrija a condição indicada. A mesma execução pode ser retomada depois; as chaves existentes são preservadas. A instalação em um host real ainda deve ser verificada pelo operador. Confira também os outros sites depois do reload.

Para reconstruir o pacote depois de mudanças locais: gere o build do frontend e execute `python deploy/build_package.py`. O instalador está em `deploy/install.sh`; os procedimentos manuais continuam em `ubuntu24.md` e `postgres-local.md`.
