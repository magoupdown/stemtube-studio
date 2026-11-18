#@title 1️⃣ Preparar o ambiente e entrar com a conta Google  { display-mode: "form" }
#@markdown Clique no ▶ à esquerda. Uma janela do Google vai pedir autorização — isso é obrigatório para usar o app. A instalação leva de 1 a 3 minutos.
conectar_google_drive = True  #@param {type:"boolean"}
#@markdown *Com o Drive conectado, os cookies ficam salvos entre sessões e os arquivos podem ser copiados para `Meu Drive/StemTube`.*

import os, sys, shutil, subprocess, json, time
if globals().get('_STEMTUBE_STATE'):
    raise RuntimeError('O ambiente já foi preparado. Para atualizar dependências, reinicie a sessão. Para reabrir a interface, execute somente a célula 2.')
_STEMTUBE_SETUP_READY = False
from IPython.display import HTML, display, clear_output

def _box(msg, kind='info'):
    cor = {'info': '#3b82f6', 'ok': '#22c55e', 'warn': '#f59e0b', 'err': '#ef4444'}[kind]
    display(HTML(f'<div style="font-family:system-ui,sans-serif;font-size:14px;padding:10px 14px;margin:6px 0;border-radius:10px;'
                 f'border-left:4px solid {cor};background:{cor}14;color:inherit">{msg}</div>'))

# ---------- 1. Login Google (obrigatório) ----------
_box('🔐 Aguardando login na conta Google… aceite a janela que abriu.')
try:
    from google.colab import auth
    auth.authenticate_user()
except Exception as e:
    raise SystemExit(f'Login cancelado ou falhou: {e}. Rode a célula novamente e conclua o login.')

USER_EMAIL = None
try:
    import google.auth, google.auth.transport.requests, requests
    _creds, _ = google.auth.default()
    _creds.refresh(google.auth.transport.requests.Request())
    USER_EMAIL = requests.get('https://www.googleapis.com/oauth2/v3/userinfo',
                              headers={'Authorization': f'Bearer {_creds.token}'}, timeout=15).json().get('email')
except Exception:
    pass
USER_EMAIL = USER_EMAIL or 'Conta Google conectada'

# ---------- 2. Google Drive (opcional) ----------
DRIVE_OK = False
if conectar_google_drive:
    try:
        from google.colab import drive
        drive.mount('/content/drive', force_remount=False)
        DRIVE_OK = os.path.isdir('/content/drive/MyDrive')
    except Exception as e:
        _box(f'Drive não conectado: {e}', 'warn')

# ---------- 4. Dependências ----------
_t0 = time.time()
_pkgs = ['yt-dlp[default]']
_box('Instalando yt-dlp e preparando as ferramentas de conversão…')
_r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-U'] + _pkgs, capture_output=True, text=True, timeout=900)
if _r.returncode != 0:
    _box('Falha ao instalar as dependências. Copie a mensagem abaixo e envie para suporte.', 'err')
    print(_r.stderr[-3000:])
    raise SystemExit('pip falhou')
if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
    subprocess.run(['apt-get', 'update', '-qq'], check=True, timeout=300)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'ffmpeg'], check=True, timeout=300)
if not shutil.which('deno'):
    try:
        subprocess.run(['curl', '-fSL', '--max-time', '120', 'https://deno.land/install.sh',
                        '-o', '/tmp/stemtube_deno_install.sh'], check=True, timeout=150)
        subprocess.run(['sh', '/tmp/stemtube_deno_install.sh'], env=dict(os.environ, DENO_INSTALL='/usr/local'),
                       stdin=subprocess.DEVNULL, check=True, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        _box(f'O runtime JavaScript (deno) não pôde ser instalado ({e}). Alguns vídeos podem falhar; o app continua funcionando.', 'warn')
os.environ['PATH'] += ':/usr/local/bin'
import importlib, yt_dlp
importlib.reload(yt_dlp)

_STEMTUBE_SETUP_READY = True
clear_output()
_box(f'✅ <b>Login OK</b> — {USER_EMAIL}', 'ok')
_box(('✅ <b>Google Drive conectado</b> — cookies e downloads podem ser salvos em <code>Meu Drive/StemTube</code>' if DRIVE_OK
      else 'ℹ️ Google Drive <b>não conectado</b> — os cookies valerão só nesta sessão.'), 'ok' if DRIVE_OK else 'info')
_box(f'✅ yt-dlp {yt_dlp.version.__version__} · FFmpeg OK · {int(time.time()-_t0)} s', 'ok')
_box('Agora execute a célula 2 para abrir o Studio.')
