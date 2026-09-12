import flet as ft
import socket
import urllib.request
import time


def main(page: ft.Page):
    page.title = "Teste"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    resultado = ft.Text(
        value="Aguardando clique...",
        size=14,
        color="white",
        selectable=True,
        font_family="monospace",
    )

    contador = ft.Text(value="Cliques: 0", size=12, color="#888")

    clique_count = [0]

    def testar(e):
        # Passo 1: atualizar imediatamente
        clique_count[0] += 1
        contador.value = f"Cliques: {clique_count[0]}"
        resultado.value = f"Clique #{clique_count[0]} detectado! Rodando testes...\n"
        page.update()

        # Passo 2: teste HTTP
        try:
            req = urllib.request.Request(
                "https://api.github.com",
                headers={"User-Agent": "Test/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resultado.value += f"[OK] HTTP: {resp.status}\n"
        except Exception as ex:
            resultado.value += f"[ERRO] HTTP: {type(ex).__name__}: {ex}\n"
        page.update()

        # Passo 3: teste srv.us:22
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            inicio = time.time()
            s.connect(("srv.us", 22))
            dur = round(time.time() - inicio, 2)
            s.close()
            resultado.value += f"[OK] srv.us:22 ({dur}s)\n"
        except Exception as ex:
            resultado.value += f"[ERRO] srv.us:22: {type(ex).__name__}\n"
        page.update()

        # Passo 4: teste localhost.run:22
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            s.connect(("localhost.run", 22))
            s.close()
            resultado.value += f"[OK] localhost.run:22\n"
        except Exception as ex:
            resultado.value += f"[ERRO] localhost.run:22: {type(ex).__name__}\n"
        page.update()

        # Passo 5: teste porta 443 (HTTPS) para comparar
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(8)
            s.connect(("srv.us", 443))
            s.close()
            resultado.value += f"[OK] srv.us:443 (HTTPS)\n"
        except Exception as ex:
            resultado.value += f"[ERRO] srv.us:443: {type(ex).__name__}\n"
        page.update()

        resultado.value += "\n=== FIM ==="
        page.update()

    btn = ft.ElevatedButton(
        text="TESTAR",
        width=250,
        height=55,
        style=ft.ButtonStyle(bgcolor="#2196f3", color="white"),
        on_click=testar,
    )

    page.add(
        ft.Column(
            controls=[
                ft.Text("Teste de Rede", size=22, weight=ft.FontWeight.BOLD),
                contador,
                ft.Divider(),
                ft.Row([btn], alignment=ft.MainAxisAlignment.CENTER),
                ft.Divider(),
                ft.Container(
                    content=resultado,
                    padding=10,
                    bgcolor="#0a0a0a",
                    border_radius=6,
                    border=ft.border.all(1, "#333"),
                    height=400,
                ),
            ]
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
