"""
PyTunnel - Túnel reverso SSH para expor servidores locais à internet.
Usa o serviço gratuito srv.us (código aberto).
"""
import paramiko
import select
import socket
import threading
import hashlib
import base64
import os
import time
import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PyTunnel")


class PyTunnel:
    """
    Túnel reverso SSH via srv.us. Expõe um servidor local (host:porta)
    para a internet com uma URL HTTPS pública e estável.
    """

    def __init__(self, local_host="127.0.0.1", local_port=8550,
                 remote_port=80, ssh_server="srv.us", ssh_user="",
                 key_path=None):
        self.local_host = local_host
        self.local_port = local_port
        self.remote_port = remote_port
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

    def _load_or_generate_key(self):
        """Carrega a chave SSH existente ou gera uma nova."""
        if os.path.exists(self.key_path):
            logger.info(f"Carregando chave SSH: {self.key_path}")
            try:
                return paramiko.RSAKey.from_private_key_file(self.key_path)
            except Exception as e:
                logger.warning(f"Chave corrompida, gerando nova: {e}")
                try:
                    os.remove(self.key_path)
                except:
                    pass

        logger.info("Gerando nova chave SSH (pode levar alguns segundos)...")
        key = paramiko.RSAKey.generate(2048)
        try:
            pasta = os.path.dirname(self.key_path)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta, exist_ok=True)
            key.write_private_key_file(self.key_path)
            logger.info(f"Chave salva em: {self.key_path}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar a chave: {e}")
        return key

    def _calcular_url(self, key):
        """
        Calcula a URL pública determinística do srv.us.
        Baseado no código-fonte do srv.us:
        SHA256(chave_pública + 0x00 + porta_remota)[:16] em base32 minúsculo.
        """
        try:
            pubkey_bytes = key.asbytes()
        except Exception:
            pubkey_bytes = key.get_base64().encode()

        hasher = hashlib.sha256()
        hasher.update(pubkey_bytes)
        hasher.update(b'\x00')
        hasher.update(str(self.remote_port).encode())
        digest = hasher.digest()[:16]
        encoded = base64.b32encode(digest).decode().lower().rstrip('=')
        url = f"https://{encoded}.srv.us/"
        logger.info(f"URL calculada: {url}")
        return url

    def _handler_conexao(self, chan):
        """Encaminha dados entre o canal SSH e o servidor local."""
        sock = socket.socket()
        try:
            sock.connect((self.local_host, self.local_port))
        except Exception as e:
            logger.error(f"Falha ao conectar em {self.local_host}:{self.local_port}: {e}")
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
        except Exception as e:
            logger.debug(f"Conexão encerrada: {e}")
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
            except Exception as e:
                if self.is_running:
                    logger.debug(f"Erro ao aceitar conexão: {e}")
                break

    def start(self):
        """Inicia o túnel. Retorna a URL pública ou None se falhar."""
        if self.is_running:
            logger.warning("Túnel já está ativo.")
            return self.public_url

        try:
            key = self._load_or_generate_key()
            self.public_url = self._calcular_url(key)

            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            logger.info(f"Conectando em {self.ssh_server}...")
            self.ssh_client.connect(
                hostname=self.ssh_server,
                port=22,
                username=self.ssh_user,
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=20,
                banner_timeout=20,
            )

            self.transport = self.ssh_client.get_transport()
            self.transport.set_keepalive(30)

            logger.info(f"Solicitando porta remota {self.remote_port}...")
            self.transport.request_port_forward("", self.remote_port)

            self.is_running = True
            self._thread = threading.Thread(target=self._loop_aceitar, daemon=True)
            self._thread.start()

            logger.info(f"✅ Túnel ativo! URL: {self.public_url}")
            return self.public_url

        except Exception as e:
            logger.error(f"❌ Erro ao iniciar túnel: {e}")
            self.stop()
            return None

    def stop(self):
        """Para o túnel e fecha todos os recursos."""
        logger.info("Parando o túnel...")
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

        logger.info("Túnel parado.")

    def is_active(self):
        """Verifica se o túnel está ativo."""
        return (self.is_running
                and self.transport is not None
                and self.transport.is_active())
