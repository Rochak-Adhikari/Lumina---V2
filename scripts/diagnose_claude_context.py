"""Safe authentication metadata only. Never prints values or credential contents."""
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from lumina.workers import ClaudeCodeWorker,build_worker_environment

def main():
    root=Path.cwd();worker=ClaudeCodeWorker(root,'claude.ps1')
    executable=worker.command('diagnostic')[0]
    print(json.dumps({'executable':executable,'profile':os.environ.get('USERPROFILE'),'home_present':'HOME' in os.environ,
        'claude_config_dir_present':'CLAUDE_CONFIG_DIR' in os.environ,'username':os.environ.get('USERNAME'),
        'auth_token_present':'ANTHROPIC_AUTH_TOKEN' in os.environ,'base_url_present':'ANTHROPIC_BASE_URL' in os.environ}))
    for label,sources in [('worker_settings_disabled',''),('user_settings_enabled','user')]:
        env=build_worker_environment(root)
        result=subprocess.run([executable,'--setting-sources',sources,'auth','status'],env=env,cwd=root,capture_output=True,text=True,timeout=15)
        try:data=json.loads(result.stdout)
        except ValueError:data={}
        print(json.dumps({'case':label,'exit_code':result.returncode,**{k:data.get(k) for k in ('loggedIn','authMethod','apiProvider')}}))

if __name__=='__main__':main()
