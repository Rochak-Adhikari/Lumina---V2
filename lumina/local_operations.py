"""Small Windows operations; no shell input or model-generated commands."""
from pathlib import Path
import os
import platform
import subprocess
from urllib.parse import urlsplit
import html
import html.parser
import ipaddress
import socket
import urllib.request
import urllib.error
import shutil


TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.json', '.toml', '.yaml', '.yml', '.log', '.py', '.js', '.css', '.html', '.xml'}
OPEN_EXTENSIONS = {'.txt', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
SECRET_NAMES = {'.gemini-key', '.env', 'id_rsa', 'id_ed25519', 'credentials.json'}


class LocalOperations:
    def __init__(self, index):
        self.index = index

    def file(self, value, extensions):
        candidate = Path(value)
        # Reject alternate streams, device paths, traversal and hidden credentials.
        if candidate.drive and not candidate.is_absolute():
            raise ValueError('Use a file inside the configured root.')
        path = candidate if candidate.is_absolute() else self.index.root / candidate
        try:
            relative = path.relative_to(self.index.root)
        except ValueError:
            raise ValueError('That file is outside the configured root.') from None
        if any(p in ('.', '..') or p.startswith('.') or ':' in p or p.casefold() in SECRET_NAMES for p in relative.parts):
            raise ValueError('That file is outside the permitted file scope.')
        if not self.index.allowed(path) or not path.is_file():
            raise ValueError('That file is unavailable inside the configured root.')
        if path.suffix.lower() not in extensions:
            raise ValueError('That file type is not permitted for this operation.')
        return path

    def read_file(self, path):
        target = self.file(path, TEXT_EXTENSIONS)
        with target.open('rb') as stream:
            data = stream.read(32769)
        if b'\x00' in data:
            raise ValueError('This file is not plain text.')
        return {'ok': True, 'path': str(target), 'content': data[:32768].decode('utf-8-sig', errors='replace'),
                'encoding': 'utf-8-sig', 'size': target.stat().st_size, 'truncated': len(data) > 32768}

    def file_metadata(self, path):
        target = self.file(path, TEXT_EXTENSIONS | OPEN_EXTENSIONS)
        stat = target.stat()
        return {'ok': True, 'path': str(target), 'filename': target.name, 'type': 'directory' if target.is_dir() else 'file',
                'size': stat.st_size, 'modified': stat.st_mtime, 'extension': target.suffix.lower()}

    def search_file_contents(self, query, path='', limit=20):
        if not isinstance(query, str) or not query.strip(): raise ValueError('A content query is required.')
        limit = max(1, min(int(limit), 50));needle = query.casefold();files=[]
        if path:
            target = self.file(path, TEXT_EXTENSIONS)
            files=[target]
        else:
            entries,_ = self.index.scan()
            files=[Path(item['path']) for item in entries if item['type']=='file' and Path(item['path']).suffix.lower() in TEXT_EXTENSIONS]
        matches=[]
        for target in files:
            try:
                with target.open('r',encoding='utf-8',errors='replace') as stream:
                    for number,line in enumerate(stream,1):
                        if needle in line.casefold():
                            matches.append({'path':str(target),'filename':target.name,'line':number,'excerpt':line.strip()[:500]})
                            if len(matches)>=limit: return {'ok':True,'count':len(matches),'matches':matches,'truncated':True}
            except (OSError,UnicodeError): continue
        return {'ok':True,'count':len(matches),'matches':matches,'truncated':False}

    def system_info(self):
        usage = shutil.disk_usage(self.index.root)
        return {'ok': True, 'system': platform.system(), 'release': platform.release(),
                'architecture': platform.machine(), 'cpu_count': os.cpu_count(),
                'disk_free': usage.free, 'disk_total': usage.total}

    @staticmethod
    def _public_url(url):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Use a complete public HTTP or HTTPS address without credentials.')
        try:
            addresses = socket.getaddrinfo(parsed.hostname, None)
            if any(ipaddress.ip_address(item[4][0]).is_private or ipaddress.ip_address(item[4][0]).is_loopback or ipaddress.ip_address(item[4][0]).is_link_local for item in addresses):
                raise ValueError('Private and local web addresses are not permitted.')
        except socket.gaierror:
            raise ValueError('The web address could not be resolved.') from None
        return url

    def fetch_web_page(self, url):
        url = self._public_url(url)
        class LimitedRedirect(urllib.request.HTTPRedirectHandler):
            def __init__(self): self.count=0
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                self.count += 1
                if self.count > 3: raise urllib.error.HTTPError(req.full_url, code, 'Too many redirects', headers, fp)
                LocalOperations._public_url(newurl)
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        request=urllib.request.Request(url,headers={'User-Agent':'LUMINA-local-reader/1.0','Accept':'text/html,text/plain,application/json'})
        opener=urllib.request.build_opener(LimitedRedirect())
        with opener.open(request,timeout=10) as response:
            content_type=response.headers.get_content_type();data=response.read(512001);truncated=len(data)>512000
            if content_type not in {'text/html','text/plain','application/json','text/xml','application/xml'}:
                raise ValueError('That response is not a readable text page.')
            text=data[:512000].decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
            title=''
            if content_type=='text/html':
                class Title(html.parser.HTMLParser):
                    def __init__(self): super().__init__();self.in_title=False;self.parts=[]
                    def handle_starttag(self,tag,attrs): self.in_title |= tag.lower()=='title'
                    def handle_endtag(self,tag): self.in_title &= tag.lower()!='title'
                    def handle_data(self,data):
                        if self.in_title:self.parts.append(data)
                parsed=Title();parsed.feed(text);title=' '.join(' '.join(parsed.parts).split())[:240]
                import re
                text=re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>',' ',data[:512000].decode(response.headers.get_content_charset() or 'utf-8',errors='replace'),flags=re.I)
                text=re.sub(r'<[^>]+>',' ',text);text=' '.join(html.unescape(text).split())[:20000]
            return {'ok':True,'final_url':response.geturl(),'status':response.status,'content_type':content_type,'title':title,'text':text,'truncated':truncated,'untrusted':True}

    def open_file(self, path):
        target = self.file(path, OPEN_EXTENSIONS)
        self.launch_file(target)
        return {'ok': True, 'path': str(target), 'message': 'The file was handed to its default application.'}

    @staticmethod
    def launch_file(path):
        if os.name != 'nt':
            raise ValueError('Opening files is available on Windows only.')
        os.startfile(str(path))

    def open_app(self, app):
        # Resolve only known installed paths. Never search the working directory or PATH.
        windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
        program = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
        program_x86 = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'))
        local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local')))
        candidates = {
            'notepad': [windows / 'System32/notepad.exe'],
            'calculator': [windows / 'System32/calc.exe'],
            'chrome': [program / 'Google/Chrome/Application/chrome.exe', program_x86 / 'Google/Chrome/Application/chrome.exe', local / 'Google/Chrome/Application/chrome.exe'],
            'edge': [program_x86 / 'Microsoft/Edge/Application/msedge.exe', program / 'Microsoft/Edge/Application/msedge.exe'],
        }
        if app not in candidates:
            raise ValueError('That application is not in the local allowlist.')
        process_names = {
            'notepad': {'notepad.exe'}, 'calculator': {'calc.exe', 'calculator.exe', 'calculatorapp.exe'},
            'chrome': {'chrome.exe'}, 'edge': {'msedge.exe'},
        }
        if self.running_process_names() & process_names[app]:
            return {'ok': True, 'app': app, 'already_running': True,
                    'message': 'The application is already running.'}
        executable = next((p for p in candidates[app] if p.is_file()), None)
        if executable is None:
            raise ValueError('That application is not installed at a supported location.')
        self.launch_app(executable)
        return {'ok': True, 'app': app, 'message': 'The application launch was requested.'}

    @staticmethod
    def running_process_names():
        """Read Windows process names without invoking a shell or exposing PIDs."""
        if os.name != 'nt':
            raise ValueError('Opening applications is available on Windows only.')
        import ctypes
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                        ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                        ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                        ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                        ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        for function in (kernel.Process32FirstW, kernel.Process32NextW):
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
            function.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
                raise ctypes.WinError(ctypes.get_last_error())
            names = {entry.szExeFile.casefold()}
            while kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                names.add(entry.szExeFile.casefold())
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise ctypes.WinError(ctypes.get_last_error())
            return names
        finally:
            kernel.CloseHandle(snapshot)

    @staticmethod
    def launch_app(path):
        if os.name != 'nt':
            raise ValueError('Opening applications is available on Windows only.')
        subprocess.Popen([str(path)], shell=False, close_fds=True)

    @staticmethod
    def validate_url(url):
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                or any(ord(c) < 33 for c in url) or '\\' in url):
            raise ValueError('Use a complete HTTP or HTTPS address without credentials.')
        return url

    def open_url(self, url):
        self.validate_url(url)
        self.launch_file(url)
        return {'ok': True, 'message': 'The address was handed to the default browser.'}

    def delete_file(self, path):
        target = self.file(path, TEXT_EXTENSIONS | OPEN_EXTENSIONS)
        if os.name != 'nt': raise ValueError('Recoverable deletion is available on Windows only.')
        import ctypes
        class SHFILEOPSTRUCT(ctypes.Structure):
            _fields_=[('hwnd',ctypes.c_void_p),('wFunc',ctypes.c_uint),('pFrom',ctypes.c_wchar_p),('pTo',ctypes.c_wchar_p),('fFlags',ctypes.c_ushort),('fAnyOperationsAborted',ctypes.c_int),('hNameMappings',ctypes.c_void_p),('lpszProgressTitle',ctypes.c_wchar_p)]
        operation=SHFILEOPSTRUCT(None,2,str(target)+'\0\0',None,0x0010|0x0004,0,None,None)
        result=ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result: raise OSError(result, 'Windows could not move the item to the Recycle Bin.')
        return {'ok':True,'path':str(target),'message':'The item was moved to the Recycle Bin.'}
