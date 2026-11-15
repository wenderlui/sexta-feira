# Instala o programa da Sexta-feira no PC: dependências, ícone e atalho na Área de Trabalho
# e no Menu Iniciar. Uso: botão direito > "Executar com o PowerShell".
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente Python (.venv)..."
    py -3 -m venv .venv
}
Write-Host "Instalando dependências do programa..."
.\.venv\Scripts\python.exe -m pip install -q --upgrade pip
.\.venv\Scripts\python.exe -m pip install -q -r requirements-desktop.txt

# Ícone .ico a partir do ícone do app
$ico = Join-Path $raiz "desktop\sexta.ico"
.\.venv\Scripts\python.exe -c "from PIL import Image; Image.open(r'web\icons\icon-512.png').save(r'$ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

# Atalhos (sem console: pythonw.exe)
$alvo = Join-Path $raiz ".venv\Scripts\pythonw.exe"
$script = Join-Path $raiz "desktop\sexta_desktop.py"
$shell = New-Object -ComObject WScript.Shell
foreach ($pasta in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $lnk = $shell.CreateShortcut((Join-Path $pasta "Sexta-feira.lnk"))
    $lnk.TargetPath = $alvo
    $lnk.Arguments = "`"$script`""
    $lnk.WorkingDirectory = $raiz
    $lnk.IconLocation = $ico
    $lnk.Description = "Sexta-feira - IA local"
    $lnk.Save()
}
Write-Host ""
Write-Host "Pronto! Abra pelo atalho 'Sexta-feira' na Área de Trabalho ou no Menu Iniciar."
Write-Host "Para abrir junto com o Windows: Ajustes > 'Abrir com o Windows' dentro do programa."
