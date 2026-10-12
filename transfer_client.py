"""Protocol adapters for AetherFTP."""
import ftplib
import os
import ssl
import stat


class ReuseFTP_TLS(ftplib.FTP_TLS):
    """Reuse the authenticated control session for protected data sockets."""
    def ntransfercmd(self, cmd, rest=None):
        report = getattr(self, 'on_status', None)
        if report: report('Opening FTP data connection')
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            try:
                if report: report('Data TLS handshake: reusing control session')
                conn = self.context.wrap_socket(conn, server_hostname=self.host,
                                                session=self.sock.session)
                if report: report('Protected data connection established')
            except Exception:
                conn.close()
                raise
        return conn, size


class Client:
    def __init__(self):
        self.conn=None; self.transport=None; self.kind=None
        self.on_status = None
        self.connection_stage = 'Not connected'
    def step(self, message):
        self.connection_stage = message
        if self.on_status: self.on_status(message)
    def connect(self, host, port, username, password, protocol):
        self.close()
        if protocol not in ('FTP', 'FTPS', 'FTPES', 'SFTP'):
            raise ValueError('Unsupported protocol')
        if protocol=='SFTP':
            try: import paramiko
            except ImportError as exc: raise RuntimeError('SFTP requires paramiko: pip install paramiko') from exc
            ssh=paramiko.SSHClient(); ssh.load_system_host_keys(); ssh.load_host_keys(os.path.expanduser('~/.ssh/known_hosts')) if os.path.exists(os.path.expanduser('~/.ssh/known_hosts')) else None
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
            try:
                self.step('SSH connection and authentication')
                ssh.connect(hostname=host,port=port,username=username,password=password,timeout=20,banner_timeout=20,auth_timeout=20,look_for_keys=False,allow_agent=False)
                self.step('Opening SFTP subsystem')
                self.conn=ssh.open_sftp(); self.transport=ssh
            except Exception:
                ssh.close(); raise
        else:
            tls = protocol in ('FTPS', 'FTPES')
            cls=ReuseFTP_TLS if tls else ftplib.FTP
            c=cls(context=ssl.create_default_context()) if tls else cls()
            if tls: c.on_status = self.step
            try:
                self.step('Connecting TCP socket')
                c.connect(host,port,timeout=20)
                self.step('TCP connected; server greeting received')
                if tls:
                    self.step('Negotiating AUTH TLS; verifying certificate')
                    c.auth()
                    self.step('TLS established: ' + str(c.sock.version()))
                self.step('Authenticating user')
                c.login(username,password)
                self.step('Login accepted')
                if tls:
                    self.step('Protecting data channel: PBSZ 0 / PROT P')
                    c.prot_p()
                    self.step('Data protection enabled; TLS session reuse enabled')
                self.step('Setting binary transfer mode')
                c.voidcmd('TYPE I')
            except Exception:
                c.close(); raise
            self.conn=c
        self.kind=protocol
        self.step('Connection ready')
    def listdir(self,path):
        if self.kind=='SFTP':
            import stat
            return sorted([(a.filename,stat.S_ISDIR(a.st_mode),a.st_size) for a in self.conn.listdir_attr(path)],key=lambda x:(not x[1],x[0].lower()))
        entries=[]
        try:
            for name,facts in self.conn.mlsd(path):
                if name in ('.','..'):continue
                entries.append((name,facts.get('type')=='dir',int(facts.get('size','0'))))
        except (ftplib.error_perm,AttributeError):
            entries=[]
            old=self.conn.pwd(); self.conn.cwd(path); base=self.conn.pwd()
            try:
                for name in self.conn.nlst():
                    short=name.rstrip('/').split('/')[-1]
                    if short in ('.','..'):continue
                    isdir=False
                    try:self.conn.cwd(name); isdir=True; self.conn.cwd(base)
                    except ftplib.error_perm:pass
                    entries.append((short,isdir,0))
            finally:self.conn.cwd(old)
        return sorted(entries,key=lambda x:(not x[1],x[0].lower()))
    def ensure_directory(self, path):
        """Accept an existing directory, but never suppress a create failure."""
        if self.kind == 'SFTP':
            try:
                self.conn.mkdir(path)
            except OSError as error:
                try: existing = self.conn.stat(path)
                except OSError: raise error
                if not stat.S_ISDIR(existing.st_mode): raise error
        else:
            try:
                self.conn.mkd(path)
            except ftplib.error_perm as error:
                previous = self.conn.pwd()
                try:
                    self.conn.cwd(path)
                except ftplib.error_perm:
                    raise error
                finally:
                    self.conn.cwd(previous)
    def download(self,remote,local,callback,resume=False):
        if self.kind != 'SFTP': self.conn.voidcmd('TYPE I')
        offset = os.path.getsize(local) if resume and os.path.exists(local) else 0
        total = self.conn.stat(remote).st_size if self.kind=='SFTP' else self.conn.size(remote)
        if total is None:
            if resume: raise ValueError('Server did not provide a resume size')
            total = 0
        if resume and offset > total: raise ValueError('Local file exceeds remote size')
        callback(offset, total)
        if self.kind=='SFTP':
            with self.conn.open(remote, 'rb') as src, open(local, 'ab' if resume else 'wb') as dst:
                src.seek(offset)
                while data := src.read(65536):
                    dst.write(data); offset += len(data); callback(offset,total)
        else:
            with open(local,'ab' if resume else 'wb') as f:
                count=[offset]
                def block(data):
                    f.write(data); count[0]+=len(data); callback(count[0],total)
                self.conn.retrbinary('RETR '+remote,block,rest=offset or None)
    def upload(self,local,remote,callback,resume=False):
        if self.kind != 'SFTP': self.conn.voidcmd('TYPE I')
        offset = 0
        if resume:
            offset = self.conn.stat(remote).st_size if self.kind=='SFTP' else self.conn.size(remote)
        total = os.path.getsize(local)
        if offset > total: raise ValueError('Remote file exceeds local size')
        callback(offset, total)
        if self.kind=='SFTP':
            with open(local, 'rb') as src, self.conn.open(remote, 'r+b' if resume else 'wb') as dst:
                src.seek(offset); dst.seek(offset)
                while data := src.read(65536):
                    dst.write(data); offset += len(data); callback(offset,total)
        else:
            with open(local,'rb') as f:
                f.seek(offset)
                count=[offset]
                def block(data):count[0]+=len(data);callback(count[0],os.path.getsize(local))
                self.conn.storbinary('STOR '+remote,f,callback=block,rest=offset or None)
    def close(self):
        for obj in (self.conn,self.transport):
            if obj:
                try:obj.close()
                except Exception:pass
        self.conn=None;self.transport=None;self.kind=None
