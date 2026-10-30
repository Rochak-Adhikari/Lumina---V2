from dataclasses import dataclass, fields
from pathlib import Path
import os
import tomllib


@dataclass(frozen=True)
class Config:
    root: Path = Path.cwd()
    state_root: Path | None = None
    provider: str = "local"
    host: str = "127.0.0.1"
    port: int = 8764
    assistant_name: str = "LUMINA"
    user_name: str = ""
    model: str = "gemini-3.1-flash-live-preview"
    live_model: str = "gemini-3.1-flash-live-preview"
    worker: str = "none"
    worker_executable: str = "claude"
    worker_timeout: int = 1800
    worker_backend: str = 'conpty'
    msys_root: str = 'C:/msys64'
    agent_limit: int = 4
    allow_metered_agents: bool = False  # Legacy configuration accepted; no longer gates Claude.
    desktop_roots: tuple = ()
    knowledge_graph: str = "graphify-out/graph.json"
    memory_path: str = ""
    greeting_path: str = ""
    voice: str = "Aoede"
    greetings_enabled: bool = True
    auto_memory_capture: bool = True
    microphone_device: str = "default"
    speaker_device: str = "default"
    graph_limit: int = 600
    scan_limit: int = 20000
    scan_seconds: int = 5

    @property
    def runtime_root(self):
        """Existing durable state may outlive a relocation of application files."""
        return Path(self.state_root) if self.state_root is not None else self.root

    @classmethod
    def load(cls, path: Path = Path("lumina.toml")):
        data = tomllib.loads(path.read_text("utf-8")) if path.exists() else {}
        known = {f.name for f in fields(cls)}
        if set(data) - known:
            raise ValueError("Unknown configuration fields: " + ", ".join(sorted(set(data) - known)))
        for key in known:
            if "LUMINA_" + key.upper() in os.environ:
                data[key] = os.environ["LUMINA_" + key.upper()]
        if 'greetings_enabled' in data:
            value=data['greetings_enabled']
            if isinstance(value,str) and value.lower() in {'true','false'}:
                data['greetings_enabled']=value.lower()=='true'
            elif not isinstance(value,bool):
                raise ValueError('greetings_enabled must be true or false.')
        if 'auto_memory_capture' in data:
            value=data['auto_memory_capture']
            if isinstance(value,str) and value.lower() in {'true','false'}:
                data['auto_memory_capture']=value.lower()=='true'
            elif not isinstance(value,bool):
                raise ValueError('auto_memory_capture must be true or false.')
        if 'allow_metered_agents' in data:
            value=data['allow_metered_agents']
            if isinstance(value,str) and value.lower() in {'true','false'}:
                data['allow_metered_agents']=value.lower()=='true'
            elif not isinstance(value,bool):
                raise ValueError('allow_metered_agents must be true or false.')
        for key in ("port", "graph_limit", "scan_limit", "scan_seconds", "worker_timeout", "agent_limit"):
            if key in data:
                data[key] = int(data[key])
        data["root"] = Path(data.get("root", Path.cwd())).expanduser().resolve(strict=True)
        if data.get('state_root'):
            data['state_root'] = Path(data['state_root']).expanduser().resolve(strict=True)
            if not data['state_root'].is_dir():
                raise ValueError('LUMINA_STATE_ROOT must be an existing directory.')
        else:
            data['state_root'] = None
        roots=data.get('desktop_roots',())
        if isinstance(roots,str): roots=[p for p in roots.split(os.pathsep) if p]
        if not isinstance(roots,(list,tuple)) or any(not isinstance(p,str) for p in roots):
            raise ValueError('desktop_roots must be an array of directory paths.')
        data['desktop_roots']=tuple(Path(os.path.expandvars(p)).expanduser().resolve(strict=True) for p in roots)
        if any(not p.is_dir() or p==Path(p.anchor) for p in data['desktop_roots']):
            raise ValueError('Desktop roots must be existing directories below a drive root.')
        cfg = cls(**data)
        if cfg.worker_backend not in {'conpty','tmux'} or not 1<=cfg.agent_limit<=16:
            raise ValueError('Choose conpty or tmux and an agent limit from 1 to 16.')
        if not cfg.root.is_dir():
            raise ValueError("LUMINA_ROOT must be an existing directory.")
        if cfg.host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("LUMINA_HOST must be a loopback address in this prototype.")
        if cfg.provider not in ("local", "gemini"):
            raise ValueError("LUMINA_PROVIDER must be local or gemini.")
        if cfg.worker not in ("none", "claude"):
            raise ValueError("LUMINA_WORKER must be none or claude.")
        if not 30 <= cfg.worker_timeout <= 7200:
            raise ValueError("worker_timeout must be 30–7200 seconds.")
        if not 1 <= cfg.port <= 65535 or not 50 <= cfg.graph_limit <= 700:
            raise ValueError("Port must be 1–65535; graph_limit must be 50–700.")
        if not 100 <= cfg.scan_limit <= 100000 or not 1 <= cfg.scan_seconds <= 15:
            raise ValueError("scan_limit must be 100–100000; scan_seconds must be 1–15.")
        return cfg

