# VPS Monitor

Monitor de VPS Linux com cadastro, login e painel individual. Contas e servidores ficam salvos no banco configurado por `DATABASE_URL`. Cada usuário só pode consultar, monitorar, diagnosticar e remover as próprias VPS.

## Requisitos

- Python 3.10+
- Node.js 20.19+ ou 22.12+
- PostgreSQL acessível pelo backend
- VPS com IP público e SSH habilitado

## Início rápido no Windows

1. Configure `DATABASE_URL` em `back-end/.env.example` ou diretamente em `back-end/.env`.
2. Execute `start.bat` na raiz do projeto.
3. Acesse `http://localhost:5173`, crie sua conta e adicione suas VPS.

O script reutiliza o ambiente Python em `back-end/.venv` ou `back-end/venv`, instala as dependências, cria `back-end/.env` a partir do exemplo quando necessário e gera as chaves de sessão e criptografia que estiverem vazias. Depois inicia backend e frontend em duas janelas e abre o painel no navegador. Valores já configurados são preservados. Na primeira inicialização, o backend cria as tabelas `users` e `vps_servers` no banco; o usuário do banco precisa dessa permissão.

## Configuração manual

No diretório `back-end`:

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python configure.py
venv\Scripts\python app.py
```

Confira o `DATABASE_URL` no `.env` antes de iniciar. Exemplo de formato: `postgresql://usuario:senha@host:5432/banco?sslmode=require`. Parâmetros de conexão, incluindo SSL, são preservados. Para desenvolvimento local também é aceito `sqlite:///vps-monitor.sqlite3`.

Em outro terminal, no diretório `front-end`:

```powershell
npm.cmd ci
npm.cmd run dev
```

O frontend usa `/api` pelo proxy do Vite para o backend na porta 5000, mantendo cookies e API na mesma origem do navegador.

### Variáveis do backend

| Variável | Uso |
| --- | --- |
| `DATABASE_URL` | Conexão PostgreSQL (ou SQLite para desenvolvimento/testes). |
| `SECRET_KEY` | Chave aleatória de pelo menos 32 caracteres para assinar sessões. Gerada pelo configurador quando vazia. |
| `VPS_ENCRYPTION_KEY` | Chave Fernet para criptografar senhas e chaves SSH no banco. Gerada pelo configurador quando vazia. |
| `SESSION_COOKIE_SECURE` | `false` para HTTP local; use `true` ao publicar com HTTPS. |
| `FLASK_DEBUG` | `false` por padrão. Habilite apenas durante desenvolvimento local. |
| `PORT` | Porta do backend, padrão `5000`. |

Mantenha as mesmas `SECRET_KEY` e `VPS_ENCRYPTION_KEY` entre reinícios e réplicas. Guarde uma cópia segura da chave de criptografia junto ao backup do banco: perdê-la impede recuperar as credenciais SSH salvas. O arquivo `.env` fica fora do Git. Em hospedagens que injetam variáveis de ambiente, configure as três variáveis obrigatórias diretamente e dispense `configure.py`.

## Uso

1. Escolha **Criar conta** e preencha nome, e-mail e senha de pelo menos 8 caracteres.
2. No painel, clique em **+ ADICIONAR VPS**.
3. Informe nome, IP público IPv4/IPv6, porta SSH, localização e usuário SSH.
4. Preencha a senha SSH ou cole o conteúdo completo da chave privada, incluindo `BEGIN` e `END`. Chaves protegidas aceitam uma senha da chave. Se os dois métodos forem preenchidos, a chave tem preferência.
5. Salve. O card da VPS aparece imediatamente com o estado **Conectando** e um indicador de carregamento durante a primeira tentativa SSH. Ao terminar, ele mostra as métricas ou o estado offline com a mensagem de erro. As métricas são atualizadas a cada 30 segundos após a consulta anterior. Uma VPS offline continua salva na conta.
6. Para remover, selecione a VPS e clique em **REMOVER SERVIDOR**.

