"""AetherFTP: dark desktop FTP/FTPS/SFTP client."""
import ftplib
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from server_book import load_profiles, save_profiles, encrypt_password, decrypt_password

BG='#0b101b'; PANEL='#151d2c'; INPUT='#202b3c'; FG='#e4eaf5'; MUTED='#9caac1'; PURPLE='#a78bfa'; CYAN='#38bdf8'

class Client:
    def __init__(self):
        self.conn=None; self.transport=None; self.kind=None
    def connect(self, host, port, username, password, protocol):
        self.close()
        if protocol=='SFTP':
            try: import paramiko
            except ImportError as exc: raise RuntimeError('SFTP requires paramiko: pip install paramiko') from exc
            ssh=paramiko.SSHClient(); ssh.load_system_host_keys(); ssh.load_host_keys(os.path.expanduser('~/.ssh/known_hosts')) if os.path.exists(os.path.expanduser('~/.ssh/known_hosts')) else None
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
            ssh.connect(hostname=host,port=port,username=username,password=password,timeout=20,look_for_keys=False,allow_agent=False)
            self.transport=ssh; self.conn=ssh.open_sftp()
        else:
            cls=ftplib.FTP_TLS if protocol=='FTPS' else ftplib.FTP
            c=cls(); c.connect(host,port,timeout=20); c.login(username,password)
            if protocol=='FTPS': c.prot_p()
            self.conn=c
        self.kind=protocol
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
            old=self.conn.pwd(); self.conn.cwd(path)
            try:
                for name in self.conn.nlst():
                    short=name.rstrip('/').split('/')[-1]
                    if short in ('.','..'):continue
                    isdir=False
                    try:self.conn.cwd(name); isdir=True; self.conn.cwd(path)
                    except ftplib.error_perm:pass
                    entries.append((short,isdir,0))
            finally:self.conn.cwd(old)
        return sorted(entries,key=lambda x:(not x[1],x[0].lower()))
    def download(self,remote,local,callback):
        if self.kind=='SFTP': self.conn.get(remote,local,callback=callback)
        else:
            with open(local,'wb') as f:
                count=[0]
                def block(data):
                    f.write(data); count[0]+=len(data); callback(count[0],0)
                self.conn.retrbinary('RETR '+remote,block)
    def upload(self,local,remote,callback):
        if self.kind=='SFTP': self.conn.put(local,remote,callback=callback)
        else:
            with open(local,'rb') as f:
                count=[0]
                def block(data):count[0]+=len(data);callback(count[0],os.path.getsize(local))
                self.conn.storbinary('STOR '+remote,f,callback=block)
    def close(self):
        for obj in (self.conn,self.transport):
            if obj:
                try:obj.close()
                except Exception:pass
        self.conn=None;self.transport=None;self.kind=None

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('AetherFTP | Engineering File Transfer'); self.geometry('1180x760');self.minsize(900,580)
        self.configure(bg=BG);self.client=Client();self.events=queue.Queue();self.lock=threading.Lock();self.busy=False
        self.remote_path='/';self.local_path=Path.home();self.entries={}
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('Treeview',background=PANEL,foreground=FG,fieldbackground=PANEL,rowheight=29,borderwidth=0,font=('Segoe UI',10))
        style.map('Treeview',background=[('selected','#493b75')]);style.configure('Treeview.Heading',background=INPUT,foreground=FG,font=('Segoe UI',10,'bold'),relief='flat')
        self.make_ui();self.refresh_local();self.after(80,self.pump);self.protocol_changed()
        self.protocol.trace_add('write',lambda *_:self.protocol_changed())
        self.protocol_changed()
        self.protocol_menu.configure(bg=INPUT,fg=FG,activebackground='#44365e',activeforeground=FG,highlightthickness=0)
        self.protocol_menu['menu'].configure(bg=INPUT,fg=FG)
        self.protocol.set('SFTP')
    def label(self,parent,text,color=FG,size=10,bold=False,**kw):
        return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,font=('Segoe UI',size,'bold' if bold else 'normal'),**kw)
    def btn(self,parent,text,command,color=INPUT):
        return tk.Button(parent,text=text,command=command,bg=color,fg=FG,activebackground='#4c3b70',activeforeground='white',relief='flat',padx=13,pady=9,cursor='hand2',font=('Segoe UI',10,'bold'))
    def make_ui(self):
        top=tk.Frame(self,bg=BG);top.pack(fill='x',padx=22,pady=(18,12))
        self.label(top,'◈  AETHER / FTP',PURPLE,20,True).pack(side='left');self.label(top,'   ENGINEERING FILE TRANSFER',MUTED,9).pack(side='left',pady=9)
        bar=tk.Frame(self,bg=PANEL,padx=12,pady=12);bar.pack(fill='x',padx=22)
        self.protocol=tk.StringVar(value='SFTP');self.protocol_menu=tk.OptionMenu(bar,self.protocol,'SFTP','FTPS','FTP');self.protocol_menu.pack(side='left',padx=(0,8))
        self.host=self.field(bar,'Host / IP','192.168.1.100',22);self.port=self.field(bar,'Port','22',6)
        self.user=self.field(bar,'Username','',14);self.password=self.field(bar,'Password','',14,show='*')
        self.btn(bar,'SERVER BOOK',self.open_server_book).pack(side='left',padx=5)
        self.btn(bar,'CONNECT',self.connect,PURPLE).pack(side='left',padx=5)
        self.btn(bar,'DISCONNECT',self.disconnect).pack(side='left')
        self.status=tk.StringVar(value='●  OFFLINE');self.label(self,self.status,MUTED,10,True).pack(anchor='w',padx=25,pady=10)
        panes=tk.PanedWindow(self,orient='horizontal',bg=BG,sashwidth=7,bd=0);panes.pack(fill='both',expand=True,padx=22)
        for side in ('local','remote'):
            frame=tk.Frame(panes,bg=PANEL,padx=10,pady=10);panes.add(frame,minsize=280)
            header=tk.Frame(frame,bg=PANEL);header.pack(fill='x')
            self.label(header,'◧  '+side.upper()+' FILESYSTEM',CYAN if side=='local' else PURPLE,11,True).pack(side='left')
            self.btn(header,'↻',self.refresh_local if side=='local' else self.refresh_remote).pack(side='right')
            p=tk.StringVar(value=str(self.local_path) if side=='local' else '/');setattr(self,side+'_display',p)
            entry=tk.Entry(frame,textvariable=p,bg=INPUT,fg=FG,insertbackground=FG,relief='flat',font=('Consolas',10));entry.pack(fill='x',pady=(10,8),ipady=8)
            entry.bind('<Return>',lambda e,s=side:self.go_path(s))
            tree=ttk.Treeview(frame,columns=('size',),show='tree headings',selectmode='browse');tree.heading('#0',text='NAME');tree.heading('size',text='SIZE');tree.column('#0',width=300);tree.column('size',width=90,anchor='e');tree.pack(fill='both',expand=True)
            tree.bind('<Double-1>',lambda e,s=side:self.open_item(s))
            setattr(self,side+'_tree',tree)
            foot=tk.Frame(frame,bg=PANEL);foot.pack(fill='x',pady=(8,0))
            if side=='local':self.btn(foot,'UPLOAD  →',self.upload).pack(side='right')
            else:self.btn(foot,'←  DOWNLOAD',self.download).pack(side='left')
        bottom=tk.Frame(self,bg=PANEL,padx=12,pady=10);bottom.pack(fill='x',padx=22,pady=(12,18))
        self.label(bottom,'TRANSFER ACTIVITY / EVENT LOG',PURPLE,10,True).pack(anchor='w')
        self.progress=ttk.Progressbar(bottom,mode='determinate');self.progress.pack(fill='x',pady=8)
        self.logbox=tk.Text(bottom,height=5,bg=BG,fg=MUTED,insertbackground=FG,relief='flat',font=('Consolas',9),state='disabled');self.logbox.pack(fill='x')
        self.log('Ready. SFTP is recommended. Plain FTP is unencrypted.')
    def field(self,parent,name,default,width,show=None):
        wrap=tk.Frame(parent,bg=PANEL);wrap.pack(side='left',padx=5)
        self.label(wrap,name,MUTED,8).pack(anchor='w')
        ent=tk.Entry(wrap,width=width,bg=INPUT,fg=FG,insertbackground=FG,relief='flat',show=show,font=('Consolas',10));ent.insert(0,default);ent.pack(ipady=7)
        return ent
    def protocol_changed(self):
        self.port.delete(0,'end');self.port.insert(0,{'SFTP':'22','FTPS':'21','FTP':'21'}[self.protocol.get()])
    def log(self,message):
        self.logbox.configure(state='normal');self.logbox.insert('end',message+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')
    def work(self,fn):
        if self.busy:self.log('Another operation is still running.');return
        self.busy=True
        def runner():
            try:
                with self.lock:fn()
            except Exception as exc:self.events.put(('error',str(exc)))
            finally:self.events.put(('idle',))
        threading.Thread(target=runner,daemon=True).start()
    def pump(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event[0]
                if kind=='log':self.log(event[1])
                elif kind=='error':self.log('ERROR: '+event[1]);self.status.set('●  ERROR')
                elif kind=='idle':self.busy=False
                elif kind=='connected':self.status.set('●  CONNECTED  |  '+event[1]);self.log('Connected using '+event[1]);self.refresh_remote()
                elif kind=='remote':
                    self.remote_path=event[1];self.remote_display.set(event[1]);self.entries={}
                    self.remote_tree.delete(*self.remote_tree.get_children())
                    if event[1]!='/':self.remote_tree.insert('','end',iid='..',text='📁  ..',values=('PARENT',))
                    for i,(name,isdir,size) in enumerate(event[2]):
                        iid='f'+str(i);self.entries[iid]=(name,isdir)
                        self.remote_tree.insert('','end',iid=iid,text=('📁  ' if isdir else '◻  ')+name,values=('<DIR>' if isdir else self.size(size),))
                elif kind=='progress':self.progress['value']=event[1]
                elif kind=='local_refresh':self.refresh_local()
        except queue.Empty:pass
        self.after(80,self.pump)
    @staticmethod
    def size(n):
        for unit in ('B','KB','MB','GB','TB'):
            if n<1024:return f'{n:.0f} {unit}' if unit=='B' else f'{n:.1f} {unit}'
            n/=1024
        return f'{n:.1f} PB'
    def connect(self):
        host=self.host.get().strip();username=self.user.get();password=self.password.get();proto=self.protocol.get()
        try:
            port=int(self.port.get())
            if not 1 <= port <= 65535: raise ValueError('Port outside range')
        except ValueError:
            messagebox.showerror('Invalid port','Enter a port between 1 and 65535.');return
        if not host:return
        def job():
            self.client.connect(host,port,username,password,proto)
            self.events.put(('connected',proto+'  '+host))
        self.work(job)
    def open_server_book(self):
        win=tk.Toplevel(self);win.title('AetherFTP | Server Book');win.geometry('760x480');win.configure(bg=BG)
        try: profiles=load_profiles()
        except Exception as exc:
            messagebox.showerror('Server Book',str(exc),parent=win);profiles=[]
        outer=tk.Frame(win,bg=BG,padx=18,pady=16);outer.pack(fill='both',expand=True)
        self.label(outer,'◈  SERVER BOOK',PURPLE,17,True).pack(anchor='w',pady=(0,12))
        tree=ttk.Treeview(outer,columns=('host','protocol','user'),show='tree headings',height=9)
        tree.heading('#0',text='PROFILE');tree.heading('host',text='HOST');tree.heading('protocol',text='PROTOCOL');tree.heading('user',text='USERNAME')
        tree.column('#0',width=180);tree.column('host',width=200);tree.column('protocol',width=85);tree.column('user',width=140)
        tree.pack(fill='both',expand=True)
        def redraw():
            tree.delete(*tree.get_children())
            for i,p in enumerate(profiles):tree.insert('','end',iid=str(i),text=p['name'],values=(p['host'],p['protocol'],p['username']))
        def selected():
            sel=tree.selection();return int(sel[0]) if sel else None
        def persist():
            try:save_profiles(profiles);redraw()
            except Exception as exc:messagebox.showerror('Server Book',str(exc),parent=win)
        def load(connect=False):
            i=selected()
            if i is None:return
            p=profiles[i]
            for widget,value in ((self.host,p['host']),(self.port,str(p['port'])),(self.user,p['username']),(self.password,'')):
                widget.delete(0,'end');widget.insert(0,value)
            self.protocol.set(p['protocol'])
            self.port.delete(0,'end');self.port.insert(0,str(p['port']))
            if p.get('password_dpapi'):
                try:self.password.insert(0,decrypt_password(p['password_dpapi']))
                except Exception as exc:messagebox.showwarning('Credential unavailable','Could not decrypt saved password: '+str(exc),parent=win)
            win.destroy()
            if connect:self.connect()
        def editor(index=None):
            old=profiles[index] if index is not None else {}
            dlg=tk.Toplevel(win);dlg.title('Edit server' if old else 'New server');dlg.geometry('440x425');dlg.configure(bg=BG);dlg.transient(win);dlg.grab_set()
            body=tk.Frame(dlg,bg=BG,padx=18,pady=14);body.pack(fill='both',expand=True)
            fields={}
            defaults={'name':'','host':self.host.get(),'port':self.port.get(),'username':self.user.get(),'password':''}
            for key,label in [('name','Profile Name'),('host','Hostname / IP'),('port','Port'),('username','Username'),('password','Password (optional)')]:
                self.label(body,label,MUTED,9).pack(anchor='w')
                ent=tk.Entry(body,bg=INPUT,fg=FG,insertbackground=FG,relief='flat',show='*' if key=='password' else None)
                ent.insert(0,old.get(key,defaults[key]));ent.pack(fill='x',ipady=5,pady=(2,7));fields[key]=ent
            protocol=tk.StringVar(value=old.get('protocol',self.protocol.get()))
            tk.OptionMenu(body,protocol,'SFTP','FTPS','FTP').pack(anchor='w')
            save_pw=tk.BooleanVar(value=bool(old.get('password_dpapi')))
            tk.Checkbutton(body,text='Save encrypted password (Windows DPAPI)',variable=save_pw,bg=BG,fg=FG,selectcolor=INPUT,activebackground=BG,activeforeground=FG).pack(anchor='w',pady=6)
            def save():
                name=fields['name'].get().strip();host=fields['host'].get().strip()
                try:port=int(fields['port'].get());assert 1<=port<=65535
                except (ValueError,AssertionError):messagebox.showerror('Invalid port','Port must be 1–65535.',parent=dlg);return
                if not name or not host:messagebox.showerror('Required','Profile name and hostname are required.',parent=dlg);return
                if any(p['name'].casefold()==name.casefold() for j,p in enumerate(profiles) if j!=index):
                    messagebox.showerror('Duplicate','A profile with that name exists.',parent=dlg);return
                item={'name':name,'host':host,'port':port,'username':fields['username'].get(),'protocol':protocol.get()}
                if save_pw.get():
                    password=fields['password'].get()
                    try:
                        if password:item['password_dpapi']=encrypt_password(password)
                        elif old.get('password_dpapi'):item['password_dpapi']=old['password_dpapi']
                    except Exception as exc:messagebox.showerror('Encryption failed',str(exc),parent=dlg);return
                if index is None:profiles.append(item)
                else:profiles[index]=item
                persist();dlg.destroy()
            self.btn(body,'SAVE PROFILE',save,PURPLE).pack(anchor='e',pady=4)
        def remove():
            i=selected()
            if i is not None and messagebox.askyesno('Delete profile','Delete selected server profile?',parent=win):
                profiles.pop(i);persist()
        def duplicate():
            i=selected()
            if i is None:return
            copy=profiles[i].copy();copy['name']+=' (copy)';profiles.append(copy);persist()
        buttons=tk.Frame(outer,bg=BG);buttons.pack(fill='x',pady=(12,0))
        for label,fn in [('NEW',lambda:editor()),('EDIT',lambda:editor(selected()) if selected() is not None else None),('DUPLICATE',duplicate),('DELETE',remove),('LOAD',load),('CONNECT',lambda:load(True))]:
            self.btn(buttons,label,fn,PURPLE if label=='CONNECT' else INPUT).pack(side='left',padx=(0,5))
        tree.bind('<Double-1>',lambda e:load(True));redraw()

    def disconnect(self):
        self.work(lambda:(self.client.close(),self.events.put(('log','Disconnected.'))))
        self.status.set('●  OFFLINE')
    def refresh_local(self):
        self.local_display.set(str(self.local_path)) if hasattr(self,'local_display') else None
        tree=getattr(self,'local_tree',None)
        if tree is None:return
        tree.delete(*tree.get_children())
        if self.local_path.parent!=self.local_path:tree.insert('','end',iid='..',text='📁  ..',values=('PARENT',))
        try:
            for i,p in enumerate(sorted(self.local_path.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower()))):
                tree.insert('','end',iid=str(i),text=('📁  ' if p.is_dir() else '◻  ')+p.name,values=('<DIR>' if p.is_dir() else self.size(p.stat().st_size),),tags=(str(p),))
        except OSError as exc:self.log('Local filesystem error: '+str(exc))
    def refresh_remote(self):
        if not self.client.conn:return
        path=self.remote_path
        self.work(lambda:self.events.put(('remote',path,self.client.listdir(path))))
    def go_path(self,side):
        if side=='local':
            p=Path(self.local_display.get()).expanduser()
            if p.is_dir():self.local_path=p;self.refresh_local()
            else:self.log('Not a local directory: '+str(p))
        else:
            self.remote_path=self.remote_display.get();self.refresh_remote()
    def open_item(self,side):
        if side=='local':
            selected=self.local_tree.selection()
            if not selected:return
            iid=selected[0]
            p=self.local_path.parent if iid=='..' else Path(self.local_tree.item(iid,'tags')[0])
            if p.is_dir():self.local_path=p;self.refresh_local()
        else:
            selected=self.remote_tree.selection()
            if not selected:return
            iid=selected[0]
            if iid=='..':self.remote_path=os.path.dirname(self.remote_path.rstrip('/')) or '/'
            else:
                name,isdir=self.entries[iid]
                if not isdir:return
                self.remote_path=self.remote_path.rstrip('/')+'/'+name
            self.refresh_remote()
    def transfer(self,direction):
        if not self.client.conn:self.log('Connect to a server first.');return
        if direction=='upload':
            selection=self.local_tree.selection()
            if not selection or selection[0]=='..':return
            source=Path(self.local_tree.item(selection[0],'tags')[0])
            if not source.is_file():self.log('Select a file, not a directory.');return
            dest=self.remote_path.rstrip('/')+'/'+source.name;size=source.stat().st_size
        else:
            selection=self.remote_tree.selection()
            if not selection or selection[0]=='..':return
            name,isdir=self.entries[selection[0]]
            if isdir:self.log('Select a file, not a directory.');return
            source=self.remote_path.rstrip('/')+'/'+name;dest=self.local_path/name;size=0
            if dest.exists() and not messagebox.askyesno('Overwrite file?',f'{dest} exists. Overwrite it?'):return
        self.progress['value']=0
        def callback(done,total):
            denom=total or size
            if denom:self.events.put(('progress',min(100,done/denom*100)))
        def job():
            self.events.put(('log',direction.upper()+' '+str(source)))
            if direction=='upload':self.client.upload(str(source),str(dest),callback)
            else:self.client.download(str(source),str(dest),callback)
            self.events.put(('progress',100));self.events.put(('log','Completed: '+str(dest)))
            if direction=='upload':self.events.put(('remote',self.remote_path,self.client.listdir(self.remote_path)))
            else:self.events.put(('local_refresh',))
        self.work(job)
    def upload(self):self.transfer('upload')
    def download(self):self.transfer('download')

if __name__=='__main__':
    app=App()
    app.mainloop()
