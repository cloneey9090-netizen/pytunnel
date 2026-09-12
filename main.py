import flet as ft
import threading
from pytunnel import PyTunnel

tunnel = None


def main(page: ft.Page):
    global tunnel

    page.title = "PyTunnel"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 400
    page.window.height = 720
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(label="Host local", value="127.0.0.1", prefix_icon=ft.Icons.DNS)
    txt_port = ft.TextField(label="Porta local", value="8550", prefix_icon=ft.Icons.NUMBERS)
    txt_url = ft.TextField(label="Link público", read_only=True, value="")

    btn_copy = ft.IconButton(icon=ft.Icons.COPY, tooltip="Copiar link", disabled=True)

    def copiar_url(e):
        if txt_url.value:
            page.set_clipboard(txt_url.value)
            page.open(ft.SnackBar(content=ft.Text("✅ Link copiado!")))
            page.update()

    btn_copy.on_click = copiar_url

    logs_text = ft.Text(value="", size=11, color="#aaa", selectable=True, font_family="monospace")
    logs_container = ft.Container(
        content=ft.Column([logs_text], scroll=ft.ScrollMode.AUTO),
        padding=10, bgcolor="#0a0a0a", border_radius=6,
        border=ft.border.all(1, "#333"), height=200,
    )

    def adicionar_log(msg):
        try:
            logs_text.value = (logs_text.value or "") + f"\n{msg}"
            page.update()
        except:
            pass

    txt_status = ft.Text("⚪ Pronto", color="#888", size=13)
    txt_status_container = ft.Container(
        content=txt_status, padding=10, bgcolor="#1e1e1e",
        border_radius=6, border=ft.border.all(1, "#333"),
    )

    btn_iniciar = ft.ElevatedButton(
        text="🚀 Iniciar", width=250, height=50,
        style=ft.ButtonStyle(bgcolor="#4caf50", color="white"),
    )
    btn_parar = ft.ElevatedButton(
        text="⏹️ Parar", width=250, height=50, disabled=True,
        style=ft.ButtonStyle(bgcolor="#f44336", color="white"),
    )

    def iniciar_tunel(e):
        global tunnel
        try:
            porta = int(txt_port.value)
        except:
            txt_status.value = "❌ Porta inválida"
            txt_status.color = "#ff5722"
            page.update()
            return

        btn_iniciar.disabled = True
        btn_parar.disabled = False
        txt_status.value = "⏳ Conectando..."
        txt_status.color = "#ff9800"
        logs_text.value = "=== Iniciando ==="
        page.update()

        def _criar():
            global tunnel
            try:
                tunnel = PyTunnel(
                    local_host=txt_host.value.strip(),
                    local_port=porta,
                    remote_port=80,
                )
                tunnel.set_log_callback(adicionar_log)
                url = tunnel.start()

                if url:
                    txt_url.value = url
                    btn_copy.disabled = False
                    txt_status.value = "✅ Ativo!"
                    txt_status.color = "#4caf50"
                else:
                    txt_status.value = "❌ Falha (veja logs)"
                    txt_status.color = "#ff5722"
                    btn_iniciar.disabled = False
            except Exception as ex:
                adicionar_log(f"❌ {type(ex).__name__}: {ex}")
                txt_status.value = "❌ Erro"
                txt_status.color = "#ff5722"
                btn_iniciar.disabled = False
            page.update()

        threading.Thread(target=_criar, daemon=True).start()

    def parar_tunel(e):
        global tunnel
        btn_parar.disabled = True
        txt_status.value = "⏳ Parando..."
        page.update()

        def _parar():
            global tunnel
            if tunnel:
                tunnel.stop()
                tunnel = None
            txt_url.value = ""
            btn_copy.disabled = True
            btn_iniciar.disabled = False
            txt_status.value = "⚪ Pronto"
            txt_status.color = "#888"
            page.update()

        threading.Thread(target=_parar, daemon=True).start()

    btn_iniciar.on_click = iniciar_tunel
    btn_parar.on_click = parar_tunel

    page.add(
        ft.Column(controls=[
            ft.Row([
                ft.Icon(ft.Icons.LINK, size=30, color="#4caf50"),
                ft.Text("PyTunnel", size=26, weight=ft.FontWeight.BOLD),
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Text("📍 Servidor Local", weight=ft.FontWeight.BOLD, size=14),
            txt_host, txt_port,
            ft.Container(height=8),
            ft.Text("🔗 Link Público", weight=ft.FontWeight.BOLD, size=14),
            ft.Row([txt_url, btn_copy], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=8),
            txt_status_container,
            ft.Container(height=8),
            ft.Row([btn_iniciar], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([btn_parar], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Text("📋 Logs", weight=ft.FontWeight.BOLD, size=14),
            logs_container,
        ])
    )


if __name__ == "__main__":
    ft.app(target=main)
