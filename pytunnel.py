"""
PyTunnel - Túnel reverso SSH para expor servidores locais à internet.
Usa serviços gratuitos (srv.us, localhost.run) como relay.
"""
import paramiko
import select
import socket
import threading
import hashlib
import base64
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PyTunnel")


class PyTunnel:
    def __init__(self, local_host="127.0.0.1", local_port=8550,
                 remote_port=80, ssh_server="localhost.run", ssh_user="nokey",
                 key_path=None):
        self.local_host = local_host
        self.local_port = local_port
        self.remote_port = remote_port
        self.ssh_server = ssh_server
        self.ssh_user = ssh_user

        if key_path is None:
            pasta_dados = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(pasta_dados, "tunnel_key_ed25519")
        self.key_path = key_path

        self.ssh_client = None
        self.transport = None
        self.is_running = False
        self.public_url = None
        self._thread = None
        self._channels = []
        self._log_callback = None

    def set_log_callback(self, callback):
        self._log_callback = callback

    def _log(self, msg):
        logger.info(msg)
        if self._log_callback:
            try:
                self._log_callback(msg)
            except:
                pass

    def _load_or_generate_key(self):
        """Carrega ou gera chave Ed25519 (muito mais rápida que RSA)."""
        if os.path.exists(self.key_path):
            self._log("🔑 Carregando chave Ed25519...")
            try:
                with open(self.key_path, "r") as f:
                    key_data = f.read()
                # Tenta carregar como Ed25519
                import io
                key = paramiko.Ed25519Key.from_private_key(io.StringIO(key_data))
                self._log("✅ Chave carregada")
                return key
            except Exception as e:
                self._log(f"⚠️ Chave corrompida: {e}")
                try:
                    os.remove(self.key_path)
                except:
                    pass

        self._log("🔑 Gerando nova chave Ed25519...")
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives import serialization

            private_key = ed25519.Ed25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_str = private_bytes.decode("utf-8")

            # Salva
            pasta = os.path.dirname(self.key_path)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta, exist_ok=True)
            with open(self.key_path, "w") as f:
                f.write(key_str)

            self._log("✅ Chave gerada e salva")

            import io
            return paramiko.Ed25519Key.from_private_key(io.StringIO(key_str))
        except Exception as e:
            self._log(f"❌ Erro ao gerar Ed25519: {e}")
            # Fallback: tenta RSA se Ed25519 falhar
            self._log("⚠️ Tentando fallback com RSA...")
            key = paramiko.RSAKey.generate(2048)
            try:
                key.write_private_key_file(self.key_path)
            except:
                pass
            return key

    def _handler_conexao(self, chan):
        sock = socket.socket()
        try:
            sock.connect((self.local_host, self.local_port))
        except Exception as e:
            self._log(f"❌ Falha ao conectar em {self.local_host}:{self.local_port}")
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
                break

    def start(self):
        if self.is_running:
            return self.public_url

        try:
            self._log("🔑 Preparando chave SSH...")
            key = self._load_or_generate_key()
            self._log("✅ Chave pronta")

            self._log(f"🌐 Conectando em {self.ssh_server}:22...")
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Timeouts curtos para não travar
            self.ssh_client.connect(
                hostname=self.ssh_server,
                port=22,
                username=self.ssh_user,
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
            )
            self._log("✅ SSH conectado!")

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)

            self._log(f"🔌 Solicitando porta remota {self.remote_port}...")
            self.transport.request_port_forward("", self.remote_port)
            self._log("✅ Porta remota solicitada")

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()

            # Para localhost.run, a URL vem na notificação do serviço
            # Mas usamos uma URL placeholder para mostrar algo
            self.public_url = f"https://(verifique console)"
            self._log(f"✅ Túnel ativo!")
            return self.public_url

        except paramiko.AuthenticationException as e:
            self._log(f"❌ Auth falhou: {e}")
            self.stop()
            return None
        except paramiko.SSHException as e:
            self._log(f"❌ SSH falhou: {e}")
            self.stop()
            return None
        except socket.timeout:
            self._log(f"❌ Timeout ao conectar")
            self.stop()
            return None
        except Exception as e:
            self._log(f"❌ Erro: {type(e).__name__}: {e}")
            self.stop()
            return None

    def stop(self):
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
        self._log("✅ Parado")

    def is_active(self):
        return (self.is_running
                and self.transport is not None
                and self.transport.is_active())
