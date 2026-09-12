"""
PyTunnel - Túnel reverso SSH. Versão DEBUG com logs detalhados.
"""
import paramiko
import select
import socket
import threading
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
        """Carrega ou gera chave Ed25519."""
        self._log("📁 Pasta de dados: " + os.path.dirname(self.key_path))
        self._log("📁 Caminho da chave: " + self.key_path)
        self._log("📁 Existe? " + str(os.path.exists(self.key_path)))

        if os.path.exists(self.key_path):
            self._log("🔑 Carregando chave existente...")
            try:
                import io
                with open(self.key_path, "r") as f:
                    key_data = f.read()
                key = paramiko.Ed25519Key.from_private_key(io.StringIO(key_data))
                self._log("✅ Chave carregada")
                return key
            except Exception as e:
                self._log(f"⚠️ Erro: {e}")
                try:
                    os.remove(self.key_path)
                except:
                    pass

        self._log("🔑 Gerando nova chave Ed25519...")
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives import serialization
            import io

            self._log("    Gerando chave na memória...")
            private_key = ed25519.Ed25519PrivateKey.generate()

            self._log("    Serializando...")
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_str = private_bytes.decode("utf-8")

            self._log("    Salvando no disco...")
            pasta = os.path.dirname(self.key_path)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta, exist_ok=True)
            with open(self.key_path, "w") as f:
                f.write(key_str)
            self._log("✅ Chave salva")

            self._log("    Carregando de volta...")
            return paramiko.Ed25519Key.from_private_key(io.StringIO(key_str))
        except Exception as e:
            import traceback
            self._log(f"❌ Erro Ed25519: {type(e).__name__}: {e}")
            for line in traceback.format_exc().splitlines():
                self._log(line)
            self._log("⚠️ Tentando fallback RSA...")
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
            self._log(f"❌ Local falhou: {e}")
            try: chan.close()
            except: pass
            return
        try:
            while True:
                r, _, _ = select.select([sock, chan], [], [], 30)
                if chan in r:
                    data = chan.recv(4096)
                    if not data: break
                    sock.sendall(data)
                if sock in r:
                    data = sock.recv(4096)
                    if not data: break
                    chan.sendall(data)
        except Exception:
            pass
        finally:
            try: chan.close()
            except: pass
            try: sock.close()
            except: pass

    def _loop_aceitar(self):
        while self.is_running and self.transport and self.transport.is_active():
            try:
                chan = self.transport.accept(1)
                if chan is None: continue
                self._channels.append(chan)
                threading.Thread(target=self._handler_conexao, args=(chan,), daemon=True).start()
            except Exception:
                break

    def start(self):
        if self.is_running:
            return self.public_url

        try:
            self._log("▶️ start() chamado")
            self._log("🔑 Preparando chave...")
            key = self._load_or_generate_key()
            self._log("✅ Chave pronta")

            self._log(f"🌐 Importando paramiko...")
            import paramiko as pk
            self._log(f"✅ paramiko {pk.__version__}")

            self._log(f"🌐 Criando SSHClient...")
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._log(f"✅ SSHClient criado")

            self._log(f"🌐 Conectando em {self.ssh_server}:22 (usuário: {self.ssh_user})...")
            inicio = time.time()
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
            dur = round(time.time() - inicio, 2)
            self._log(f"✅ SSH conectado em {dur}s!")

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)
            self._log("✅ Transport configurado")

            self._log(f"🔌 Solicitando porta remota {self.remote_port}...")
            self.transport.request_port_forward("", self.remote_port)
            self._log("✅ Porta remota OK")

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()
            self._log("✅ Loop aceitar iniciado")

            self.public_url = "https://(verifique notificação do serviço)"
            self._log(f"🎉 TÚNEL ATIVO!")
            return self.public_url

        except paramiko.AuthenticationException as e:
            self._log(f"❌ Auth falhou: {e}")
            self.stop(); return None
        except paramiko.SSHException as e:
            self._log(f"❌ SSH falhou: {e}")
            self.stop(); return None
        except socket.timeout:
            self._log(f"❌ Timeout ao conectar")
            self.stop(); return None
        except Exception as e:
            import traceback
            self._log(f"❌ Erro: {type(e).__name__}: {e}")
            for line in traceback.format_exc().splitlines():
                self._log(line)
            self.stop(); return None

    def stop(self):
        self._log("🛑 Parando...")
        self.is_running = False
        for chan in self._channels:
            try: chan.close()
            except: pass
        self._channels.clear()
        if self.transport:
            try: self.transport.close()
            except: pass
            self.transport = None
        if self.ssh_client:
            try: self.ssh_client.close()
            except: pass
            self.ssh_client = None
        self._log("✅ Parado")

    def is_active(self):
        return (self.is_running and self.transport is not None
                and self.transport.is_active())
