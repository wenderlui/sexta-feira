# Inicia o servidor da Sexta-feira no Windows.
# Uso: clique com o botão direito > "Executar com o PowerShell", ou agende no Agendador de Tarefas.
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente Python (.venv)..."
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

# Só escuta no próprio PC; o Tailscale publica em HTTPS para os seus aparelhos.
.\.venv\Scripts\python.exe -m uvicorn sexta.app:app --app-dir server --host 127.0.0.1 --port 8000
