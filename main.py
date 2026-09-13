"""
PyTunnel Pro - Túnel reverso SSH com múltiplos provedores.
- Chave Ed25519 (Pinggy, srv.us) e RSA (localhost.run)
- Auth NONE para localhost.run
- Timeouts de 45s
- Reconexão automática
- Fallback entre provedores
- Contador de tempo e status em tempo real
"""
import flet as ft
import traceback
import paramiko
import select
import socket
import threading
import os
import io
import time
import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PyTunnel")


# ============================================================
# CLASSE PyTunnel - Motor do túnel com múltiplos provedores
# ============================================================

class PyTunnel:
    """
    Túnel reverso SSH com fallback automático entre provedores gratuitos.
    Ordem: Pinggy → localhost.run → srv.us
    """

    PROVEDORES = [
        {
            "nome": "Pinggy",
            "server": "free.pinggy.io",
            "port": 443,
            "user": "free",
            "auth": "publickey",
            "tipo_chave": "ed25519",
            "porta_remota": 0,
            "regex_url": r'https://[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]*(?:run\.pinggy-free\.link|free\.pinggy\.net|a\.pinggy\.link|pinggy\.online)',
            "requer_shell": True,
            "limite_min": 60,
        },
        {
            "nome": "localhost.run",
            "server": "localhost.run",
            "port": 22,
            "user": "nokey",
            "auth": "none",
            "tipo_chave": None,
            "porta_remota": 0,
            "regex_url": r'https://[a-zA-Z0-9\-]+\.lhr\.life',
            "requer_shell": False,
            "limite_min": 0,
        },
        {
            "nome": "srv.us",
            "server": "srv.us",
            "port": 22,
            "user": "",
            "auth": "publickey",
            "tipo_chave": "ed25519",
            "porta_remota": 1,
            "regex_url": r'https://[a-zA-Z0-9\-]+\.srv\.us',
            "requer_shell": False,
            "limite_min": 0,
        },
    ]

    def __init__(self, local_host="127.0.0.1", local_port=8550,
                 key_path=None, provedor_preferido=None):
        self.local_host = local_host
        self.local_port = local_port
        self.key_path = key_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tunnel_key"
        )
        self.provedor_preferido = provedor_preferido

        self.ssh_client = None
        self.transport = None
        self.is_running = False
        self.public_url = None
        self._thread = None
        self._channels = []
        self.log_callback = None
        self.status_callback = None

        self.provedor_atual = None
        self.inicio_conexao = None
        self.tentativas_reconexao = 0
        self.max_tentativas = 5

    def set_log_callback(self, callback):
        self.log_callback = callback

    def set_status_callback(self, callback):
        self.status_callback = callback

    def _log(self, mensagem):
        logger.info(mensagem)
        if self.log_callback:
            try:
                self.log_callback(mensagem)
            except:
                pass

    def _notificar_status(self, status, mensagem, detalhes=""):
        if self.status_callback:
            try:
                self.status_callback(status, mensagem, detalhes)
            except:
                pass

    def _load_or_generate_key(self, provedor):
        """Carrega ou gera chave SSH. Retorna None se auth='none'."""
        tipo_chave = provedor.get("tipo_chave")
        if not tipo_chave:
            return None  # localhost.run não usa chave

        caminho_chave = f"{self.key_path}_{tipo_chave}"

        # Tenta carregar chave existente
        if os.path.exists(caminho_chave):
            self._log(f"🔑 Carregando chave {tipo_chave.upper()}...")
            try:
                with open(caminho_chave, "r") as f:
                    conteudo = f.read()
                if tipo_chave == "rsa":
                    return paramiko.RSAKey.from_private_key(io.StringIO(conteudo))
                else:
                    return paramiko.Ed25519Key.from_private_key(io.StringIO(conteudo))
            except Exception as e:
                self._log(f"⚠️ Chave corrompida, gerando nova")
                try:
                    os.remove(caminho_chave)
                except:
                    pass

        # Gera nova chave
        self._log(f"🔑 Gerando nova chave {tipo_chave.upper()}...")

        if tipo_chave == "rsa":
            key = paramiko.RSAKey.generate(2048)
            try:
                key.write_private_key_file(caminho_chave)
                self._log(f"✅ Chave RSA salva")
            except Exception as e:
                self._log(f"⚠️ Não salvou: {e}")
            return key
        else:
            try:
                from cryptography.hazmat.primitives.asymmetric import ed25519
                from cryptography.hazmat.primitives import serialization

                private_key = ed25519.Ed25519PrivateKey.generate()
                private_bytes = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.OpenSSH,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                chave_str = private_bytes.decode("utf-8")

                pasta = os.path.dirname(caminho_chave)
                if pasta and not os.path.exists(pasta):
                    os.makedirs(pasta, exist_ok=True)
                with open(caminho_chave, "w") as f:
                    f.write(chave_str)
                self._log(f"✅ Chave Ed25519 salva")

                return paramiko.Ed25519Key.from_private_key(io.StringIO(chave_str))
            except Exception as e:
                self._log(f"❌ Erro Ed25519: {e}")
                key = paramiko.RSAKey.generate(2048)
                return key

    def _handler_conexao(self, chan):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.local_host, self.local_port))
        except Exception as e:
            self._log(f"❌ Local falhou ({self.local_host}:{self.local_port}): {e}")
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
        except Exception:
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
        self._log("🔄 Loop de escuta iniciado")
        while self.is_running and self.transport and self.transport.is_active():
            try:
                chan = self.transport.accept(1)
                if chan is None:
                    continue
                self._log(f"🌐 Requisição externa recebida!")
                self._channels.append(chan)
                threading.Thread(
                    target=self._handler_conexao, args=(chan,), daemon=True
                ).start()
            except Exception:
                if self.is_running:
                    pass
                break
        self._log("🛑 Loop de escuta encerrado")

    def _capturar_url_shell(self, provedor):
        """Captura URL abrindo shell interativo (Pinggy)."""
        try:
            shell = self.ssh_client.invoke_shell()
            shell.settimeout(1.0)
            dados = b""
            inicio = time.time()
            while time.time() - inicio < 12:
                try:
                    if shell.recv_ready():
                        chunk = shell.recv(4096)
                        if chunk:
                            dados += chunk
                            texto = dados.decode('utf-8', errors='ignore')
                            texto_limpo = re.sub(
                                r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', texto
                            )
                            matches = re.findall(provedor["regex_url"], texto_limpo)
                            for m in matches:
                                if "dashboard" not in m and len(m) > 15:
                                    try:
                                        shell.close()
                                    except:
                                        pass
                                    return m.strip()
                except socket.timeout:
                    pass
                time.sleep(0.3)
            try:
                shell.close()
            except:
                pass
            return None
        except Exception as e:
            self._log(f"⚠️ Erro ao capturar URL via shell: {e}")
            return None

    def _capturar_url_channel(self, provedor):
        """Captura URL via channel normal (srv.us, localhost.run)."""
        try:
            chan = self.transport.open_session()
            chan.settimeout(2)
            buffer = ""
            inicio = time.time()
            while time.time() - inicio < 15:
                try:
                    if chan.recv_ready():
                        data = chan.recv(4096).decode('utf-8', errors='ignore')
                        if data:
                            buffer += data
                            for linha in data.splitlines():
                                if linha.strip():
                                    self._log(f"   📥 {linha.strip()[:120]}")
                            matches = re.findall(provedor["regex_url"], buffer)
                            for m in matches:
                                try:
                                    chan.close()
                                except:
                                    pass
                                return m.strip()
                except socket.timeout:
                    pass
                except Exception:
                    break
                time.sleep(0.2)
            try:
                chan.close()
            except:
                pass
            return None
        except Exception as e:
            self._log(f"⚠️ Erro ao capturar URL via channel: {e}")
            return None

    def _conectar_ssh(self, provedor, key):
        """Faz a conexão SSH de acordo com o tipo de auth do provedor."""
        common = {
            "hostname": provedor["server"],
            "port": provedor["port"],
            "username": provedor["user"],
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": 45,
            "banner_timeout": 45,
            "auth_timeout": 45,
        }

        if provedor["auth"] == "none":
            # localhost.run: autenticação NONE (sem chave, sem senha)
            self._log("🔓 Usando autenticação NONE...")
            try:
                from paramiko.auth_strategy import NoneAuth
                self.ssh_client.connect(auth_strategy=NoneAuth(""), **common)
            except ImportError:
                # Fallback: tenta connect sem auth e depois auth_none
                try:
                    self.ssh_client.connect(**common)
                except paramiko.SSHException:
                    self.ssh_client.get_transport().auth_none(provedor["user"])
        else:
            # Pinggy e srv.us: chave pública
            self.ssh_client.connect(pkey=key, **common)

    def _tentar_provedor(self, provedor, indice):
        self._log(f"")
        self._log(f"━━━ Tentando {provedor['nome']} ({indice+1}/{len(self.PROVEDORES)}) ━━━")
        self._notificar_status("conectando", f"Conectando em {provedor['nome']}...")

        try:
            key = self._load_or_generate_key(provedor)

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self._log(f"🌐 {provedor['server']}:{provedor['port']} (user: {provedor['user'] or 'vazio'})...")
            self._conectar_ssh(provedor, key)
            self._log(f"✅ SSH conectado!")

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)

            # Solicita porta remota (alguns provedores exigem porta específica)
            porta_remota = provedor.get("porta_remota", 0)
            self._log(f"🔌 Solicitando porta remota {porta_remota}...")
            self.transport.request_port_forward('', porta_remota)

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()

            # Captura URL
            if provedor["requer_shell"]:
                url = self._capturar_url_shell(provedor)
            else:
                url = self._capturar_url_channel(provedor)

            if not url:
                self._log(f"⚠️ {provedor['nome']} não retornou URL")
                self._fechar_conexao()
                return None

            self.public_url = url
            self.provedor_atual = provedor
            self.inicio_conexao = time.time()
            self.tentativas_reconexao = 0

            self._log(f"🎉 Túnel ativo em {provedor['nome']}: {url}")
            self._notificar_status(
                "ativo",
                f"✅ Túnel ativo via {provedor['nome']}",
                url
            )
            return url

        except Exception as e:
            self._log(f"❌ {provedor['nome']} falhou: {type(e).__name__}: {e}")
            self._fechar_conexao()
            return None

    def _fechar_conexao(self):
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

    def _monitorar_conexao(self):
        while self.public_url and self.tentativas_reconexao < self.max_tentativas:
            time.sleep(5)
            if self.is_running and self.transport and self.transport.is_active():
                continue
            if self.public_url:
                self._log("⚠️ Conexão caiu! Tentando reconectar...")
                self._notificar_status("reconectando", "Reconectando...")
                self.tentativas_reconexao += 1
                self._fechar_conexao()
                time.sleep(3)
                if self.provedor_atual:
                    idx = self.PROVEDORES.index(self.provedor_atual)
                    resultado = self._tentar_provedor(self.provedor_atual, idx)
                    if resultado:
                        self._log("✅ Reconectado com sucesso!")
                        continue
                self._log("⚠️ Falha na reconexão. Tentando próximo provedor...")

    def start(self):
        if self.public_url and self.is_running:
            self._log("Túnel já está ativo")
            return self.public_url

        self.tentativas_reconexao = 0

        if self.provedor_preferido is not None:
            provedor = self.PROVEDORES[self.provedor_preferido]
            self._log(f"🎯 Modo manual: testando apenas {provedor['nome']}")
            url = self._tentar_provedor(provedor, self.provedor_preferido)
            if url:
                threading.Thread(target=self._monitorar_conexao, daemon=True).start()
                return url
            self._log(f"❌ {provedor['nome']} falhou")
            self._notificar_status("erro", f"❌ {provedor['nome']} indisponível")
            return None

        for i, provedor in enumerate(self.PROVEDORES):
            url = self._tentar_provedor(provedor, i)
            if url:
                threading.Thread(target=self._monitorar_conexao, daemon=True).start()
                return url
            time.sleep(2)

        self._log("❌ Todos os provedores falharam")
        self._notificar_status("erro", "❌ Nenhum provedor disponível")
        return None

    def stop(self):
        self._log("🛑 Parando túnel...")
        self._notificar_status("parado", "Túnel parado")
        self.public_url = None
        self._fechar_conexao()
        self._log("✅ Parado")

    def is_active(self):
        return (self.is_running
                and self.transport is not None
                and self.transport.is_active())

    def tempo_restante(self):
        if not self.inicio_conexao or not self.provedor_atual:
            return None
        limite = self.provedor_atual.get("limite_min", 0)
        if limite == 0:
            return None
        decorrido = time.time() - self.inicio_conexao
        restante = (limite * 60) - decorrido
        return max(0, int(restante))


