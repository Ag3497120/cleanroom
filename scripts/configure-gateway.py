"""Create the Mac-only configuration; no secrets go into GitHub Pages."""
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

root=Path(__file__).resolve().parents[1]
directory=root/".gateway"
directory.mkdir(mode=0o700,exist_ok=True)
path=directory/"config.json"
draft=directory/"config.draft.json"
config=json.loads(path.read_text()) if path.exists() else (json.loads(draft.read_text()) if draft.exists() else {})
def prompt(key,label,default=""):
    value=input(f"{label} [{config.get(key,default)}]: ").strip() or config.get(key,default)
    if not value: raise SystemExit(label+" が必要です。設定は保存していません。")
    config[key]=value

prompt("site_url","GitHub PagesのURL（リポジトリのパスまで）")
prompt("gateway_url","Mac接続のHTTPS URL（パスなし）")
prompt("github_client_id","device flowを有効にしたGitHub OAuthアプリのClient ID")
prompt("owner_github_id","Mac所有者のGitHub数値ID")
for key in ("site_url","gateway_url"):
    url=urlsplit(config[key])
    if url.scheme!="https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise SystemExit("HTTPS URLを確認してください。保存していません。")
    if key=="gateway_url" and url.path not in ("","/"): raise SystemExit("Mac接続URLはパスなしで指定してください。")
if not re.fullmatch(r"[0-9]{1,20}",config["owner_github_id"]):raise SystemExit("GitHub数値IDを確認してください。")
config["notify_email"]=input(f"上限通知メール（空欄ならメールなし） [{config.get('notify_email','')}]: ").strip() or config.get('notify_email','')
config.update(state_dir=str(directory/"state"),port=8766,owner_port=8767,python=sys.executable)
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as out:json.dump(config,out,ensure_ascii=False,indent=2)
path.chmod(0o600)
print("Mac内だけに設定しました。Open-Compute-Gateway.commandで起動できます。")