São aceitas chaves Ed25519, RSA e ECDSA. O caminho de um arquivo no computador do usuário não é usado: envie o conteúdo da chave. A VPS precisa dos comandos Linux usados na coleta (`awk`, `free`, `df`, `uptime`, `ps`, `grep`, `sed` e `cat`). A coleta não exige senha sudo.

O antigo `servers.json` deixou de ser utilizado. Caso exista, cadastre as VPS novamente dentro da conta do respectivo dono.

## API e isolamento

| Método | Rota | Uso |
| --- | --- | --- |
| GET | `/api/auth/me` | Consulta a sessão e obtém o token CSRF; `user` é `null` sem login. |
| POST | `/api/auth/register` | Cadastra e autentica uma conta. |
| POST | `/api/auth/login` | Autentica por e-mail e senha. |
| POST | `/api/auth/logout` | Encerra a sessão no navegador. |
| GET | `/api/vps` | Coleta métricas somente das VPS da conta autenticada. |
| POST | `/api/vps` | Salva uma VPS vinculada à conta autenticada. |
| DELETE | `/api/vps/<id>` | Remove uma VPS própria; retorna 404 para IDs inexistentes ou de outro usuário. |
| GET | `/api/vps/debug-ssh` | Diagnostica somente as conexões da própria conta. |

Todas as operações de escrita exigem o cabeçalho `X-CSRF-Token` obtido em `/api/auth/me`. Cadastro e login renovam esse token. Sessões usam cookies `HttpOnly` e `SameSite=Lax` com duração de sete dias. Senhas de conta têm hash scrypt; credenciais SSH ficam criptografadas no banco e não são devolvidas pela API. O dono da VPS vem da sessão, independentemente de IDs enviados pelo cliente. Conexões SSH não usam chaves locais ou o agente SSH do backend. Endereços privados e locais são recusados no cadastro.

## Build e hospedagem

O roteiro completo para **Ubuntu 24.04, Nginx existente e vps-monitor.net** está em [deploy/ubuntu24.md](deploy/ubuntu24.md). Inclui pacote sem segredos, Gunicorn por socket Unix, unit systemd com privilégios reduzidos, limites do Nginx, HTTPS/renovação, permissões do banco e validação da identidade SSH.

Execute `npm.cmd run build` em `front-end` e `python deploy/build_package.py` na raiz para gerar `.artifacts/vps-monitor-release.tar.gz`. O backend serve `front-end/dist`; Node/Vite não são necessários no servidor. Os modelos ficam em `deploy/` e o lock com versões e hashes para Ubuntu x86-64/Python 3.12 em `back-end/requirements-production.lock`.

Com `APP_ENV=production`, o backend exige cookies seguros, domínios confiáveis, debug desabilitado e fingerprint SSH no cadastro. O banco é inicializado explicitamente por `flask --app app init-db`; o serviço não cria tabelas automaticamente. A quota padrão é de 10 VPS por conta. Configure `SSH_ALLOWED_PORTS` com as portas autorizadas. A fingerprint é salva com as credenciais criptografadas, sem alteração no schema das tabelas existentes.

Se reutilizar o banco local, mantenha a `VPS_ENCRYPTION_KEY` já utilizada. VPS antigas sem fingerprint precisam ser cadastradas com sua identidade confirmada para coletar métricas em produção. O `.env.example` contém apenas placeholders; conexões reais pertencem ao `.env` ignorado pelo Git ou ao arquivo protegido de ambiente no servidor.

## Validação

No diretório `back-end`, com as dependências instaladas:

```powershell
python -m unittest discover -s tests -v
```

Os testes usam SQLite temporário e SSH simulado. Cobrem cadastro, login, sessão, CSRF, separação de contas, exclusão, diagnóstico, persistência após reinício e proteção das credenciais. Não acessam suas VPS nem o PostgreSQL configurado no `.env`.

No diretório `front-end`:

```powershell
npm.cmd run lint
npm.cmd run build
```
