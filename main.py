import flet as ft
import threading
import socket
import requests
import time


def main(page: ft.Page):
    page.title = "PyTunnel - Diagnóstico"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 400
    page.window.height = 720
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(label="Host local", value="127.0.0.1", prefix_icon=ft.Icons.DNS)
    txt_port = ft.TextField(label="Porta local", value="8550", prefix_icon=ft.Icons.NUMBERS)

    logs_text = ft.Text(value="Aguardando...", size=11, color="#aaa", selectable=True, font_family="monospace")
    logs_container = ft.Container(
        content=ft.Column([logs_text], scroll=ft.ScrollMode.AUTO),
        padding=10, bgcolor="#0a0a0a", border_radius=6,
        border=ft.border.all(1, "#333"), height=400,
    )

    def log(msg):
        try:
            logs_text.value = (logs_text.value or "") + "\n" + msg
            page.update()
        except:
            pass

    def limpar_log(e=None):
        logs_text.value = "Iniciando diagnóstico...\n"
        page.update()

    def testar_socket(host, porta, timeout=8):
        """Testa conexão TCP crua, sem paramiko."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            inicio = time.time()
            sock.connect((host, porta))
            duracao = round(time.time() - inicio, 2)
            sock.close()
            return True, duracao
        except socket.timeout:
            return False, "timeout"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def rodar_diagnostico(e):
        limpar_log()
        threading.Thread(target=_diagnostico, daemon=True).start()

    def _diagnostico():
        log("=" * 40)
        log("🔍 DIAGNÓSTICO PyTunnel")
        log("=" * 40)

        # ETAPA 1 — HTTP básico
        log("\n📡 ETAPA 1: Teste HTTP (internet básica)")
        try:
            inicio = time.time()
            r = requests.get("https://api.github.com", timeout=10)
            duracao = round(time.time() - inicio, 2)
            log(f"✅ HTTP OK - Status {r.status_code} em {duracao}s")
        except Exception as ex:
            log(f"❌ HTTP FALHOU: {type(ex).__name__}: {ex}")
            log("⚠️ Sem internet básica. Verifique a conexão.")

        # ETAPA 2 — Teste TCP direto na porta 22
        servidores_teste = [
            ("srv.us", 22),
            ("localhost.run", 22),
            ("serveo.net", 22),
        ]

        log("\n🔌 ETAPA 2: Teste TCP na porta 22 (SSH)")
        for host, porta in servidores_teste:
            log(f"\n   Testando {host}:{porta}...")
            ok, info = testar_socket(host, porta)
            if ok:
                log(f"   ✅ {host}:{porta} OK ({info}s)")
            else:
                log(f"   ❌ {host}:{porta} FALHOU: {info}")

        # ETAPA 3 — Teste servidor local
        log("\n🏠 ETAPA 3: Teste do servidor local")
        host_local = txt_host.value.strip() or "127.0.0.1"
        try:
            porta_local = int(txt_port.value)
        except:
            porta_local = 8550

        log(f"   Testando {host_local}:{porta_local}...")
        ok, info = testar_socket(host_local, porta_local)
        if ok:
            log(f"   ✅ Servidor local OK ({info}s)")
        else:
            log(f"   ❌ Servidor local FALHOU: {info}")

        # ETAPA 4 — Teste do paramiko (importação)
        log("\n🐍 ETAPA 4: Teste de importação do paramiko")
        try:
            import paramiko
            log(f"   ✅ paramiko importado - versão {paramiko.__version__}")
        except Exception as ex:
            log(f"   ❌ paramiko FALHOU: {type(ex).__name__}: {ex}")

        log("\n" + "=" * 40)
        log("✅ Diagnóstico completo. Mande um print desta tela.")
        log("=" * 40)

    btn_diagnostico = ft.ElevatedButton(
        text="🔍 Rodar Diagnóstico",
        width=280, height=50,
        style=ft.ButtonStyle(bgcolor="#2196f3", color="white"),
        on_click=rodar_diagnostico,
    )

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.BUG_REPORT, size=30, color="#2196f3"),
                        ft.Text("PyTunnel Diagnóstico", size=22, weight=ft.FontWeight.BOLD),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Text("Testa rede, SSH e dependências", size=12, color="#888"),
                ft.Divider(),
                txt_host, txt_port,
                ft.Container(height=8),
                ft.Row([btn_diagnostico], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=8),
                ft.Text("📋 Resultado:", weight=ft.FontWeight.BOLD),
                logs_container,
            ],
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
