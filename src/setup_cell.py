#@title 1️⃣ Preparar o ambiente e entrar com a conta Google  { display-mode: "form" }
#@markdown Clique no ▶ à esquerda. Uma janela do Google vai pedir autorização — isso é obrigatório para usar o app. A instalação leva de 1 a 3 minutos.
conectar_google_drive = True  #@param {type:"boolean"}
#@markdown *Com o Drive conectado, os cookies ficam salvos entre sessões e os arquivos podem ser copiados para `Meu Drive/StemTube`.*
instalar_separador_ia = True  #@param {type:"boolean"}
#@markdown *Desmarque para preparar só os downloads (mais rápido). A separação de faixas com IA precisa deste componente.*

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

# ---------- 3. GPU ----------
GPU_NAME = None
try:
    import torch
    if torch.cuda.is_available():
        GPU_NAME = torch.cuda.get_device_name(0)
except Exception:
    pass
if instalar_separador_ia and not GPU_NAME:
    _box('⚠️ <b>Nenhuma GPU nesta sessão.</b> Downloads funcionam normalmente, mas a separação de faixas vai ficar muito lenta. '
         'Vá em <b>Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU</b> e rode esta célula de novo.', 'warn')

# ---------- 4. Dependências ----------
_t0 = time.time()
_pkgs = ['yt-dlp[default]'] + (['audio-separator[cpu]', 'audioread'] if instalar_separador_ia else [])
_box('📦 Instalando ' + ('yt-dlp, o separador de faixas (audio-separator) e o runtime JavaScript… 1 a 3 min' if instalar_separador_ia else 'yt-dlp e o runtime JavaScript… ~30 s'))
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

SEP_VERSION = None
if instalar_separador_ia:
    try:
        import audio_separator
        SEP_VERSION = getattr(audio_separator, '__version__', None) or 'ok'
    except Exception as e:
        raise RuntimeError('O separador não pôde ser importado. Reinicie a sessão e execute novamente a preparação.') from e
    _cli_check = subprocess.run(['audio-separator', '--help'], capture_output=True, text=True, timeout=120)
    if _cli_check.returncode or '--custom_output_names' not in _cli_check.stdout:
        raise RuntimeError('O comando audio-separator não está operacional ou é incompatível. Reinicie a sessão.')

_STEMTUBE_SETUP_READY = True
clear_output()
_box(f'✅ <b>Login OK</b> — {USER_EMAIL}', 'ok')
_box(('✅ <b>Google Drive conectado</b> — cookies, downloads, faixas e mixagens podem ser salvos em <code>Meu Drive/StemTube</code>' if DRIVE_OK
      else 'ℹ️ Google Drive <b>não conectado</b> — os cookies valerão só nesta sessão.'), 'ok' if DRIVE_OK else 'info')
if instalar_separador_ia:
    _box((f'⚡ GPU: <b>{GPU_NAME}</b>' if GPU_NAME else '⚠️ <b>Sem GPU</b> — ative em Ambiente de execução ▸ Alterar o tipo de ambiente de execução ▸ T4 GPU'), 'ok' if GPU_NAME else 'warn')
_box(f'✅ yt-dlp <b>{yt_dlp.version.__version__}</b> · separador de IA {"<b>instalado</b>" if SEP_VERSION else "<b>não instalado</b> (só downloads)"} · '
     f'ffmpeg {"OK" if shutil.which("ffmpeg") else "NÃO encontrado"} · deno {"OK" if shutil.which("deno") else "não instalado"} · {int(time.time()-_t0)} s', 'ok')
_box('👉 Agora rode a célula <b>2️⃣ Abrir o aplicativo</b>.' + (' O modelo de IA de voz começa a ser baixado em segundo plano assim que o app abrir.' if SEP_VERSION else ''), 'info')
