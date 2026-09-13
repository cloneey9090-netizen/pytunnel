import paramiko
import select
import socket
import threading
import hashlib
import base64
import os
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PyTunnel")


class PyTunnel:
    """
    Túnel reverso SSH via Pinggy (a.pinggy.io:443). Expõe um servidor local
    para a internet de forma estável, ideal para Android.
    """

    def __init__(self, local_host="127.0.0.1", local_port=8550,
                 remote_port=0, ssh_server="a.pinggy.io", ssh_user="http",
                 key_path=None):
        self.local_host = local_host
        self.local_port = local_port
        self.remote_port = remote_port  # Pinggy usa 0 para URL automática
        self.ssh_server = ssh_server
        self.ssh_user = ssh_user

        if key_path is None:
            pasta_dados = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(pasta_dados, "tunnel_key")
        self.key_path = key_path

        self.ssh_client = None
        self.transport = None
        self.is_running = False
        self.public_url = None
        self._thread = None
        self._channels = []
        self.log_callback = None

    def set_log_callback(self, callback):
        """Define uma função para receber os logs em tempo real na UI."""
        self.log_callback = callback

    def _log(self, mensagem):
        """Envia o log para o terminal e para a interface gráfica."""
        logger.info(mensagem)
        if self.log_callback:
            try:
                self.log_callback(mensagem)
            except:
                pass

    def _load_or_generate_key(self):
        """Carrega a chave SSH RSA existente ou gera uma nova."""
        if os.path.exists(self.key_path):
            self._log(f"🔑 Carregando chave SSH existente...")
            try:
                return paramiko.RSAKey.from_private_key_file(self.key_path)
            except Exception as e:
                self._log(f"⚠️ Chave corrompida, gerando nova: {e}")
                try:
                    os.remove(self.key_path)
                except:
                    pass

        self._log("🔑 Gerando nova chave SSH RSA (pode levar alguns segundos)...")
        key = paramiko.RSAKey.generate(2048)
        try:
            pasta = os.path.dirname(self.key_path)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta, exist_ok=True)
            key.write_private_key_file(self.key_path)
            self._log(f"✅ Chave salva em: {self.key_path}")
        except Exception as e:
            self._log(f"⚠️ Não foi possível salvar a chave: {e}")
        return key

    def _calcular_url(self, key):
        """Calcula a URL pública baseada no hash da chave."""
        try:
            pubkey_bytes = key.asbytes()
        except Exception:
            pubkey_bytes = key.get_base64().encode()

        hasher = hashlib.sha256()
        hasher.update(pubkey_bytes)
        digest = hasher.digest()[:8]
        subdomain = base64.b32encode(digest).decode().lower().rstrip('=')
        url = f"https://{subdomain}.lhr.life"
        self._log(f"🌐 URL calculada: {url}")
        return url

    def _handler_conexao(self, chan):
        """Encaminha dados entre o canal SSH e o servidor local."""
        sock = socket.socket()
        try:
            sock.connect((self.local_host, self.local_port))
        except Exception as e:
            self._log(f"❌ Falha ao conectar em {self.local_host}:{self.local_port}: {e}")
            try:
                chan.close()
            except:
                pass
            return

        try:
            while True:
                r, _, _ = select.select([sock, chan], [], [], 30)
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
        """Aceita conexões no túnel enquanto estiver ativo."""
        while self.is_running and self.transport and self.transport.is_active():
            try:
                chan = self.transport.accept(1)
                if chan is None:
                    continue
                self._channels.append(chan)
                threading.Thread(
                    target=self._handler_conexao,
                    args=(chan,),
                    daemon=True
                ).start()
            except Exception:
                if self.is_running:
                    pass
                break

    def start(self):
        """Inicia o túnel. Retorna a URL pública ou None se falhar."""
        if self.is_running:
            self._log("⚠️ Túnel já está ativo.")
            return self.public_url

        try:
            key = self._load_or_generate_key()
            self.public_url = self._calcular_url(key)

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self._log(f"🌐 Conectando em {self.ssh_server}:443...")
            self.ssh_client.connect(
                hostname=self.ssh_server,
                port=443,  # Porta 443 para burlar firewalls de rede/Android
                username=self.ssh_user,
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=20,
                banner_timeout=20,
            )

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)
            self._log("✅ SSH conectado!")

            self._log(f"🔌 Solicitando porta remota {self.remote_port}...")
            self.transport.request_port_forward('', self.remote_port)
            self._log("✅ Porta remota solicitada")

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()

            self._log(f"🎉 Túnel ativo! URL: {self.public_url}")
            return self.public_url

        except paramiko.AuthenticationException as e:
            self._log(f"❌ Erro de autenticação: {e}")
            self.stop()
            return None
        except paramiko.SSHException as e:
            self._log(f"❌ Erro SSH: {e}")
            self.stop()
            return None
        except socket.timeout:
            self._log(f"❌ Timeout ao conectar em {self.ssh_server}")
            self.stop()
            return None
        except Exception as e:
            self._log(f"❌ Erro ao iniciar túnel: {type(e).__name__}: {e}")
            self.stop()
            return None

    def stop(self):
        """Para o túnel e fecha todos os recursos."""
        self._log("🛑 Parando túnel...")
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

        self._log("✅ Túnel parado.")

    def is_active(self):
        """Verifica se o túnel está ativo."""
        return (self.is_running
                and self.transport is not None
                and self.transport.is_active())
