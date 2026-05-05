# VPS Monitor

Um monitor de servidores Linux (VPS) stateless e em tempo real. Para acompanhar CPU, RAM, Disco, Rede e Uptime de múltiplos servidores em uma única dashboard.

## Requisitos

Antes de começar, você precisará ter instalado:
- [Python 3.10+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/)

## Início Rápido (Windows)

1. **Baixe o projeto** e extraia em uma pasta.
2. **Clique duas vezes** no arquivo `start.bat` na raiz do projeto.
   - O script irá instalar todas as dependências do Backend e Frontend automaticamente.
   - Ele abrirá a Dashboard no seu navegador padrão.

## Configuração da VPS

O monitor se conecta via SSH. Para que ele funcione, sua VPS deve:
- Ter o serviço SSH ativo.
- Permitir login via Usuário/Senha ou Chave SSH (Ed25519/RSA).
- Ter os comandos básicos instalados (`free`, `df`, `awk`, `grep`).

## Como usar

1. Com o projeto rodando, clique em **+ ADICIONAR VPS**.
2. Preencha os dados:
   - **IP:** O endereço da sua VPS.
   - **SSH Key:** Caminho completo para sua chave privada (ex: `C:\Users\Nome\.ssh\id_ed25519`).
   - **Senha:** Se não usar chave, preencha o campo de senha.
3. Clique em **SALVAR** e aguarde a coleta dos dados.

## Estrutura do Projeto

- `/back-end`: API Flask em Python (coleta métricas via Paramiko/SSH).
- `/front-end`: Dashboard React + Vite (UI ultra-responsiva).
- `servers.json`: Onde seus servidores ficam salvos localmente.
