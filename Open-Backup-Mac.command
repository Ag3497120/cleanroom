#!/bin/zsh
set -eu
cd "$(dirname "$0")"
printf '24GB Macへ接続します。必要なら、このターミナルにそのMacのログインパスワードを入力してください。\n接続中はこの画面を開いたままにしてください。Ctrl+Cで切断します。\n'
backup_target="${VERANTYX_BACKUP_SSH:-}"
if [[ -z "$backup_target" ]]; then
  read 'backup_target?24GB Macの接続先（ユーザー名@10.0.0.2）: '
fi
exec ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:11435:127.0.0.1:11434 "$backup_target" 'export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; printf "Mac: "; scutil --get ComputerName; printf "Memory bytes: "; sysctl -n hw.memsize; if ! command -v ollama >/dev/null; then echo "OllamaをこのMacにインストールしてから再接続してください。"; exit 1; fi; if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then OLLAMA_HOST=127.0.0.1:11434 ollama serve & fi; echo "SSH forwarding ready. Leave this terminal open."; while :; do sleep 60; done'
