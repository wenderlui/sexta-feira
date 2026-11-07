# Inicia o servidor da Sexta-feira no Windows.
# Uso: clique com o botão direito > "Executar com o PowerShell", ou agende no Agendador de Tarefas.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente Python (.venv)..."
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
}

# Instala ou atualiza as dependências (rápido quando já estão instaladas).
$req = if (Test-Path "requirements-voz.txt") { "requirements-voz.txt" } else { "requirements.txt" }
.\.venv\Scripts\python.exe -m pip install -q -r $req

# Só escuta no próprio PC; o Tailscale publica em HTTPS para os seus aparelhos.
# O registro fica em logs\servidor.log (útil quando roda escondido pela Tarefa Agendada).
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
# O uvicorn escreve o registro no stderr; no PowerShell 5.1 com "Stop" isso abortaria o script,
# então o redirecionamento fica a cargo do cmd.
$ErrorActionPreference = "Continue"
cmd /c ".venv\Scripts\python.exe -m uvicorn sexta.app:app --app-dir server --host 127.0.0.1 --port 8000 >> logs\servidor.log 2>&1"
