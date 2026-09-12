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
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(
        label="Host local",
        value="127.0.0.1",
        hint_text="Ex: 127.0.0.1",
        prefix_icon=ft.Icons.DNS,
    )

    txt_port = ft.TextField(
        label="Porta local",
        value="8550",
        hint_text="Ex: 8550",
        prefix_icon=ft.Icons.NUMBERS,
    )

    txt_status = ft.Text("⚪ Pronto para iniciar", color="#888", size=13)
    txt_status_container = ft.Container(
        content=txt_status,
        padding=12,
        bgcolor="#1e1e1e",
        border_radius=8,
        border=ft.border.all(1, "#333333"),
    )

    txt_url = ft.TextField(
        label="Link público",
        read_only=True,
        value="",
        multiline=False,
    )

    btn_copy = ft.IconButton(
        icon=ft.Icons.COPY,
        tooltip="Copiar link",
        disabled=True,
    )

    def copiar_url(e):
        if txt_url.value:
            page.set_clipboard(txt_url.value)
            page.open(ft.SnackBar(content=ft.Text("✅ Link copiado!")))
            page.update()

    btn_copy.on_click = copiar_url

    btn_iniciar = ft.ElevatedButton(
        text="🚀 Iniciar Túnel",
        width=250,
        height=50,
        style=ft.ButtonStyle(bgcolor="#4caf50", color="white"),
    )

    btn_parar = ft.ElevatedButton(
        text="⏹️ Parar Túnel",
        width=250,
        height=50,
        disabled=True,
        style=ft.ButtonStyle(bgcolor="#f44336", color="white"),
    )

    def iniciar_tunel(e):
        global tunnel

        if not txt_host.value or not txt_port.value:
            txt_status.value = "❌ Preencha host e porta"
            txt_status.color = "#ff5722"
            page.update()
            return

        try:
            porta = int(txt_port.value)
            if porta < 1 or porta > 65535:
                raise ValueError()
        except ValueError:
            txt_status.value = "❌ Porta inválida (use 1-65535)"
            txt_status.color = "#ff5722"
            page.update()
            return

        btn_iniciar.disabled = True
        btn_parar.disabled = True
        txt_status.value = "⏳ Conectando ao servidor..."
        txt_status.color = "#ff9800"
        page.update()

        def _criar_tunel():
            global tunnel
            try:
                tunnel = PyTunnel(
                    local_host=txt_host.value.strip(),
                    local_port=porta,
                    remote_port=80,
                )
                url = tunnel.start()

                if url:
                    txt_url.value = url
                    btn_copy.disabled = False
                    txt_status.value = "✅ Túnel ativo!"
                    txt_status.color = "#4caf50"
                    btn_parar.disabled = False
                    page.open(ft.SnackBar(content=ft.Text("✅ Túnel criado com sucesso!")))
                else:
                    txt_status.value = "❌ Falha ao criar túnel. Verifique a conexão."
                    txt_status.color = "#ff5722"
                    btn_iniciar.disabled = False
            except Exception as ex:
                txt_status.value = f"❌ Erro: {ex}"
                txt_status.color = "#ff5722"
                btn_iniciar.disabled = False
            page.update()

        threading.Thread(target=_criar_tunel, daemon=True).start()

    def parar_tunel(e):
        global tunnel
        btn_parar.disabled = True
        txt_status.value = "⏳ Parando..."
        txt_status.color = "#ff9800"
        page.update()

        def _parar():
            global tunnel
            if tunnel:
                tunnel.stop()
                tunnel = None
            txt_url.value = ""
            btn_copy.disabled = True
            btn_iniciar.disabled = False
            txt_status.value = "⚪ Pronto para iniciar"
            txt_status.color = "#888"
            page.open(ft.SnackBar(content=ft.Text("Túnel parado")))
            page.update()

        threading.Thread(target=_parar, daemon=True).start()

    btn_iniciar.on_click = iniciar_tunel
    btn_parar.on_click = parar_tunel

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LINK, size=32, color="#4caf50"),
                        ft.Text("PyTunnel", size=28, weight=ft.FontWeight.BOLD),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Text(
                    "Exponha seu servidor local para a internet",
                    size=13,
                    color="#888",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Divider(),
                ft.Text("📍 Servidor Local", weight=ft.FontWeight.BOLD, size=15),
                txt_host,
                txt_port,
                ft.Container(height=10),
                ft.Text("🔗 Link Público", weight=ft.FontWeight.BOLD, size=15),
                ft.Row(
                    controls=[txt_url, btn_copy],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=10),
                txt_status_container,
                ft.Container(height=15),
                ft.Row([btn_iniciar], alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([btn_parar], alignment=ft.MainAxisAlignment.CENTER),
                ft.Divider(),
                ft.Text(
                    "🔐 Conexão via SSH com criptografia ponta a ponta.\n"
                    "🌐 Serviço: srv.us (gratuito e de código aberto).\n"
                    "💡 O link é estável: ele não muda entre reinicializações.",
                    size=11,
                    color="#666",
                ),
            ],
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
