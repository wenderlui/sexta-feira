"""Sexta-feira para o PC: janela própria com menus + ícone na bandeja do Windows.

- Usa o servidor que já roda (Tarefa Agendada) ou sobe um, se não houver.
- Sobe o Ollama se ele estiver fechado. Tudo local, nada na nuvem.
- Fechar a janela só a esconde: a Sexta-feira continua na bandeja, 24/7.
- Abrir o programa de novo apenas traz a janela já aberta para a frente.

Uso: .venv\\Scripts\\pythonw.exe desktop\\sexta_desktop.py   (ou o atalho criado por
scripts\\instalar-desktop.ps1)
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST, PORT = "127.0.0.1", 8000
BASE = f"http://{HOST}:{PORT}"
OLLAMA = "http://127.0.0.1:11434"
LOCK_PORT = 47821            # porta local que garante uma única janela aberta
APP_NAME = "Sexta-feira"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW


# ---------------------------------------------------------------- utilitários (testáveis)
def is_up(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (só localhost)
            return 200 <= r.status < 500
    except OSError:
        return False


def python_exe(root: Path = ROOT, windowless: bool = False) -> str:
    """Python do .venv do projeto (pythonw.exe para não abrir console)."""
    name = "pythonw.exe" if windowless else "python.exe"
    venv = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (name if os.name == "nt" else "python")
    return str(venv) if venv.exists() else sys.executable


def server_command(root: Path = ROOT) -> list[str]:
    return [python_exe(root), "-m", "uvicorn", "sexta.app:app", "--app-dir", str(root / "server"),
            "--host", HOST, "--port", str(PORT)]


def autostart_command(root: Path = ROOT) -> str:
    script = root / "desktop" / "sexta_desktop.py"
    return f'"{python_exe(root, windowless=True)}" "{script}" --bandeja'


def get_autostart() -> bool:
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Liga/desliga abrir com o Windows (só para o seu usuário, sem precisar de admin)."""
    if os.name != "nt":
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
    return get_autostart()


