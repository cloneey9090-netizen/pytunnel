import flet as ft
import socket
import urllib.request
import time


def main(page: ft.Page):
    page.title = "Teste Simples"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    logs = ft.Text(
        value="Clique no botão para testar",
        size=13,
        color="#ccc",
        selectable=True,
        font_family="monospace",
    )

    container = ft.Container(
        content=logs,
        padding=10,
        bgcolor="#0a0a0a",
        border_radius=6,
        border=ft.border.all(1, "#333"),
        height=450,
    )

    def testar(e):
        logs.value = "INICIANDO TESTE...\n"
        page.update()

        try:
            req = urllib.request.Request(
                "https://api.github.com",
                headers={"User-Agent": "Test/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                logs.value += f"HTTP OK: {resp.status}\n"
        except Exception as ex:
            logs.value += f"HTTP ERRO: {type(ex).__name__}: {ex}\n"
        page.update()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            inicio = time.time()
            s.connect(("srv.us", 22))
            dur = round(time.time() - inicio, 2)
            s.close()
            logs.value += f"srv.us:22 OK ({dur}s)\n"
        except Exception as ex:
            logs.value += f"srv.us:22 ERRO: {type(ex).__name__}: {ex}\n"
        page.update()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            s.connect(("localhost.run", 22))
            s.close()
            logs.value += "localhost.run:22 OK\n"
        except Exception as ex:
            logs.value += f"localhost.run:22 ERRO: {type(ex).__name__}: {ex}\n"
        page.update()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            s.connect(("serveo.net", 22))
            s.close()
            logs.value += "serveo.net:22 OK\n"
        except Exception as ex:
            logs.value += f"serveo.net:22 ERRO: {type(ex).__name__}: {ex}\n"
        page.update()

        logs.value += "\nFIM DO TESTE\n"
        page.update()

    btn = ft.ElevatedButton(
        text="TESTAR AGORA",
        width=280,
        height=55,
        style=ft.ButtonStyle(bgcolor="#2196f3", color="white"),
        on_click=testar,
    )

    page.add(
        ft.Column(
            controls=[
                ft.Text("Teste de Rede", size=24, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([btn], alignment=ft.MainAxisAlignment.CENTER),
                ft.Divider(),
                container,
            ],
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
