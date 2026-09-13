import flet as ft
import traceback
import paramiko
import select
import socket
import threading
import os
import logging
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PyTunnel")

class PyTunnel:
    """
    Túnel reverso SSH via Pinggy (a.pinggy.io:443).
    Expõe o servidor local (host:porta) para a internet com URL HTTPS pública do Pinggy.
    """

    def __init__(self, local_host="127.0.0.1", local_port=8550,
                 remote_port=0, ssh_server="a.pinggy.io", ssh_user="http",
                 key_path=None):
        self.local_host = local_host
        self.local_port = local_port
        self.remote_port = remote_port 
        self.ssh_server = ssh_server
        self.ssh_user = ssh_user # 'http' para túnel web no Pinggy

        self.ssh_client = None
        self.transport = None
        self.is_running = False
        self.public_url = None
        self._thread = None
        self._channels = []
        self.log_callback = None

    def set_log_callback(self, callback):
        self.log_callback = callback

    def _log(self, mensagem):
        logger.info(mensagem)
        if self.log_callback:
            try:
                self.log_callback(mensagem)
            except:
                pass

    def _handler_conexao(self, chan):
        """Encaminha dados entre o canal SSH do Pinggy e o servidor local."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.local_host, self.local_port))
        except Exception as e:
            self._log(f"❌ Falha ao conectar no app local ({self.local_host}:{self.local_port}): {e}")
            try:
                chan.close()
            except:
                pass
            return

        try:
            while self.is_running:
                r, _, _ = select.select([sock, chan], [], [], 1.0)
                if not self.is_running:
                    break
                if chan in r:
                    data = chan.recv(4096)
                    if not data:
                        break
                    sock.sendall(data)
                if sock in r:
                    data = sock.recv(4096)
                    if not data:
                        break
                    chan.sendall(data)
        except Exception as e:
            pass
        finally:
            try:
                chan.close()
            except:
                pass
            try:
                sock.close()
            except:
                pass

    def _loop_aceitar(self):
        """Escuta as conexões que o Pinggy redireciona da internet."""
        self._log("🔄 Loop de escuta do túnel ativo.")
        while self.is_running and self.transport and self.transport.is_active():
            try:
                chan = self.transport.accept(1)
                if chan is None:
                    continue
                
                self._log("🌐 Requisição externa recebida do Pinggy! Redirecionando...")
                self._channels.append(chan)
                threading.Thread(
                    target=self._handler_conexao,
                    args=(chan,),
                    daemon=True
                ).start()
            except Exception as e:
                if self.is_running:
                    pass
                break
        self._log("🛑 Loop de escuta encerrado.")

    def start(self):
        """Conecta no Pinggy e lê o link gerado abrindo um canal de shell interativo."""
        if self.is_running:
            self._log("Túnel já está ativo.")
            return self.public_url

        try:
            # Gera chave RSA limpa direto na memória
            self._log("Gerando chave temporária para o Pinggy...")
            key = paramiko.RSAKey.generate(2048)

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self._log(f"Conectando em {self.ssh_server}:443...")
            self.ssh_client.connect(
                hostname=self.ssh_server,
                port=443,
                username=self.ssh_user,
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=25,
                banner_timeout=25,
            )

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)

            # Solicita o encaminhamento de porta
            self._log("Solicitando porta remota ao Pinggy...")
            self.transport.request_port_forward('', self.remote_port)

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()

            # Abre um canal de Shell Interativo para capturar a URL do Pinggy
            url_encontrada = None
            try:
                self._log("Abrindo shell para capturar a URL...")
                shell = self.ssh_client.invoke_shell()
                shell.settimeout(1.0)
                
                dados_iniciais = b""
                import time
                inicio_tentativa = time.time()
                
                # Aguarda até 8 segundos coletando a saída do shell
                while time.time() - inicio_tentativa < 8.0:
                    try:
                        if shell.recv_ready():
                            chunk = shell.recv(4096)
                            if chunk:
                                dados_iniciais += chunk
                                texto_parcial = dados_iniciais.decode('utf-8', errors='ignore')
                                
                                # Limpa códigos ANSI de formatação do terminal antes de procurar
                                texto_limpo_regex = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', texto_parcial)
                                
                                # Regex estrita: para exatamente onde termina o domínio (.net ou .link), ignorando pipes e lixo
                                matches = re.findall(r'(https://[a-zA-Z0-9.-]+(?:free\.pinggy\.net|pinggy-free\.link))', texto_limpo_regex)
                                if matches:
                                    for m in matches:
                                        link_candidato = m.strip()
                                        if "dashboard" not in link_candidato and len(link_candidato) > 15:
                                            url_encontrada = link_candidato
                                            break
                                    if url_encontrada:
                                        break
                    except socket.timeout:
                        pass
                    time.sleep(0.3)
                
                texto_canal = dados_iniciais.decode('utf-8', errors='ignore')
                if texto_canal.strip():
                    texto_limpo = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', texto_canal)
                    self._log(f"Mensagem do servidor Pinggy:\n{texto_limpo.strip()}")
                
                try:
                    shell.close()
                except:
                    pass

            except Exception as ex:
                self._log(f"Nota ao ler shell: {ex}")

            if not url_encontrada:
                url_encontrada = "https://<Verifique_a_mensagem_do_servidor_acima>"

            self.public_url = url_encontrada
            self._log(f"✅ Túnel ativo! URL Oficial do Pinggy: {self.public_url}")
            return self.public_url

        except Exception as e:
            self._log(f"❌ Erro ao iniciar túnel: {e}")
            self.stop()
            return None

    def stop(self):
        self.is_running = False
        for chan in self._channels:
            try:
                chan.close()
            except:
                pass
        self._channels.clear()

        if self.transport:
            try:
                self.transport.close()
            except:
                pass
            self.transport = None

        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None

        self._log("Túnel parado.")

    def is_active(self):
        return (self.is_running
                and self.transport is not None
                and self.transport.is_active())


# ==========================================
# INTERFACE GRÁFICA (FLET)
# ==========================================
tunnel = None

def main(page: ft.Page):
    global tunnel

    page.title = "PyTunnel S"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(label="Host local", value="127.0.0.1", prefix_icon=ft.Icons.DNS)
    txt_port = ft.TextField(label="Porta local", value="8550", prefix_icon=ft.Icons.NUMBERS)
    txt_url = ft.TextField(label="Link público oficial (Pinggy)", read_only=True, value="")

    logs_field = ft.TextField(
        value="",
        read_only=True,
        multiline=True,
        min_lines=12,
        max_lines=12,
        text_size=11,
        color="#ccc",
    )

    logs_container = ft.Container(
        content=logs_field,
        padding=5,
        bgcolor="#0a0a0a",
        border_radius=6,
        border=ft.border.all(1, "#333"),
    )

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

    def on_iniciar(e):
        global tunnel

        btn_iniciar.disabled = True
        btn_parar.disabled = False
        txt_status.value = "⏳ Conectando ao Pinggy..."
        txt_status.color = "#ff9800"
        txt_url.value = ""
        logs_field.value = ""
        page.update()

        def log(msg):
            logs_field.value = (logs_field.value or "") + msg + "\n"
            try:
                page.update()
            except:
                pass

        try:
            porta = int(txt_port.value)
        except:
            log("❌ Porta inválida")
            txt_status.value = "❌ Porta inválida"
            txt_status.color = "#ff5722"
            btn_iniciar.disabled = False
            page.update()
            return

        tunnel = PyTunnel(
            local_host=txt_host.value.strip(),
            local_port=porta,
            remote_port=0,
        )
        tunnel.set_log_callback(log)

        url = tunnel.start()

        if url:
            txt_url.value = url
            txt_status.value = "✅ Ativo!"
            txt_status.color = "#4caf50"
            btn_parar.disabled = False
        else:
            txt_status.value = "❌ Falha"
            txt_status.color = "#ff5722"
            btn_iniciar.disabled = False
            btn_parar.disabled = True

        page.update()

    def on_parar(e):
        global tunnel
        try:
            if tunnel:
                tunnel.stop()
                tunnel = None
            txt_url.value = ""
            btn_iniciar.disabled = False
            btn_parar.disabled = True
            txt_status.value = "⚪ Pronto"
            txt_status.color = "#888"
            logs_field.value = (logs_field.value or "") + "\n🛑 Parado"
        except Exception as ex:
            logs_field.value = (logs_field.value or "") + f"\n❌ {ex}"
        page.update()

    btn_iniciar.on_click = on_iniciar
    btn_parar.on_click = on_parar

    page.add(
        ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LINK, size=28, color="#4caf50"),
                ft.Text("PyTunnel S", size=22, weight=ft.FontWeight.BOLD),
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