# ============================================================
# INTERFACE GRÁFICA (FLET)
# ============================================================

tunnel = None
contador_ativo = False


def main(page: ft.Page):
    global tunnel, contador_ativo

    page.title = "PyTunnel Pro"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    txt_host = ft.TextField(
        label="Host local", value="127.0.0.1",
        prefix_icon=ft.Icons.DNS, width=250
    )
    txt_port = ft.TextField(
        label="Porta local", value="8550",
        prefix_icon=ft.Icons.NUMBERS, width=150
    )
    txt_url = ft.TextField(
        label="Link público", read_only=True, value="",
        multiline=False
    )

    btn_copy = ft.IconButton(
        icon=ft.Icons.COPY, tooltip="Copiar link",
        disabled=True,
    )

    def copiar_url(e):
        if txt_url.value:
            page.set_clipboard(txt_url.value)
            page.open(ft.SnackBar(content=ft.Text("✅ Link copiado!")))
            page.update()

    btn_copy.on_click = copiar_url

    logs_field = ft.TextField(
        value="", read_only=True, multiline=True,
        min_lines=10, max_lines=10,
        text_size=11, color="#ccc",
    )
    logs_container = ft.Container(
        content=logs_field, padding=5, bgcolor="#0a0a0a",
        border_radius=6, border=ft.border.all(1, "#333"),
    )

    txt_status = ft.Text("⚪ Pronto", color="#888", size=13)
    status_container = ft.Container(
        content=txt_status, padding=10, bgcolor="#1e1e1e",
        border_radius=6, border=ft.border.all(1, "#333"),
    )

    txt_contador = ft.Text("", color="#4caf50", size=12, weight=ft.FontWeight.BOLD)

    btn_iniciar = ft.ElevatedButton(
        text="🚀 Iniciar", width=160, height=45,
        style=ft.ButtonStyle(bgcolor="#4caf50", color="white"),
    )
    btn_parar = ft.ElevatedButton(
        text="⏹️ Parar", width=160, height=45, disabled=True,
        style=ft.ButtonStyle(bgcolor="#f44336", color="white"),
    )

    def log(msg):
        logs_field.value = (logs_field.value or "") + msg + "\n"
        try:
            page.update()
        except:
            pass

    def status_callback(status, mensagem, detalhes=""):
        if status == "conectando":
            txt_status.value = f"⏳ {mensagem}"
            txt_status.color = "#ff9800"
        elif status == "ativo":
            txt_status.value = f"✅ {mensagem}"
            txt_status.color = "#4caf50"
            if detalhes:
                txt_url.value = detalhes
                btn_copy.disabled = False
        elif status == "reconectando":
            txt_status.value = f"🔄 {mensagem}"
            txt_status.color = "#ff9800"
        elif status == "erro":
            txt_status.value = mensagem
            txt_status.color = "#ff5722"
        elif status == "parado":
            txt_status.value = "⚪ Pronto"
            txt_status.color = "#888"

        try:
            page.update()
        except:
            pass

    def atualizar_contador():
        global tunnel, contador_ativo
        while contador_ativo and tunnel:
            try:
                restante = tunnel.tempo_restante()
                if restante is not None:
                    min_r = restante // 60
                    seg_r = restante % 60
                    txt_contador.value = f"⏱️ Expira em: {min_r:02d}:{seg_r:02d}"
                    if restante < 300:
                        txt_contador.color = "#ff5722"
                    elif restante < 600:
                        txt_contador.color = "#ff9800"
                    else:
                        txt_contador.color = "#4caf50"
                    page.update()
                else:
                    txt_contador.value = ""
                    page.update()
            except:
                pass
            time.sleep(1)

    def on_iniciar(e):
        global tunnel, contador_ativo

        btn_iniciar.disabled = True
        btn_parar.disabled = False
        txt_url.value = ""
        txt_contador.value = ""
        logs_field.value = ""
        status_callback("conectando", "Conectando...")
        page.update()

        try:
            porta = int(txt_port.value)
        except:
            log("❌ Porta inválida")
            status_callback("erro", "❌ Porta inválida")
            btn_iniciar.disabled = False
            return

        tunnel = PyTunnel(
            local_host=txt_host.value.strip(),
            local_port=porta,
        )
        tunnel.set_log_callback(log)
        tunnel.set_status_callback(status_callback)

        def worker():
            url = tunnel.start()
            if not url:
                btn_iniciar.disabled = False
                btn_parar.disabled = True
            page.update()

        threading.Thread(target=worker, daemon=True).start()

        contador_ativo = True
        threading.Thread(target=atualizar_contador, daemon=True).start()

    def on_parar(e):
        global tunnel, contador_ativo
        contador_ativo = False
        try:
            if tunnel:
                tunnel.stop()
                tunnel = None
            txt_url.value = ""
            txt_contador.value = ""
            btn_copy.disabled = True
            btn_iniciar.disabled = False
            btn_parar.disabled = True
            status_callback("parado", "Pronto")
        except Exception as ex:
            log(f"❌ {ex}")
        page.update()

    btn_iniciar.on_click = on_iniciar
    btn_parar.on_click = on_parar

    page.add(
        ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LINK, size=28, color="#4caf50"),
                ft.Text("PyTunnel Pro", size=22, weight=ft.FontWeight.BOLD),
            ]),
            ft.Text("Pinggy • localhost.run • srv.us",
                    size=11, color="#888"),
            ft.Divider(),
            ft.Text("📍 Servidor Local", weight=ft.FontWeight.BOLD, size=14),
            ft.Row([txt_host, txt_port]),
            ft.Container(height=5),
            ft.Text("🔗 Link Público", weight=ft.FontWeight.BOLD, size=14),
            ft.Row([txt_url, btn_copy],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            status_container,
            ft.Row([txt_contador], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=5),
            ft.Row([btn_iniciar, btn_parar],
                   alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Text("📋 Logs", weight=ft.FontWeight.BOLD, size=14),
            logs_container,
        ])
    )


if __name__ == "__main__":
    ft.app(target=main)