# ---------------------------------------------------------------- uma janela só
def claim_single_instance() -> socket.socket | None:
    """Devolve o socket se esta for a primeira cópia; senão avisa a outra e devolve None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((HOST, LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        try:
            with socket.create_connection((HOST, LOCK_PORT), timeout=2) as c:
                c.sendall(b"show")
        except OSError:
            pass
        return None


# ---------------------------------------------------------------- serviços locais
class Services:
    def __init__(self):
        self.server: subprocess.Popen | None = None
        self.log_file = None

    def ensure_ollama(self) -> None:
        if is_up(f"{OLLAMA}/api/tags"):
            return
        exe = "ollama.exe" if os.name == "nt" else "ollama"
        try:
            subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass  # Ollama não instalado: a tela Serviços mostra o aviso

    def ensure_server(self, wait: float = 60) -> bool:
        if is_up(f"{BASE}/api/health"):
            return True
        (ROOT / "logs").mkdir(exist_ok=True)
        self.log_file = open(ROOT / "logs" / "servidor.log", "ab")  # noqa: SIM115
        env = {**os.environ, "FOR_DISABLE_CONSOLE_CTRL_HANDLER": "1", "PYTHONUTF8": "1"}
        self.server = subprocess.Popen(server_command(), cwd=ROOT, env=env, creationflags=NO_WINDOW,
                                       stdout=self.log_file, stderr=subprocess.STDOUT)
        end = time.time() + wait
        while time.time() < end:
            if is_up(f"{BASE}/api/health"):
                return True
            if self.server.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    def stop_own_server(self) -> None:
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(10)
            except subprocess.TimeoutExpired:
                self.server.kill()
        self.server = None

    def restart_server(self) -> bool:
        """Reinicia o servidor, seja ele deste programa ou da Tarefa Agendada."""
        self.stop_own_server()
        try:
            import psutil
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr and conn.laddr.port == PORT and conn.status == psutil.CONN_LISTEN and conn.pid:
                    psutil.Process(conn.pid).terminate()
        except Exception:  # sem psutil ou sem permissão: tenta subir assim mesmo
            pass
        for _ in range(20):
            if not is_up(f"{BASE}/api/health", 0.5):
                break
            time.sleep(0.5)
        return self.ensure_server()


# ---------------------------------------------------------------- ponte com a página
class Api:
    """Funções que a página chama via window.pywebview.api.* (só existem no programa)."""

    def __init__(self, app: "DesktopApp"):
        self._app = app

    def info(self):
        return {"desktop": True, "autostart": get_autostart(), "root": str(ROOT)}

    def restart_server(self):
        return self._app.services.restart_server()

    def set_autostart(self, enabled):
        return set_autostart(bool(enabled))

    def open_browser(self):
        webbrowser.open(BASE + "/")
        return True

    def open_folder(self, which):
        folder = {"logs": ROOT / "logs", "data": ROOT / "data", "projeto": ROOT}.get(which)
        if folder and os.name == "nt":
            folder.mkdir(exist_ok=True)
            os.startfile(folder)  # noqa: S606
        return bool(folder)

    def hide(self):
        self._app.hide()
        return True

    def quit(self):
        threading.Thread(target=self._app.quit, daemon=True).start()
        return True


class DesktopApp:
    def __init__(self, lock: socket.socket, start_hidden: bool = False):
        self.lock = lock
        self.services = Services()
        self.start_hidden = start_hidden
        self.window = None
        self.tray = None
        self.quitting = False

    # janela
    def show(self):
        if self.window:
            self.window.show()
            self.window.restore()

    def hide(self):
        if self.window:
            self.window.hide()

    def _on_closing(self):
        if self.quitting:
            return True
        self.hide()      # fechar = esconder na bandeja
        return False

    def quit(self):
        self.quitting = True
        if self.tray:
            self.tray.stop()
        self.services.stop_own_server()
        if self.window:
            self.window.destroy()

    # pedidos de outra cópia ("show")
    def _listen_lock(self):
        while not self.quitting:
            try:
                conn, _ = self.lock.accept()
                with conn:
                    if conn.recv(16) == b"show":
                        self.show()
            except OSError:
                return

    # bandeja
    def _tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            return
        icon_png = ROOT / "web" / "icons" / "icon-180.png"
        image = Image.open(icon_png) if icon_png.exists() else Image.new("RGB", (64, 64), "#36d6ff")
        item = pystray.MenuItem
        menu = pystray.Menu(
            item("Abrir Sexta-feira", lambda: self.show(), default=True),
            item("Painel no navegador", lambda: webbrowser.open(BASE + "/")),
            pystray.Menu.SEPARATOR,
            item("Reiniciar servidor", lambda: threading.Thread(
                target=self.services.restart_server, daemon=True).start()),
            item("Abrir com o Windows", lambda: set_autostart(not get_autostart()),
                 checked=lambda _i: get_autostart()),
            pystray.Menu.SEPARATOR,
            item("Sair", lambda: self.quit()),
        )
        self.tray = pystray.Icon("sexta-feira", image, APP_NAME, menu)
        self.tray.run_detached()

    def _boot(self):
        self.services.ensure_ollama()
        ok = self.services.ensure_server()
        if self.window:
            self.window.load_url(f"{BASE}/desktop.html" if ok else self._error_page())

    @staticmethod
    def _error_page() -> str:
        log = ROOT / "logs" / "servidor.log"
        return ("data:text/html;charset=utf-8,<body style='background:%2302060d;color:%23dff6ff;"
                "font-family:Segoe UI;padding:40px'><h2>O servidor não subiu</h2>"
                f"<p>Veja o registro em {log}</p></body>")

    def run(self):
        import webview

        threading.Thread(target=self._listen_lock, daemon=True).start()
        self._tray()
        loading = (ROOT / "desktop" / "carregando.html").as_uri()
        self.window = webview.create_window(
            APP_NAME, loading, js_api=Api(self), width=1440, height=900, min_size=(980, 640),
            background_color="#02060d", hidden=self.start_hidden, text_select=True,
        )
        self.window.events.closing += self._on_closing
        # private_mode=False: guarda as permissões de microfone e o histórico do chat.
        webview.start(self._boot, private_mode=False,
                      storage_path=str(ROOT / "data" / "janela"))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    lock = claim_single_instance()
    if lock is None:
        return 0  # já estava aberto: a outra cópia aparece
    DesktopApp(lock, start_hidden="--bandeja" in argv).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
