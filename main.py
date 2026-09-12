import flet as ft
import asyncio
import traceback
from pytunnel import PyTunnel

tunnel = None


def main(page: ft.Page):
    global tunnel

    page.title = "PyTunnel v3"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(label="Host local", value="127.0.0.1", prefix_icon=ft.Icons.DNS)
    txt_port = ft.TextField(label="Porta local", value="8550", prefix_icon=ft.Icons.NUMBERS)
    txt_url = ft.TextField(label="Link público", read_only=True, value="")

    # ===== LOG COMO TEXTO ÚNICO (igual ao teste que funcionou) =====
    logs_text = ft.Text(
        value="Aguardando...",
        size=11,
        color="#ccc",
        selectable=True,
        font_family="monospace",
    )

    logs_container = ft.Container(
        content=ft.Column([logs_text], scroll=ft.ScrollMode.AUTO),
        padding=10,
        bgcolor="#0a0a0a",
        border_radius=6,
        border=ft.border.all(1, "#333"),
        height=300,
    )

    def escrever(msg):
        """Atualiza o texto dos logs (MÉTODO QUE FUNCIONOU no teste anterior)."""
        if logs_text.value == "Aguardando...":
            logs_text.value = msg
        else:
            logs_text.value = (logs_text.value or "") + "\n" + msg

    txt_status = ft.Text("⚪ Pronto", color="#888", size=13)
    status_container = ft.Container(
        content=txt_status,
        padding=10,
        bgcolor="#1e1e1e",
        border_radius=6,
        border=ft.border.all(1, "#333"),
    )

    btn_iniciar = ft.ElevatedButton(
        text="🚀 Iniciar", width=160, height=45,
        style=ft.ButtonStyle(bgcolor="#4caf50", color="white"),
    )
    btn_parar = ft.ElevatedButton(
        text="⏹️ Parar", width=160, height=45, disabled=True,
        style=ft.ButtonStyle(bgcolor="#f44336", color="white"),
    )

    def log_callback(msg):
        """Chamado pelo pytunnel.py. Só acumula, não atualiza UI."""
        escrever(msg)

    async def rodar_tunel():
        """Roda o túnel de forma assíncrona (método recomendado no Flet)."""
        global tunnel

        escrever("=== INICIANDO ===")
        escrever(f"Host: {txt_host.value}")
        escrever(f"Porta: {txt_port.value}")
        page.update()

        try:
            porta = int(txt_port.value)
        except:
            escrever("❌ Porta inválida")
            page.update()
            return

        escrever("🔧 Criando PyTunnel...")
        page.update()

        try:
            tunnel = PyTunnel(
                local_host=txt_host.value.strip(),
                local_port=porta,
                remote_port=80,
            )
            tunnel.set_log_callback(log_callback)
            escrever("🚀 Chamando start()...")
            page.update()

            # Roda o start em thread separada dentro da task async
            # para não bloquear a UI
            url = await asyncio.get_event_loop().run_in_executor(
                None, tunnel.start
            )

            escrever(f"📥 start() retornou: {url}")
            page.update()

            if url:
                txt_url.value = url
                txt_status.value = "✅ Ativo!"
                txt_status.color = "#4caf50"
                page.update()
            else:
                txt_status.value = "❌ Falha (veja logs acima)"
                txt_status.color = "#ff5722"
                btn_iniciar.disabled = False
                page.update()

        except Exception as ex:
            escrever(f"❌ EXCEPTION: {type(ex).__name__}: {ex}")
            for line in traceback.format_exc().splitlines():
                escrever(line)
            txt_status.value = "❌ Erro grave"
            txt_status.color = "#ff5722"
            btn_iniciar.disabled = False
            page.update()

    def on_iniciar(e):
        btn_iniciar.disabled = True
        btn_parar.disabled = False
        txt_status.value = "⏳ Conectando..."
        txt_status.color = "#ff9800"
        logs_text.value = ""  # limpa logs
        page.update()

        # Usa run_task (método correto no Flet)
        page.run_task(rodar_tunel)

    def on_parar(e):
        global tunnel
        btn_parar.disabled = True
        txt_status.value = "⏳ Parando..."
        page.update()

        def parar():
            global tunnel
            try:
                if tunnel:
                    tunnel.stop()
                    tunnel = None
                escrever("🛑 Parado")
            except Exception as ex:
                escrever(f"❌ Erro: {ex}")

        # Para em thread, mas atualiza o texto e chama update
        import threading
        def worker():
            parar()
            txt_url.value = ""
            btn_iniciar.disabled = False
            txt_status.value = "⚪ Pronto"
            txt_status.color = "#888"
            page.update()

        threading.Thread(target=worker, daemon=True).start()

    btn_iniciar.on_click = on_iniciar
    btn_parar.on_click = on_parar

    page.add(
        ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LINK, size=28, color="#4caf50"),
                ft.Text("PyTunnel v3", size=22, weight=ft.FontWeight.BOLD),
            ]),
            ft.Divider(),
            txt_host, txt_port,
            ft.Container(height=5),
            txt_url,
            status_container,
            ft.Row([btn_iniciar, btn_parar], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Text("📋 Logs", weight=ft.FontWeight.BOLD, size=14),
            logs_container,
        ])
    )


if __name__ == "__main__":
    ft.app(target=main)
