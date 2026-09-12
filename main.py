import flet as ft
import threading
import traceback
from pytunnel import PyTunnel

tunnel = None
log_messages = []


def main(page: ft.Page):
    global tunnel

    page.title = "PyTunnel DEBUG"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(label="Host local", value="127.0.0.1", prefix_icon=ft.Icons.DNS)
    txt_port = ft.TextField(label="Porta local", value="8550", prefix_icon=ft.Icons.NUMBERS)
    txt_url = ft.TextField(label="Link público", read_only=True, value="")

    log_column = ft.Column(scroll=ft.ScrollMode.AUTO, height=250, spacing=2)
    log_container = ft.Container(
        content=log_column,
        padding=10, bgcolor="#0a0a0a", border_radius=6,
        border=ft.border.all(1, "#333"),
    )

    txt_status = ft.Text("⚪ Pronto", color="#888", size=13)
    status_container = ft.Container(
        content=txt_status, padding=10, bgcolor="#1e1e1e",
        border_radius=6, border=ft.border.all(1, "#333"),
    )

    btn_iniciar = ft.ElevatedButton(
        text="🚀 Iniciar", width=160, height=45,
        style=ft.ButtonStyle(bgcolor="#4caf50", color="white"),
    )
    btn_parar = ft.ElevatedButton(
        text="⏹️ Parar", width=160, height=45, disabled=True,
        style=ft.ButtonStyle(bgcolor="#f44336", color="white"),
    )

    def add_log(msg):
        """Adiciona log na tela. NÃO chama page.update() (evita bug no Android)."""
        log_messages.append(msg)
        try:
            log_column.controls.append(
                ft.Text(msg, size=11, color="#ccc", font_family="monospace", selectable=True)
            )
        except:
            pass

    def update_ui():
        """Atualiza a UI. Chama só da main thread."""
        try:
            page.update()
        except Exception as e:
            print(f"update error: {e}")

    def iniciar_tunel(e):
        global tunnel

        # Limpar logs anteriores
        log_messages.clear()
        log_column.controls.clear()

        try:
            porta = int(txt_port.value)
            if porta < 1 or porta > 65535:
                raise ValueError()
        except:
            add_log("❌ Porta inválida")
            update_ui()
            return

        btn_iniciar.disabled = True
        btn_parar.disabled = False
        txt_status.value = "⏳ Conectando..."
        txt_status.color = "#ff9800"
        txt_url.value = ""

        add_log("=== INICIANDO ===")
        add_log(f"Host: {txt_host.value}")
        add_log(f"Porta: {porta}")
        update_ui()

        def worker():
            global tunnel
            try:
                add_log("🔧 Criando PyTunnel...")
                tunnel = PyTunnel(
                    local_host=txt_host.value.strip(),
                    local_port=porta,
                    remote_port=80,
                )
                add_log("🔧 Registrando callback...")
                tunnel.set_log_callback(add_log)
                add_log("🚀 Chamando start()...")
                url = tunnel.start()
                add_log(f"📥 start() retornou: {url}")

                if url:
                    txt_url.value = url
                    txt_status.value = "✅ Ativo!"
                    txt_status.color = "#4caf50"
                else:
                    txt_status.value = "❌ Falha (veja logs)"
                    txt_status.color = "#ff5722"
                    btn_iniciar.disabled = False
            except Exception as ex:
                add_log(f"❌ EXCEPTION: {type(ex).__name__}: {ex}")
                add_log("--- TRACEBACK ---")
                for line in traceback.format_exc().splitlines():
                    add_log(line)
                txt_status.value = "❌ Erro grave"
                txt_status.color = "#ff5722"
                btn_iniciar.disabled = False

            update_ui()

        threading.Thread(target=worker, daemon=True).start()

    def parar_tunel(e):
        global tunnel
        btn_parar.disabled = True
        txt_status.value = "⏳ Parando..."
        update_ui()

        def worker():
            global tunnel
            try:
                if tunnel:
                    tunnel.stop()
                    tunnel = None
                add_log("🛑 Parado")
            except Exception as ex:
                add_log(f"❌ Erro ao parar: {ex}")
            txt_url.value = ""
            btn_iniciar.disabled = False
            txt_status.value = "⚪ Pronto"
            txt_status.color = "#888"
            update_ui()

        threading.Thread(target=worker, daemon=True).start()

    btn_iniciar.on_click = iniciar_tunel
    btn_parar.on_click = parar_tunel

    page.add(
        ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LINK, size=28, color="#4caf50"),
                ft.Text("PyTunnel DEBUG", size=22, weight=ft.FontWeight.BOLD),
            ]),
            ft.Divider(),
            txt_host, txt_port,
            ft.Container(height=5),
            txt_url,
            status_container,
            ft.Row([btn_iniciar, btn_parar], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Text("📋 Logs", weight=ft.FontWeight.BOLD, size=14),
            log_container,
        ])
    )


if __name__ == "__main__":
    ft.app(target=main)
