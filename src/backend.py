# ============================================================
#  StemTube Studio — backend (roda dentro do Google Colab)
#  Expõe funções Python para a interface web via
#  google.colab.output.register_callback / kernel.invokeFunction
#
#  Reúne, em um único aplicativo:
#    • download de vídeos, playlists e canais do YouTube (MP4 ou áudio)
#    • recorte por tempo de um vídeo
#    • separação de voz e instrumentos por IA (audio-separator)
#    • mixer e renderização de mixagens
#
#  Desenvolvido por @emersonms - 2026
# ============================================================
import os, re, json, time, uuid, shutil, threading, socketserver, http.server
import urllib.parse, traceback, queue, subprocess, base64, sys, math, tempfile

import yt_dlp
from IPython.display import JSON

APP_NAME    = 'StemTube Studio'
APP_VERSION = '1.0.0'

# ---------- caminhos ----------
BASE_DIR      = '/content/stemtube'
WORK_DIR      = os.path.join(BASE_DIR, 'work')       # áudio de origem (wav) e uploads
OUT_DIR       = os.path.join(BASE_DIR, 'out')        # resultados por tarefa (servidos ao navegador)
MODELS_DIR    = os.path.join(BASE_DIR, 'models')     # modelos de IA baixados
COOKIES_PATH  = os.path.join(BASE_DIR, 'cookies.txt')
DRIVE_MYDRIVE = '/content/drive/MyDrive'
DRIVE_ROOT    = os.path.join(DRIVE_MYDRIVE, 'StemTube')
LEGACY_DRIVE_ROOTS = [os.path.join(DRIVE_MYDRIVE, 'StemLab'), os.path.join(DRIVE_MYDRIVE, 'YT_Downloader')]
FILE_PORT     = 8767
MAX_UPLOAD_MB = 1024
MAX_DURATION  = 25 * 60   # 25 min: acima disso a GPU gratuita costuma estourar a memória na separação
MAX_PLAYLIST  = 1000
MOCK          = bool(os.environ.get('STEMTUBE_MOCK'))  # modo de teste local sem GPU/modelos
for _d in (WORK_DIR, OUT_DIR, MODELS_DIR):
    os.makedirs(_d, exist_ok=True)

try:
    import audio_separator as _audio_separator
    SEP_AVAILABLE = True
except Exception:
    SEP_AVAILABLE = MOCK

STATE = globals().get('_STEMTUBE_STATE') or {
    'jobs': {}, 'sources': {}, 'uploads': {},
    'user': globals().get('USER_EMAIL') or 'Conta Google conectada',
    'js_runtime': None, 'gpu': None, 'prefetch': {},
}
_STEMTUBE_STATE = STATE
MODEL_LOCK = STATE.setdefault('model_lock', threading.Lock())

# ---------- modos de separação ----------
STEM_PT = {'Vocals': 'Voz', 'Instrumental': 'Playback', 'Drums': 'Bateria', 'Bass': 'Baixo',
           'Guitar': 'Guitarra', 'Piano': 'Piano', 'Other': 'Outros'}
STEM_ICON = {'Vocals': '🎤', 'Instrumental': '🎹', 'Drums': '🥁', 'Bass': '🎸', 'Guitar': '🎸', 'Piano': '🎹', 'Other': '🎼'}
STEM_COLOR = {'Vocals': '#f472b6', 'Instrumental': '#38bdf8', 'Drums': '#fb923c', 'Bass': '#a78bfa',
              'Guitar': '#facc15', 'Piano': '#34d399', 'Other': '#94a3b8'}
MODES = {
    '2stem': {'label': 'Voz + Playback', 'model': 'model_bs_roformer_ep_317_sdr_12.9755.ckpt',
              'stems': ['Vocals', 'Instrumental'], 'factor': 1.2, 'base': 30},
    '4stem': {'label': 'Banda (4 faixas)', 'model': 'htdemucs_ft.yaml',
              'stems': ['Vocals', 'Drums', 'Bass', 'Other'], 'factor': 1.2, 'base': 40},
    '6stem': {'label': 'Completo (6 faixas)', 'model': 'htdemucs_6s.yaml',
              'stems': ['Vocals', 'Drums', 'Bass', 'Guitar', 'Piano', 'Other'], 'factor': 0.5, 'base': 30},
}
OUT_FORMATS   = {'wav': 'WAV', 'flac': 'FLAC', 'mp3': 'MP3'}
AUDIO_FORMATS = ('mp3', 'm4a', 'opus', 'flac', 'wav', 'best')
AUDIO_QUALITIES = ('best', '320', '256', '192', '128', '96')
UPLOAD_EXTS   = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.aiff', '.aif', '.mp4', '.webm', '.mkv', '.mov')
YT_HOSTS      = ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
                 'youtube-nocookie.com', 'www.youtube-nocookie.com')

# ---------- utilidades ----------
def _drive_on():
    return os.path.isdir(DRIVE_MYDRIVE)

def _detect_js_runtime():
    if STATE['js_runtime'] is not None:
        return STATE['js_runtime']
    rt = {}
    for name in ('deno', 'node', 'bun'):
        p = shutil.which(name)
        if p:
            rt = {name: {'path': p}}
            break
    STATE['js_runtime'] = rt
    return rt

def _gpu_info(force=False):
    if STATE['gpu'] is not None and not force:
        return STATE['gpu']
    info = {'available': False, 'name': None, 'memory_gb': None, 'mock': MOCK}
    try:
        import torch
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info.update({'available': True, 'name': p.name, 'memory_gb': round(p.total_memory / 1024 ** 3, 1)})
    except Exception:
        pass
    STATE['gpu'] = info
    return info

def _friendly_error(msg):
    m = (msg or '').lower()
    if 'sign in to confirm' in m or 'not a bot' in m or ('bot' in m and 'confirm' in m):
        return ('O YouTube pediu confirmação de que você não é um robô. Isso é comum em servidores do Colab. '
                'Carregue os cookies da sua conta na seção "Cookies" e tente novamente.')
    if 'private video' in m or 'this video is private' in m:
        return 'Vídeo privado. Carregue os cookies de uma conta com acesso para usá-lo.'
    if 'members-only' in m or 'join this channel' in m:
        return 'Conteúdo exclusivo para membros. Carregue os cookies da conta que é membro do canal.'
    if 'age' in m and ('restrict' in m or 'confirm your age' in m or 'inappropriate' in m):
        return 'Vídeo com restrição de idade. Carregue os cookies da sua conta para confirmar a idade.'
    if 'video unavailable' in m or 'video is unavailable' in m or 'not available' in m:
        return 'Vídeo indisponível (removido, bloqueado na região ou link inválido).'
    if 'unsupported url' in m or 'is not a valid url' in m:
        return 'Este link não é reconhecido. Cole um link de vídeo, playlist ou canal do YouTube.'
    if 'requested format is not available' in m:
        return 'O formato escolhido não está disponível para este vídeo. Tente outra resolução ou formato.'
    if 'http error 429' in m or 'too many requests' in m:
        return 'O YouTube limitou as requisições (429). Aguarde alguns minutos ou use cookies.'
    if 'live' in m and ('is a live' in m or 'not yet' in m or 'premiere' in m):
        return 'Transmissões ao vivo ou estreias ainda não disponíveis não podem ser processadas.'
    if 'out of memory' in m or 'cuda error' in m:
        return 'A memória da GPU estourou. Tente uma música mais curta ou o modo "Voz + Playback".'
    return re.sub(r'^\s*ERROR:\s*', '', msg or 'Erro desconhecido').strip()[:400]

class _SilentLogger:
    """Engole a saída do yt-dlp, mas guarda erros para reportar na interface."""
    def __init__(self): self.errors, self.warnings = [], []
    def debug(self, msg):   pass
    def info(self, msg):    pass
    def warning(self, msg): self.warnings.append(str(msg))
    def error(self, msg):   self.errors.append(str(msg))

def _base_opts():
    o = {
        'quiet': True, 'no_warnings': True, 'noprogress': True, 'nocheckcertificate': False,
        'extractor_retries': 3, 'retries': 5, 'fragment_retries': 5, 'socket_timeout': 30,
        'geo_bypass': True, 'logger': _SilentLogger(),
    }
    if os.path.exists(COOKIES_PATH):
        o['cookiefile'] = COOKIES_PATH
    rt = _detect_js_runtime()
    if rt:
        o['js_runtimes'] = rt
    return o

def _fmt_size(b):
    if not b: return None
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024: return f'{b:.0f} {unit}' if unit == 'B' else f'{b:.1f} {unit}'
        b /= 1024
    return f'{b:.1f} TB'

def _hms(sec):
    sec = int(round(sec or 0)); h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

def _thumb(info):
    t = info.get('thumbnail')
    if not t and info.get('thumbnails'):
        t = info['thumbnails'][-1].get('url')
    if not t and info.get('id'):
        t = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
    return t

def _safe_name(s, n=90):
    s = yt_dlp.utils.sanitize_filename(str(s or 'audio'), restricted=False)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:n] or 'audio'

def _ffprobe_duration(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        duration = float(out) if out else 0.0
        return duration if math.isfinite(duration) and duration > 0 else 0.0
    except Exception:
        return 0.0

def _output_path(rel, preview=False):
    """Resolve um caminho relativo dentro de OUT_DIR, bloqueando travessia e links externos."""
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        raise ValueError('Caminho de arquivo inválido.')
    root = os.path.realpath(OUT_DIR)
    path = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath((root, path)) != root or not os.path.isfile(path):
        raise FileNotFoundError('Arquivo não encontrado nesta sessão.')
    if preview and not path.endswith(('.preview.mp3', '.preview.mp4')):
        raise ValueError('Prévia inválida ou grande demais para a ponte do Colab.')
    return path

def _check_cancel(job):
    if job.get('cancel'):
        raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')

def _run_process(job, cmd, timeout=1800, progress_file=None, progress_total=None, on_progress=None):
    """Processo com leitura contínua, prazo e cancelamento, inclusive sem logs."""
    _check_cancel(job)
    with tempfile.TemporaryFile(mode='w+b') as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        job['proc'] = proc
        started = time.monotonic()
        try:
            while proc.poll() is None:
                _check_cancel(job)
                if time.monotonic() - started > timeout:
                    raise TimeoutError('O processamento ultrapassou o tempo limite.')
                total = progress_total or job.get('duration')
                if progress_file and total:
                    try:
                        with open(progress_file) as f: values = re.findall(r'out_time_us=(\d+)', f.read())
                        if values:
                            pct = min(99, int(values[-1]) / 1000000 / total * 100)
                            if on_progress: on_progress(pct)
                            else: job['percent'] = max(job.get('percent', 0), pct)
                    except OSError: pass
                time.sleep(0.1)
            _check_cancel(job)
            if proc.returncode:
                log.seek(max(0, log.tell() - 3000))
                raise RuntimeError(log.read().decode('utf-8', errors='replace')[-3000:])
        finally:
            if proc.poll() is None: proc.kill()
            proc.wait()
            job['proc'] = None

# ---------- links do YouTube ----------
def _parse_url(url, mode='auto'):
    """Descobre se o link aponta para vídeo, playlist, canal ou uma combinação.
    mode: 'auto' (detecta), 'video' (só o vídeo) ou 'playlist' (só a playlist/canal)."""
    u = (url or '').strip()
    if not re.match(r'^https?://', u, re.I):
        u = 'https://' + u
    p = urllib.parse.urlparse(u)
    host = (p.hostname or '').lower()
    if p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('unsupported url: endereço inválido.')
    qs = urllib.parse.parse_qs(p.query)
    video_id = None
    playlist_id = (qs.get('list') or [None])[0]
    if host == 'youtu.be':
        video_id = p.path.strip('/').split('/')[0] or None
    elif host in YT_HOSTS:
        if p.path == '/watch':
            video_id = (qs.get('v') or [None])[0]
        else:
            m = re.match(r'^/(shorts|live|embed|v)/([A-Za-z0-9_-]{11})', p.path)
            if m: video_id = m.group(2)
        if p.path.startswith('/playlist'):
            video_id = None
    else:
        raise ValueError('unsupported url: apenas links do YouTube são aceitos.')
    if video_id and not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('unsupported url: identificador de vídeo inválido.')
    if playlist_id and not re.fullmatch(r'[A-Za-z0-9_-]{2,128}', playlist_id):
        raise ValueError('unsupported url: identificador de playlist inválido.')
    is_mix = bool(playlist_id and playlist_id.startswith('RD'))
    channel_url = u if (not video_id and not playlist_id and re.match(r'^/(@[\w.-]+|channel/|c/|user/)', p.path)) else None
    if is_mix and video_id:
        playlist_url = f'https://www.youtube.com/watch?v={video_id}&list={playlist_id}'
    elif playlist_id:
        playlist_url = f'https://www.youtube.com/playlist?list={playlist_id}'
    elif channel_url:
        playlist_url = channel_url.rstrip('/')
        if not re.search(r'/(videos|shorts|streams|playlists)$', playlist_url):
            playlist_url += '/videos'
    else:
        playlist_url = None
    if mode == 'video':
        if not video_id:
            raise ValueError('Você escolheu "somente o vídeo", mas este link não aponta para um vídeo. Cole o link de um vídeo (watch?v=…, youtu.be/… ou /shorts/…).')
        playlist_id, playlist_url, channel_url = None, None, None
    elif mode == 'playlist':
        if not playlist_url:
            raise ValueError('Você escolheu "playlist completa", mas este link não contém uma playlist. Abra a playlist no YouTube e copie o link que tem "list=" (ou o link de um canal).')
        video_id = None
    if not video_id and not playlist_url:
        raise ValueError('unsupported url: não encontrei um vídeo ou playlist nesse link.')
    return {'url': u, 'video_id': video_id, 'playlist_id': playlist_id, 'playlist_url': playlist_url,
            'channel_url': channel_url, 'is_mix': is_mix}

# ---------- cookies ----------
def _cookie_domain_ok(domain):
    domain = domain.lower().lstrip('.')
    return any(domain == base or domain.endswith('.' + base) for base in ('youtube.com', 'google.com'))

def _validate_cookie_content(content):
    rows = ['# Netscape HTTP Cookie File']
    for line in content.splitlines():
        raw = line[len('#HttpOnly_'):] if line.startswith('#HttpOnly_') else line
        if not raw.strip() or raw.startswith('#'):
            continue
        parts = raw.split('\t')
        if len(parts) != 7 or parts[1] not in ('TRUE', 'FALSE') or parts[3] not in ('TRUE', 'FALSE'):
            raise ValueError('Registro Netscape inválido: confira a exportação dos cookies.')
        if not parts[4].isdigit() or not parts[5]:
            raise ValueError('Nome ou validade de cookie inválido.')
        if _cookie_domain_ok(parts[0]):
            rows.append(line)
    if len(rows) == 1:
        raise ValueError('Não há cookies do YouTube ou Google neste arquivo.')
    return '\n'.join(rows) + '\n'

def _json_cookies_to_netscape(items):
    lines = ['# Netscape HTTP Cookie File', f'# gerado pelo {APP_NAME}', '']
    for c in items:
        dom = c.get('domain') or '.youtube.com'
        flag = 'TRUE' if dom.startswith('.') else 'FALSE'
        path = c.get('path') or '/'
        secure = 'TRUE' if c.get('secure') else 'FALSE'
        exp = c.get('expirationDate') or c.get('expires') or c.get('expiry') or 0
        try: exp = int(float(exp))
        except Exception: exp = 0
        lines.append('\t'.join([dom, flag, path, secure, str(exp), str(c.get('name', '')), str(c.get('value', ''))]))
    return '\n'.join(lines) + '\n'

def _header_cookies_to_netscape(header):
    header = re.sub(r'^\s*cookie\s*:\s*', '', header.strip(), flags=re.I)
    items = []
    for part in header.split(';'):
        if '=' in part:
            n, v = part.strip().split('=', 1)
            items.append({'domain': '.youtube.com', 'path': '/', 'secure': True,
                          'expirationDate': int(time.time()) + 365 * 86400, 'name': n.strip(), 'value': v.strip()})
    return _json_cookies_to_netscape(items)

def _normalize_cookies(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Cookies devem ser texto com até 2 MB.')
    t = text.strip().lstrip('﻿')
    if not t:
        raise ValueError('Arquivo de cookies vazio.')
    if t.startswith('[') or t.startswith('{'):
        data = json.loads(t)
        if isinstance(data, dict):
            data = data.get('cookies') or data.get('items') or list(data.values())
        return _json_cookies_to_netscape(data)
    if '\t' in t:
        if not t.startswith('#'):
            t = '# Netscape HTTP Cookie File\n' + t
        return t + '\n'
    if '=' in t and ';' in t and '\n' not in t.strip():
        return _header_cookies_to_netscape(t)
    raise ValueError('Formato de cookies não reconhecido. Use um arquivo cookies.txt (formato Netscape), o JSON exportado por extensão ou o cabeçalho Cookie:.')

def _cookie_summary():
    if not os.path.exists(COOKIES_PATH):
        return {'found': False}
    names, total = set(), 0
    with open(COOKIES_PATH, encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('#HttpOnly_'): line = line[len('#HttpOnly_'):]
            if line.startswith('#') or not line.strip(): continue
            parts = line.rstrip('\n').split('\t')
            if len(parts) >= 7 and _cookie_domain_ok(parts[0]):
                total += 1
                names.add(parts[5])
    logged = bool(names & {'SID', '__Secure-3PSID', 'SAPISID', '__Secure-3PAPISID', 'LOGIN_INFO'})
    src = 'drive' if os.path.exists(os.path.join(DRIVE_ROOT, 'cookies.txt')) else 'sessao'
    return {'found': True, 'total': total, 'logged_in': logged, 'source': src,
            'updated': time.strftime('%d/%m/%Y %H:%M', time.localtime(os.path.getmtime(COOKIES_PATH)))}

def _restore_cookies_from_drive():
    """Carrega cookies salvos no Drive (inclusive das versões anteriores: StemLab e YT Downloader)."""
    if os.path.exists(COOKIES_PATH) or not _drive_on():
        return None
    for root in [DRIVE_ROOT] + LEGACY_DRIVE_ROOTS:
        saved = os.path.join(root, 'cookies.txt')
        if os.path.exists(saved):
            try:
                content = _validate_cookie_content(open(saved, encoding='utf-8', errors='ignore').read())
            except Exception:
                continue
            with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            os.chmod(COOKIES_PATH, 0o600)
            if root != DRIVE_ROOT:   # migra para a pasta nova
                try:
                    os.makedirs(DRIVE_ROOT, exist_ok=True)
                    shutil.copy(COOKIES_PATH, os.path.join(DRIVE_ROOT, 'cookies.txt'))
                except Exception:
                    pass
            return os.path.basename(root)
    return None

def cb_save_cookies(text, persist_drive=True):
    try:
        content = _validate_cookie_content(_normalize_cookies(text))
        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        os.chmod(COOKIES_PATH, 0o600)
        saved_drive = False
        if persist_drive and _drive_on():
            os.makedirs(DRIVE_ROOT, exist_ok=True)
            shutil.copy(COOKIES_PATH, os.path.join(DRIVE_ROOT, 'cookies.txt'))
            saved_drive = True
        s = _cookie_summary(); s['saved_drive'] = saved_drive
        return JSON({'ok': True, 'cookies': s})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

def cb_clear_cookies(also_drive=False):
    try:
        if os.path.exists(COOKIES_PATH): os.remove(COOKIES_PATH)
        if also_drive:
            for root in [DRIVE_ROOT] + LEGACY_DRIVE_ROOTS:
                p = os.path.join(root, 'cookies.txt')
                if os.path.exists(p): os.remove(p)
        return JSON({'ok': True, 'cookies': _cookie_summary()})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_test_cookies():
    try:
        if not os.path.exists(COOKIES_PATH):
            return JSON({'ok': False, 'error': 'Nenhum cookie carregado.'})
        opts = _base_opts(); opts.update({'extract_flat': True, 'playlistend': 1, 'ignoreerrors': True})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info('https://www.youtube.com/feed/history', download=False)
        ok = bool(info and (info.get('entries') is not None))
        return JSON({'ok': True, 'valid': ok,
                     'message': 'Cookies válidos: sua conta foi reconhecida pelo YouTube.' if ok
                     else 'O YouTube não reconheceu a sessão. Exporte os cookies novamente com a conta logada.'})
    except Exception as e:
        return JSON({'ok': True, 'valid': False, 'message': _friendly_error(str(e))})

# ---------- bootstrap ----------
def _model_ready(model):
    return model in STATE.setdefault('ready_models', set())

def cb_bootstrap():
    try:
        migrated = _restore_cookies_from_drive()
        return JSON({'ok': True, 'app': APP_NAME, 'version': APP_VERSION, 'user': STATE['user'], 'drive': _drive_on(),
                     'cookies': _cookie_summary(), 'cookies_migrated_from': migrated,
                     'ytdlp': yt_dlp.version.__version__, 'js_runtime': next(iter(_detect_js_runtime()), None),
                     'gpu': _gpu_info(), 'port': FILE_PORT, 'mock': MOCK, 'max_upload_mb': MAX_UPLOAD_MB,
                     'max_duration': MAX_DURATION, 'separator': SEP_AVAILABLE,
                     'modes': {k: {'label': v['label'], 'stems': v['stems'], 'factor': v['factor'], 'base': v['base'],
                                   'ready': _model_ready(v['model'])} for k, v in MODES.items()},
                     'stem_pt': STEM_PT, 'stem_icon': STEM_ICON, 'stem_color': STEM_COLOR})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- análise / prévia ----------
def _res_label(h):
    names = {4320: '8K', 2160: '4K UHD', 1440: '2K QHD', 1080: 'Full HD', 720: 'HD', 480: 'SD', 360: 'Baixa', 240: 'Muito baixa', 144: 'Mínima'}
    return names.get(h, '')

def _summarize_video(info):
    vids, auds, seen_aud = {}, [], set()
    duration = info.get('duration') or 0
    for f in info.get('formats') or []:
        vcodec, acodec = f.get('vcodec') or 'none', f.get('acodec') or 'none'
        size = f.get('filesize') or f.get('filesize_approx') or 0
        if not size and duration and f.get('tbr'):
            size = int(f['tbr'] * 1000 / 8 * duration)  # estimativa por bitrate
        if vcodec != 'none' and f.get('height'):
            h = int(f['height'])
            cand = {
                'height': h, 'fps': int(round(f.get('fps') or 0)), 'ext': f.get('ext'),
                'vcodec': vcodec.split('.')[0], 'size': size, 'tbr': f.get('tbr') or 0,
                'hdr': (f.get('dynamic_range') or 'SDR') != 'SDR', 'has_audio': acodec != 'none',
            }
            cur = vids.get(h)
            if (cur is None or (cand['fps'], cand['tbr']) > (cur['fps'], cur['tbr'])):
                vids[h] = cand
        elif acodec != 'none' and vcodec == 'none':
            if 'drc' in (f.get('format_id') or '') or 'DRC' in (f.get('format_note') or ''):
                continue
            abr = int(round(f.get('abr') or f.get('tbr') or 0))
            key = (f.get('ext'), acodec.split('.')[0], abr // 8, f.get('language'))
            if key in seen_aud: continue
            seen_aud.add(key)
            auds.append({'format_id': f.get('format_id'), 'ext': f.get('ext'), 'acodec': acodec.split('.')[0],
                         'abr': abr, 'size': size, 'lang': f.get('language'), 'note': f.get('format_note')})
    best_audio = max([a['size'] for a in auds] or [0])
    resolutions = []
    for h in sorted(vids, reverse=True):
        v = vids[h]
        est = (v['size'] + (0 if v['has_audio'] else best_audio)) if v['size'] else 0
        resolutions.append({**v, 'size_label': _fmt_size(est), 'size': est, 'label': _res_label(h)})
    auds.sort(key=lambda a: -a['abr'])
    return {
        'id': info.get('id'), 'title': info.get('title'), 'channel': info.get('uploader') or info.get('channel'),
        'channel_url': info.get('uploader_url') or info.get('channel_url'),
        'duration': duration, 'duration_str': _hms(duration),
        'views': info.get('view_count'), 'likes': info.get('like_count'),
        'upload_date': info.get('upload_date'), 'thumbnail': _thumb(info),
        'description': (info.get('description') or '')[:600],
        'is_live': bool(info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming')),
        'age_limit': info.get('age_limit') or 0, 'availability': info.get('availability'),
        'url': info.get('webpage_url') or f"https://www.youtube.com/watch?v={info.get('id')}",
        'resolutions': resolutions,
        'audio_formats': [{**a, 'size_label': _fmt_size(a['size'])} for a in auds],
        'too_long': duration > MAX_DURATION,
    }

def _register_youtube_source(v):
    """Registra o vídeo analisado como fonte para a separação de faixas."""
    src_id = uuid.uuid4().hex[:10]
    STATE['sources'][src_id] = {
        'id': src_id, 'kind': 'youtube', 'video_id': v['id'], 'title': v['title'], 'channel': v['channel'],
        'duration': v['duration'], 'duration_str': v['duration_str'], 'thumbnail': v['thumbnail'], 'url': v['url'],
        'wav': None, 'created': time.time(), 'too_long': v['too_long'],
    }
    return src_id

def _summarize_entry(e, idx):
    vid = e.get('id')
    return {
        'index': idx, 'id': vid, 'title': e.get('title') or f'Vídeo {idx}',
        'url': e.get('url') if (e.get('url') or '').startswith('http') else f'https://www.youtube.com/watch?v={vid}',
        'duration': e.get('duration'), 'channel': e.get('uploader') or e.get('channel'),
        'views': e.get('view_count'),
        'thumbnail': _thumb(e) or f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg',
        'unavailable': (e.get('title') in ('[Private video]', '[Deleted video]')) or e.get('availability') in ('private', 'premium_only', 'needs_auth', 'subscriber_only'),
    }

def _extract_playlist(pl_url, is_mix=False):
    opts = _base_opts(); opts.update({'extract_flat': 'in_playlist', 'ignoreerrors': True, 'playlistend': MAX_PLAYLIST})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(pl_url, download=False)
    mix_msg = ('Este link é um Mix automático do YouTube (list=RD…). O YouTube só gera Mixes dentro do player e não permite '
               'listá-los por fora, então não dá para baixá-lo como playlist. Você pode baixar o vídeo, ou salvar os vídeos '
               'do Mix em uma playlist sua no YouTube e colar o link dela aqui.')
    if not info:
        raise RuntimeError(mix_msg if is_mix else 'O YouTube não retornou a playlist (pode exigir login/cookies ou estar indisponível).')
    if info.get('_type') != 'playlist' and not info.get('entries'):
        raise RuntimeError(mix_msg if is_mix else 'Este link não retornou uma playlist.')
    entries = [e for e in (info.get('entries') or []) if e]
    items = [_summarize_entry(e, i + 1) for i, e in enumerate(entries)]
    if not items:
        raise RuntimeError('A playlist veio vazia. Se ela for privada ou "não listada", carregue os cookies da sua conta.')
    total_dur = sum((i['duration'] or 0) for i in items)
    return {
        'id': info.get('id'), 'title': info.get('title') or ('Mix do YouTube' if is_mix else 'Playlist'),
        'channel': info.get('uploader') or info.get('channel') or ('YouTube' if is_mix else None), 'url': pl_url,
        'count': len(items), 'total_duration': total_dur, 'is_mix': is_mix,
        'thumbnail': _thumb(info) or (items[0]['thumbnail'] if items else None),
        'description': (info.get('description') or '')[:400],
        'items': items, 'truncated': len(items) >= MAX_PLAYLIST,
    }

def cb_analyze(url, mode='auto'):
    try:
        parsed = _parse_url(url, mode if mode in ('auto', 'video', 'playlist') else 'auto')
        result = {'ok': True, 'input': parsed['url'], 'mode': mode, 'video': None, 'playlist': None, 'playlist_error': None}
        if parsed['video_id']:
            opts = _base_opts(); opts['noplaylist'] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={parsed['video_id']}", download=False)
            if not info:
                raise RuntimeError('video unavailable')
            v = _summarize_video(info)
            v['source_id'] = _register_youtube_source(v)
            result['video'] = v
        if parsed['playlist_url']:
            try:
                result['playlist'] = _extract_playlist(parsed['playlist_url'], parsed['is_mix'])
            except Exception as e:
                if not result['video']:
                    raise
                result['playlist_error'] = _friendly_error(str(e))   # o vídeo continua utilizável
        return JSON(result)
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

# ---------- upload de arquivo local (em pedaços base64) ----------
def cb_upload_start(name, size):
    try:
        size = int(size or 0)
        if size <= 0:
            raise ValueError('Arquivo vazio.')
        if size > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f'O arquivo tem {_fmt_size(size)}. O limite é {MAX_UPLOAD_MB} MB.')
        ext = os.path.splitext(name or '')[1].lower()
        if ext not in UPLOAD_EXTS:
            raise ValueError('Formato não suportado. Envie MP3, WAV, FLAC, M4A, OGG, OPUS, AIFF ou um vídeo MP4/WEBM/MKV/MOV.')
        up_id = uuid.uuid4().hex[:10]
        path = os.path.join(WORK_DIR, f'upload_{up_id}{ext}')
        open(path, 'wb').close()
        STATE['uploads'][up_id] = {'path': path, 'name': name, 'size': size, 'received': 0}
        return JSON({'ok': True, 'upload_id': up_id})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_upload_chunk(up_id, data_b64):
    try:
        up = STATE['uploads'].get(up_id)
        if not up: raise ValueError('Envio não encontrado. Tente novamente.')
        if len(data_b64) > 4 * 1024 * 1024:
            raise ValueError('Bloco de upload muito grande.')
        chunk = base64.b64decode(data_b64, validate=True)
        if up['received'] + len(chunk) > min(up['size'], MAX_UPLOAD_MB * 1024 * 1024):
            raise ValueError('O bloco excede o tamanho declarado do arquivo.')
        with open(up['path'], 'ab') as f:
            f.write(chunk)
        up['received'] += len(chunk)
        return JSON({'ok': True, 'received': up['received']})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_upload_finish(up_id):
    try:
        up = STATE['uploads'].pop(up_id, None)
        if not up: raise ValueError('Envio não encontrado. Tente novamente.')
        if up['received'] != up['size']:
            os.remove(up['path'])
            raise ValueError(f'Envio incompleto ({_fmt_size(up["received"])} de {_fmt_size(up["size"])}). Tente novamente.')
        dur = _ffprobe_duration(up['path'])
        if dur <= 0:
            os.remove(up['path'])
            raise ValueError('Não consegui ler este arquivo como áudio. Verifique se ele não está corrompido.')
        src_id = uuid.uuid4().hex[:10]
        title = os.path.splitext(os.path.basename(up['name']))[0]
        src = {'id': src_id, 'kind': 'file', 'title': title, 'channel': None, 'duration': dur, 'duration_str': _hms(dur),
               'file_name': up['name'], 'file_size': up['size'], 'file_size_label': _fmt_size(up['size']),
               'thumbnail': None, 'url': None, 'wav': None, 'src_path': up['path'],
               'created': time.time(), 'too_long': dur > MAX_DURATION}
        STATE['sources'][src_id] = src
        return JSON({'ok': True, 'source': src})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- tarefas: estrutura comum ----------
def _stage(job, key, label, status='running', percent=None):
    for s in job['stages']:
        if s['key'] == key:
            s['status'] = status
            if percent is not None: s['percent'] = percent
            if status == 'running':
                s['started'] = s.get('started') or time.time()
            if status in ('done', 'error'):
                s['ended'] = time.time()
        elif s['status'] == 'running' and status == 'running':
            s['status'] = 'done'; s['percent'] = 100; s['ended'] = time.time()
    if job.get('stage') != key: job['detail'] = ''
    job['stage'] = key; job['stage_label'] = label
    if percent is not None: job['percent'] = percent
    if status == 'running': job['status'] = 'running'

def _copy_to_drive(job, path, sub):
    if not job.get('save_drive'):
        return None
    try:
        if not _drive_on():
            raise OSError('Google Drive desconectado')
        root = os.path.realpath(DRIVE_ROOT)
        d = os.path.realpath(os.path.join(root, sub))
        if os.path.commonpath((root, d)) != root:
            raise ValueError('Pasta de destino inválida.')
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, os.path.basename(path))
        # Reserva o nome sem sobrescrever arquivos de tarefas anteriores.
        base, ext = os.path.splitext(dst)
        index = 1
        while True:
            try:
                target = open(dst, 'xb')
                break
            except FileExistsError:
                dst = f'{base} ({index}){ext}'
                index += 1
        try:
            with target, open(path, 'rb') as source:
                shutil.copyfileobj(source, target)
        except Exception:
            try: os.remove(dst)
            except OSError: pass
            raise
        return dst.replace(DRIVE_MYDRIVE, 'Meu Drive', 1)
    except Exception as e:
        warning = 'Arquivo disponível nesta sessão, mas a cópia no Drive falhou: ' + str(e)
        job['warning'] = warning
        job.setdefault('drive_warnings', []).append(warning)
        return None

def _final_path(info, out_dir, before):
    rd = (info or {}).get('requested_downloads') or []
    if rd and rd[0].get('filepath') and os.path.exists(rd[0]['filepath']):
        return rd[0]['filepath']
    for k in ('filepath', '_filename', 'filename'):
        p = (info or {}).get(k)
        if p and os.path.exists(p): return p
    cands = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
             if f not in before and not f.endswith(('.part', '.ytdl', '.webp', '.jpg', '.png'))]
    return max(cands, key=os.path.getmtime) if cands else None

# ---------- download de vídeo / áudio (um ou vários itens) ----------
def _dl_progress(job, st):
    """Atualiza o progresso geral da tarefa a partir do item atual."""
    items = job['items']; total = len(items)
    finished = sum(1 for s in items if s['status'] in ('done', 'error', 'cancelled'))
    cur_pct = (st.get('percent') or 0) / 100 if st['status'] in ('downloading', 'processing') else 0
    job['percent'] = ((finished + cur_pct) / total * 100) if total else 0
    idx = items.index(st) + 1
    job['stage_label'] = (f'{idx}/{total} · ' if total > 1 else '') + (st.get('stage') or '')
    job['detail'] = st.get('title') or ''

def _progress_hook(d, job, st):
    _check_cancel(job)
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        done = d.get('downloaded_bytes') or 0
        info = d.get('info_dict') or {}
        stream = 'áudio' if (info.get('vcodec') in (None, 'none')) else 'vídeo'
        st.update({
            'status': 'downloading', 'percent': (done / total * 100) if total else 0,
            'downloaded': done, 'total': total, 'speed': d.get('speed') or 0, 'eta': d.get('eta'),
            'stage': (f'Baixando {stream} completo para cortar…' if job.get('trim') else f'Baixando {stream}…'),
        })
    elif d['status'] == 'finished':
        st.update({'percent': 100, 'stage': 'Download concluído, processando…'})
    _dl_progress(job, st)

def _pp_hook(d, job, st):
    _check_cancel(job)
    names = {'FFmpegExtractAudio': 'Convertendo áudio…', 'FFmpegVideoRemuxer': 'Empacotando MP4…',
             'FFmpegMerger': 'Juntando vídeo e áudio…', 'FFmpegMetadata': 'Gravando metadados…',
             'EmbedThumbnail': 'Inserindo capa…', 'MoveFiles': 'Finalizando…'}
    if d['status'] in ('started', 'processing'):
        st.update({'status': 'processing', 'stage': names.get(d.get('postprocessor'), 'Processando…')})
        _dl_progress(job, st)

def _build_dl_opts(job, st, out_dir):
    mode, height = job['mode'], job['height']
    audio_format, audio_quality, embed_meta = job['audio_format'], job['audio_quality'], job['embed_meta']
    opts = _base_opts()
    opts.update({
        'outtmpl': os.path.join(out_dir, '%(title).150B [%(id)s].%(ext)s'),
        'noplaylist': True, 'overwrites': True, 'windowsfilenames': True, 'concurrent_fragment_downloads': 4,
        'progress_hooks': [lambda d: _progress_hook(d, job, st)],
        'postprocessor_hooks': [lambda d: _pp_hook(d, job, st)],
        'postprocessors': [],
    })
    if job.get('trim'):
        # Recorte por tempo: o arquivo completo é baixado (rápido, com progresso) e cortado
        # depois com ffmpeg em _cut_clip. Capa/metadados são aplicados no corte, não aqui.
        opts['outtmpl'] = os.path.join(out_dir, '_completo_%(id)s.%(ext)s')
        embed_meta = False
    if mode == 'audio':
        opts['format'] = 'ba/b'
        if audio_format != 'best' and not job.get('trim'):
            pp = {'key': 'FFmpegExtractAudio', 'preferredcodec': audio_format}
            if audio_format not in ('wav', 'flac') and audio_quality and audio_quality != 'best':
                pp['preferredquality'] = str(audio_quality)
            elif audio_format == 'mp3':
                pp['preferredquality'] = '0'  # melhor VBR
            opts['postprocessors'].append(pp)
        if embed_meta:
            opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
            if audio_format in ('mp3', 'm4a', 'flac', 'opus', 'aac'):
                opts['writethumbnail'] = True
                opts['postprocessors'].append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
    else:
        sort = [f'res:{height}' if height and height != 'best' else 'res', 'fps', 'codec:avc1:m4a', 'ext:mp4:m4a']
        opts['format'] = 'bv*+ba/b'
        opts['format_sort'] = sort
        opts['merge_output_format'] = 'mp4'
        opts['postprocessors'].append({'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
        if embed_meta:
            opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
    return opts

def _cut_clip(job, st, src_path, info, out_dir):
    """Corta [start, end] do arquivo completo com ffmpeg, mostrando progresso.
    Vídeo: H.264. Áudio: recodificação para corte preciso; original mantém pacotes."""
    trim = job['trim']; start, end = float(trim['start']), float(trim['end'])
    dur_total = float((info or {}).get('duration') or 0) or _ffprobe_duration(src_path)
    if dur_total and start >= dur_total:
        raise RuntimeError(f'O início do trecho ({_hms(start)}) passa da duração do vídeo ({_hms(dur_total)}).')
    if dur_total:
        end = min(end, dur_total)
    length = end - start
    if length < 0.5:
        raise RuntimeError('O trecho ficou curto demais depois de ajustar ao tamanho do vídeo.')
    title = _safe_name((info or {}).get('title') or st.get('title') or 'video', 140)
    ext = ('mp4' if job['mode'] == 'video' else job['audio_format'])
    if ext == 'best':
        ext = os.path.splitext(src_path)[1].lstrip('.') or 'm4a'
    tag = f"(trecho {_hms(start).replace(':', '.')}-{_hms(end).replace(':', '.')})"
    dst = os.path.join(out_dir, f"{title} [{(info or {}).get('id') or st.get('id')}] {tag}.{ext}")
    meta = ['-metadata', f"title={(info or {}).get('title') or ''} {tag}",
            '-metadata', f"artist={(info or {}).get('uploader') or (info or {}).get('channel') or ''}",
            '-metadata', f"comment={(info or {}).get('webpage_url') or ''}"]
    if job['mode'] == 'video':
        codec = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart']
        mapping = ['-map', '0:v:0', '-map', '0:a:0?']
    else:
        fmt = job['audio_format']
        quality = job['audio_quality']
        bitrate = quality if quality != 'best' else '320'
        codec = {
            'mp3': ['-c:a', 'libmp3lame'] + (['-q:a', '0'] if quality == 'best' else ['-b:a', bitrate + 'k']),
            'm4a': ['-c:a', 'aac', '-b:a', bitrate + 'k'],
            'opus': ['-c:a', 'libopus', '-b:a', bitrate + 'k'],
            'wav': ['-c:a', 'pcm_s24le'], 'flac': ['-c:a', 'flac'],
            'best': ['-c:a', 'copy'],
        }[fmt]
        mapping = ['-map', '0:a:0', '-vn']
        if fmt == 'best':
            job['warning'] = 'No formato original, o recorte segue os pacotes de áudio e pode variar alguns milissegundos. Para corte preciso, escolha outro formato.'
    if not job.get('embed_meta', True):
        meta = []
    progress = os.path.join(out_dir, f'cut_{st.get("id") or "x"}.progress')
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', progress,
           '-ss', f'{start:.3f}', '-i', src_path, '-t', f'{length:.3f}'] + mapping + ['-map_metadata', '-1'] + meta + codec + [dst]
    st.update({'status': 'processing', 'stage': 'Cortando trecho…' + (' (recodificando vídeo)' if job['mode'] == 'video' else ''), 'percent': 0})
    _dl_progress(job, st)
    def on_progress(pct):
        st['percent'] = max(st.get('percent') or 0, pct); _dl_progress(job, st)
    try:
        _run_process(job, cmd, timeout=3600, progress_file=progress, progress_total=length, on_progress=on_progress)
    finally:
        if os.path.exists(progress): os.remove(progress)
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        raise RuntimeError('Falha ao cortar o trecho: o ffmpeg não gerou o arquivo.')
    try: os.remove(src_path)
    except OSError: pass
    st['percent'] = 100
    return dst

def _run_download_job(job):
    out_dir = os.path.join(OUT_DIR, job['id']); os.makedirs(out_dir, exist_ok=True)
    job['status'] = 'running'
    is_video = job['mode'] == 'video'
    for st in job['items']:
        if job.get('cancel'):
            st.update({'status': 'cancelled', 'stage': 'Cancelado'}); continue
        st.update({'status': 'downloading', 'stage': 'Preparando…', 'percent': 0})
        _dl_progress(job, st)
        try:
            opts = _build_dl_opts(job, st, out_dir)
            logger = _SilentLogger(); opts['logger'] = logger
            opts['ignoreerrors'] = False  # Nunca tratar uma conversão incompleta como arquivo final.
            before = set(os.listdir(out_dir))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(st['url'], download=True)
            _check_cancel(job)
            path = _final_path(info, out_dir, before)
            if not path:
                raise RuntimeError(logger.errors[-1] if logger.errors else 'O arquivo final não foi encontrado após o download.')
            if logger.errors:
                st['warning'] = _friendly_error(logger.errors[-1])
            if job.get('trim'):
                path = _cut_clip(job, st, path, info, out_dir)
            preview = os.path.join(out_dir, st['id'] + ('.preview.mp4' if is_video else '.preview.mp3'))
            st.update({'status': 'processing', 'stage': 'Preparando prévia…'})
            _dl_progress(job, st)
            preview_ok = _make_video_preview(path, preview, job) if is_video else _make_preview(path, preview, job)
            size = os.path.getsize(path)
            drive_path = _copy_to_drive(job, path, os.path.join('Downloads', job.get('folder') or ''))
            st.update({'status': 'done', 'percent': 100, 'stage': 'Concluído',
                       'file': os.path.basename(path), 'rel': f"{job['id']}/{os.path.basename(path)}",
                       'size': size, 'size_label': _fmt_size(size), 'drive_path': drive_path,
                       'preview': f"{job['id']}/{os.path.basename(preview)}" if preview_ok else None,
                       'preview_kind': 'video' if is_video else 'audio',
                       'title': (info or {}).get('title') or st.get('title')})
        except yt_dlp.utils.DownloadCancelled:
            st.update({'status': 'cancelled', 'stage': 'Cancelado'})
        except Exception as e:
            st.update({'status': 'error', 'stage': 'Erro', 'error': _friendly_error(str(e))})
        _dl_progress(job, st)
    done = [s for s in job['items'] if s['status'] == 'done']
    errs = [s for s in job['items'] if s['status'] == 'error']
    job['files'] = [{'stem': 'Video' if is_video else 'Audio', 'label': s.get('title') or s['file'],
                     'icon': '🎬' if is_video else '🎵', 'color': '#ff5c7a' if is_video else '#38bdf8',
                     'file': s['file'], 'rel': s['rel'], 'size': s['size'], 'size_label': s['size_label'],
                     'preview': s.get('preview'), 'preview_kind': s.get('preview_kind'), 'drive_path': s.get('drive_path'), 'warning': s.get('warning')} for s in done]
    job['done_items'], job['error_items'] = len(done), len(errs)
    if errs and done:
        job['warning'] = f"{len(errs)} de {len(job['items'])} {'item falhou' if len(errs) == 1 else 'itens falharam'}. Use \"Tentar novamente\" para repetir só os que deram erro."
    if job.get('cancel'):
        raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')
    if errs and not done:
        raise RuntimeError(errs[0].get('error') or 'Nenhum arquivo foi baixado.')
    job['stage_label'] = 'Concluído'; job['detail'] = ''

def _parse_trim(trim, items):
    """Valida o recorte {start, end} em segundos. Só para um vídeo por vez."""
    if not trim:
        return None
    if len(items) != 1:
        raise ValueError('O recorte por tempo só funciona com um vídeo por vez.')
    try:
        start = max(0.0, float(trim.get('start') or 0))
        end = float(trim.get('end'))
    except Exception:
        raise ValueError('Tempos do recorte inválidos. Use o formato mm:ss ou hh:mm:ss.')
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError('Tempos do recorte inválidos.')
    if end <= start:
        raise ValueError('O fim do trecho precisa ser maior que o início.')
    if end - start < 1:
        raise ValueError('O trecho precisa ter pelo menos 1 segundo.')
    return {'start': start, 'end': end}

def _new_download_job(payload):
    items = payload.get('items') or []
    if not isinstance(items, list) or not items:
        raise ValueError('Nenhum vídeo selecionado.')
    if len(items) > MAX_PLAYLIST:
        raise ValueError(f'No máximo {MAX_PLAYLIST} vídeos por tarefa.')
    mode = payload.get('mode', 'video')
    if mode not in ('video', 'audio'):
        raise ValueError('Tipo de download inválido.')
    height = payload.get('height', 'best')
    if height != 'best':
        try: height = int(height)
        except Exception: raise ValueError('Resolução inválida.')
        if not 100 <= height <= 8640: raise ValueError('Resolução inválida.')
    audio_format = payload.get('audio_format', 'mp3')
    if audio_format not in AUDIO_FORMATS:
        raise ValueError('Formato de áudio inválido.')
    audio_quality = str(payload.get('audio_quality', 'best'))
    if audio_quality not in AUDIO_QUALITIES:
        raise ValueError('Qualidade de áudio inválida.')
    clean_items = []
    seen = set()
    for it in items:
        vid = str(it.get('id') or '')
        url = str(it.get('url') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid):
            raise ValueError('Identificador de vídeo inválido na seleção.')
        if not url.startswith('http'):
            url = f'https://www.youtube.com/watch?v={vid}'
        parsed = _parse_url(url, 'video')
        if parsed.get('video_id') != vid:
            raise ValueError('O link não corresponde ao identificador do vídeo.')
        if vid in seen:
            continue
        seen.add(vid)
        url = f'https://www.youtube.com/watch?v={vid}'
        clean_items.append({'id': vid, 'url': url, 'title': str(it.get('title') or vid)[:200],
                            'thumbnail': str(it.get('thumbnail') or '')[:500] or f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg',
                            'status': 'queued', 'percent': 0, 'stage': 'Na fila'})
    trim = _parse_trim(payload.get('trim'), clean_items)
    folder = re.sub(r'[^\w\s.-]', '', str(payload.get('folder') or ''))[:80].strip().strip('.')
    first = clean_items[0]
    n = len(clean_items)
    if mode == 'video':
        qual = 'melhor resolução' if height == 'best' else f'{height}p'
    else:
        qual = 'áudio original' if audio_format == 'best' else audio_format.upper() + ('' if audio_quality == 'best' or audio_format in ('wav', 'flac') else f' {audio_quality} kbps')
    label = (f'{n} vídeos · ' if n > 1 else '') + ('Vídeo MP4 · ' if mode == 'video' else 'Áudio · ') + qual
    if trim: label += f" · trecho {_hms(trim['start'])}–{_hms(trim['end'])}"
    return {
        'kind': 'download', 'mode': mode, 'height': height, 'audio_format': audio_format, 'audio_quality': audio_quality,
        'embed_meta': bool(payload.get('embed_meta', True)), 'folder': folder, 'trim': trim,
        'title': str(payload.get('title') or (first['title'] if n == 1 else f"{first['title']} e mais {n - 1}"))[:200],
        'thumbnail': first['thumbnail'], 'label': label, 'items': clean_items, 'duration': 0,
        'stages': [{'key': 'fetch', 'label': 'Baixar do YouTube', 'status': 'pending', 'percent': 0},
                   {'key': 'export', 'label': 'Converter e finalizar', 'status': 'pending', 'percent': 0}],
    }

# ---------- separação de faixas (IA) ----------
def _download_youtube_audio(job, src, out_dir, tag='src'):
    """Baixa o áudio original (m4a/webm) de um vídeo, sem conversão."""
    opts = _base_opts()
    logger = _SilentLogger(); opts['logger'] = logger
    def hook(d):
        _check_cancel(job)
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            done = d.get('downloaded_bytes') or 0
            job['percent'] = (done / total * 100) if total else 0
            job['detail'] = f"{_fmt_size(done) or '0 B'}{' de ' + _fmt_size(total) if total else ''}" + (f" · {_fmt_size(d['speed'])}/s" if d.get('speed') else '')
        elif d['status'] == 'finished':
            job['percent'] = 100; job['detail'] = ''
    opts.update({
        'outtmpl': os.path.join(out_dir, f'{tag}_%(id)s.%(ext)s'),
        'noplaylist': True, 'overwrites': True, 'windowsfilenames': True, 'concurrent_fragment_downloads': 4,
        'format': 'ba/b', 'progress_hooks': [hook], 'postprocessors': [], 'ignoreerrors': False,
    })
    before = set(os.listdir(out_dir))
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(src['url'], download=True)
    _check_cancel(job)
    path = _final_path(info, out_dir, before)
    if not path:
        raise RuntimeError(logger.errors[-1] if logger.errors else 'O arquivo não foi encontrado após o download.')
    if logger.errors:
        job['warning'] = _friendly_error(logger.errors[-1])
    return path

def _ensure_source_wav(job, src):
    """Garante um WAV 44.1 kHz estéreo da fonte (baixando do YouTube se preciso). Fica em cache por fonte."""
    if src.get('wav') and os.path.exists(src['wav']):
        _stage(job, 'fetch', 'Áudio já disponível', 'done', 100)
        return src['wav']
    src_dir = os.path.join(WORK_DIR, src['id']); os.makedirs(src_dir, exist_ok=True)
    if src['kind'] == 'youtube':
        _stage(job, 'fetch', 'Baixando áudio do YouTube…', 'running', 0)
        raw = _download_youtube_audio(job, src, src_dir, tag='src')
    else:
        raw = src['src_path']
    _stage(job, 'fetch', 'Preparando o áudio…', 'running', 100)
    job['detail'] = 'Convertendo para WAV 44.1 kHz'
    wav = os.path.join(src_dir, 'source.wav')
    _run_process(job, ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', raw,
                       '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s24le', wav])
    src['wav'] = wav
    if not src.get('duration'):
        src['duration'] = _ffprobe_duration(wav); src['duration_str'] = _hms(src['duration'])
    job['detail'] = ''
    return wav

def _sep_cmd():
    exe = shutil.which('audio-separator')
    return [exe] if exe else [sys.executable, '-m', 'audio_separator.utils.cli']

def _iter_output(stream, job, proc, timeout=7200):
    lines = queue.Queue()
    def read():
        buf = ''
        try:
            while True:
                ch = stream.read(1)
                if not ch: break
                if ch in ('\r', '\n'):
                    if buf.strip(): lines.put(buf)
                    buf = ''
                else:
                    buf = (buf + ch)[-4000:]
            if buf: lines.put(buf)
        finally:
            lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    started = time.monotonic()
    while True:
        _check_cancel(job)
        if time.monotonic() - started > timeout:
            raise TimeoutError('A separação excedeu duas horas. Tente um áudio mais curto.')
        try: line = lines.get(timeout=0.2)
        except queue.Empty: continue
        if line is None: return
        yield line

def _run_separator(job, wav, mode, out_format, out_dir, names):
    cfg = MODES[mode]
    cmd = _sep_cmd() + [wav, '--model_filename', cfg['model'],
           '--model_file_dir', MODELS_DIR, '--output_dir', out_dir, '--output_format', OUT_FORMATS[out_format],
           '--custom_output_names', json.dumps(names), '--log_level', 'info']
    if out_format == 'mp3':
        cmd += ['--output_bitrate', '320k']
    if cfg['model'].endswith('.yaml'):
        cmd += ['--demucs_shifts', '1']
    if _gpu_info()['available']:
        cmd += ['--use_autocast']   # precisão mista na GPU: bem mais rápido, qualidade praticamente igual
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', TQDM_MININTERVAL='0.5')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='ignore', env=env, bufsize=0)
    job['proc'] = proc
    tail, err_hint = [], None
    started = time.time(); phase_started = None
    est = cfg['base'] + (job.get('duration') or 180) * cfg['factor']
    onde = 'na GPU' if (_gpu_info()['available']) else 'no processador'
    if _model_ready(cfg['model']):
        _stage(job, 'model', f'Carregando o modelo {onde}…', 'running', 0)
    else:
        _stage(job, 'model', 'Baixando o modelo de IA (uma vez por sessão)…', 'running', 0)
    try:
        for line in _iter_output(proc.stdout, job, proc):
            if job.get('cancel'):
                proc.kill(); raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')
            tail.append(line[:300]); tail[:] = tail[-40:]
            low = line.lower()
            m = re.search(r'(\d{1,3})%\|', line)  # barras do tqdm (download do modelo / separação)
            if 'starting separation' in low:
                _stage(job, 'separate', f'Separando as faixas {onde}…', 'running', 0); phase_started = time.time(); job['detail'] = ''
            elif 'loading model' in low and job['stage'] == 'model':
                job['detail'] = 'Carregando pesos…'
            elif ' saving ' in low or 'writing output' in low:
                if job['stage'] == 'separate': job['detail'] = 'Gravando arquivos…'
            elif m and job['stage'] == 'model':
                job['percent'] = int(m.group(1)); job['detail'] = f'Baixando modelo… {m.group(1)}%'
            elif m and job['stage'] == 'separate':
                job['percent'] = max(job['percent'], min(99, int(m.group(1)))); job['detail'] = f'{m.group(1)}%'
            if ('error' in low or 'traceback' in low) and 'errorlevel' not in low:
                err_hint = line
            if job['stage'] == 'separate' and phase_started and not m:
                job['percent'] = max(job['percent'], min(95, (time.time() - phase_started) / max(est, 1) * 100))
        proc.wait()
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait()
        job['proc'] = None
        try: proc.stdout.close()
        except Exception: pass
    if job.get('cancel'):
        raise yt_dlp.utils.DownloadCancelled('Cancelado pelo usuário')
    if proc.returncode != 0:
        msg = err_hint or (tail[-1] if tail else f'o separador retornou código {proc.returncode}')
        job['log_tail'] = tail[-15:]
        raise RuntimeError(_friendly_error(msg))
    job['sep_seconds'] = round(time.time() - started)

def _run_separator_mock(job, wav, mode, out_format, out_dir, names):
    """Modo de teste local: gera 'faixas' com filtros do ffmpeg, sem IA."""
    filters = {'Vocals': 'highpass=f=1200', 'Instrumental': 'lowpass=f=1200', 'Drums': 'lowpass=f=200',
               'Bass': 'lowpass=f=120', 'Guitar': 'bandpass=f=800:w=400', 'Piano': 'bandpass=f=1500:w=600', 'Other': 'highpass=f=3000'}
    _stage(job, 'model', 'Carregando o modelo (simulação)…', 'running', 0); time.sleep(1.0)
    _stage(job, 'separate', 'Separando as faixas (simulação)…', 'running', 0)
    stems = MODES[mode]['stems']
    for i, stem in enumerate(stems):
        _check_cancel(job)
        ext = out_format
        dst = os.path.join(out_dir, f'{names[stem]}.{ext}')
        codec = ['-c:a', 'libmp3lame', '-b:a', '320k'] if ext == 'mp3' else (['-c:a', 'flac'] if ext == 'flac' else ['-c:a', 'pcm_s16le'])
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', wav, '-af', filters[stem]] + codec + [dst], check=True)
        job['percent'] = (i + 1) / len(stems) * 100; time.sleep(0.4)
    job['sep_seconds'] = 3

def _make_video_preview(src_path, dst_path, job):
    """Prévia completa H.264/AAC em até 480p, sem alterar o vídeo para download."""
    try:
        _run_process(job, ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src_path,
                          '-map', '0:v:0', '-map', '0:a:0?', '-vf',
                          "scale=w='min(854,iw)':h='min(480,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
                          '-r', '24', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30',
                          '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
                          '-ac', '2', '-movflags', '+faststart', dst_path], timeout=3600)
        return os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0
    except yt_dlp.utils.DownloadCancelled:
        raise
    except Exception:
        if os.path.exists(dst_path): os.remove(dst_path)
        job['warning'] = 'O vídeo foi gerado, mas sua prévia não pôde ser criada. Use Baixar para abrir o arquivo.'
        return False

def _make_preview(src_path, dst_path, job):
    try:
        _run_process(job, ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', src_path,
                          '-vn', '-ac', '2', '-ar', '44100', '-c:a', 'libmp3lame', '-b:a', '96k', dst_path])
        return os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0
    except yt_dlp.utils.DownloadCancelled:
        raise
    except Exception:
        if os.path.exists(dst_path): os.remove(dst_path)
        job['warning'] = 'Os arquivos foram gerados, mas uma prévia não pôde ser criada. Baixe as faixas para ouvir.'
        return False

def _run_separate_job(job):
    src = STATE['sources'][job['source_id']]
    job['duration'] = src.get('duration') or 0
    out_dir = os.path.join(OUT_DIR, job['id']); os.makedirs(out_dir, exist_ok=True)
    wav = _ensure_source_wav(job, src)
    if not job['duration']:
        job['duration'] = _ffprobe_duration(wav)
    if job['duration'] > MAX_DURATION:
        raise RuntimeError(f'Este áudio tem {_hms(job["duration"])}. O limite é {MAX_DURATION // 60} minutos para não estourar a memória da GPU.')
    mode, fmt = job['mode'], job['out_format']
    base = _safe_name(src['title'])
    names = {stem: f'stemtube_{stem.lower()}' for stem in MODES[mode]['stems']}   # nomes internos simples
    _stage(job, 'model', 'Aguardando disponibilidade do modelo…', 'running', 0)
    while not MODEL_LOCK.acquire(timeout=0.2):
        _check_cancel(job)
    try:
        _check_cancel(job)
        (_run_separator_mock if MOCK else _run_separator)(job, wav, mode, fmt, out_dir, names)
        if not MOCK: STATE.setdefault('ready_models', set()).add(MODES[mode]['model'])
    finally:
        MODEL_LOCK.release()
    _stage(job, 'export', 'Preparando prévias e arquivos…', 'running', 0)
    files = []
    stems = MODES[mode]['stems']
    for i, stem in enumerate(stems):
        _check_cancel(job)
        cand = [f for f in os.listdir(out_dir) if f.lower().startswith(names[stem]) and not f.endswith('.preview.mp3')]
        if not cand:
            raise RuntimeError(f'A faixa "{STEM_PT[stem]}" não foi gerada pelo separador.' + (' Detalhes: ' + ' | '.join(job.get('log_tail') or [])[-300:] if job.get('log_tail') else ''))
        path = os.path.join(out_dir, f'{base} - {STEM_PT[stem]}{os.path.splitext(cand[0])[1]}')
        os.replace(os.path.join(out_dir, cand[0]), path)
        prev = os.path.join(out_dir, f'{stem.lower()}.preview.mp3')
        _make_preview(path, prev, job)
        size = os.path.getsize(path)
        files.append({'stem': stem, 'label': STEM_PT[stem], 'icon': STEM_ICON[stem], 'color': STEM_COLOR[stem],
                      'file': os.path.basename(path), 'rel': f"{job['id']}/{os.path.basename(path)}",
                      'preview': f"{job['id']}/{os.path.basename(prev)}" if os.path.exists(prev) else None,
                      'size': size, 'size_label': _fmt_size(size),
                      'drive_path': _copy_to_drive(job, path, os.path.join('Faixas', base, job['id']))})
        job['percent'] = (i + 1) / len(stems) * 100
    orig_prev = os.path.join(out_dir, 'original.preview.mp3')   # prévia do original para comparação no mixer
    if _make_preview(wav, orig_prev, job):
        job['original_preview'] = f"{job['id']}/original.preview.mp3"
    job['files'] = files
    _stage(job, 'export', 'Concluído', 'done', 100)

def _new_separate_job(payload):
    src = STATE['sources'].get(payload.get('source_id'))
    if not src:
        raise ValueError('Fonte não encontrada. Analise o link ou envie o arquivo novamente.')
    if not SEP_AVAILABLE:
        raise ValueError('O separador de faixas não está instalado. Rode a célula 1 com a opção "instalar_separador_ia" marcada.')
    mode = payload.get('mode'); fmt = payload.get('out_format', 'wav')
    if mode not in MODES: raise ValueError('Modo de separação inválido.')
    if fmt not in OUT_FORMATS: raise ValueError('Formato de saída inválido.')
    if src.get('too_long'):
        raise ValueError(f'Este áudio tem {src["duration_str"]}. O limite para separação é {MAX_DURATION // 60} minutos.')
    job = {'kind': 'separate', 'source_id': src['id'], 'title': src['title'], 'thumbnail': src.get('thumbnail'),
           'duration': src.get('duration') or 0, 'mode': mode, 'mode_label': MODES[mode]['label'], 'out_format': fmt,
           'stems': MODES[mode]['stems'], 'label': f"{MODES[mode]['label']} · {fmt.upper()}",
           'stages': [{'key': 'fetch', 'label': 'Obter o áudio', 'status': 'pending', 'percent': 0},
                      {'key': 'model', 'label': 'Modelo de IA', 'status': 'pending', 'percent': 0},
                      {'key': 'separate', 'label': 'Separar na GPU', 'status': 'pending', 'percent': 0},
                      {'key': 'export', 'label': 'Exportar faixas', 'status': 'pending', 'percent': 0}]}
    if not MOCK and not _gpu_info()['available']:
        job['warning'] = 'Sem GPU nesta sessão: a separação vai rodar no processador e pode demorar muitos minutos.'
    return job

# ---------- mixagem ----------
def cb_mix_job(parent_id, tracks, out_format='wav', save_drive=False):
    """Cria uma mixagem independente sem alterar as faixas da separação."""
    try:
        parent = STATE['jobs'].get(parent_id)
        if not parent or parent['status'] != 'done' or parent['kind'] != 'separate':
            raise ValueError('Conclua uma separação antes de renderizar a mixagem.')
        if out_format not in OUT_FORMATS:
            raise ValueError('Escolha WAV, FLAC ou MP3.')
        if not isinstance(tracks, list) or not 1 <= len(tracks) <= len(parent['files']):
            raise ValueError('Selecione ao menos uma faixa audível para renderizar.')
        available = {f['stem']: f for f in parent['files']}
        selected, seen = [], set()
        for item in tracks:
            stem = item.get('stem'); gain = float(item.get('gain', 1))
            if stem not in available or stem in seen or not math.isfinite(gain) or not 0 < gain <= 1:
                raise ValueError('Seleção de faixas ou volume inválido.')
            seen.add(stem)
            f = available[stem]
            _output_path(f['rel'])
            selected.append({'stem': stem, 'gain': gain, 'rel': f['rel'], 'label': f['label']})
        label = ' + '.join(f['label'] for f in selected)
        job = _enqueue({'kind': 'mix', 'parent_id': parent_id, 'source_id': parent['source_id'],
                        'title': parent['title'], 'thumbnail': parent.get('thumbnail'), 'duration': parent.get('duration') or 0,
                        'save_drive': bool(save_drive), 'out_format': out_format, 'mix_tracks': selected,
                        'label': f'Mixagem: {label} · {out_format.upper()}',
                        'stages': [{'key': 'export', 'label': 'Renderizar mixagem', 'status': 'pending', 'percent': 0}]})
        return JSON({'ok': True, 'job_id': job['id'], 'ahead': job['ahead']})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

def _run_mix_job(job):
    out_dir = os.path.join(OUT_DIR, job['id']); os.makedirs(out_dir, exist_ok=True)
    fmt = job['out_format']
    filename = _safe_name(job['title'], 65) + ' - Mixagem.' + fmt
    path = os.path.join(out_dir, filename)
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    filters, labels = [], []
    for i, track in enumerate(job['mix_tracks']):
        cmd += ['-i', _output_path(track['rel'])]
        filters.append(f'[{i}:a]aresample=44100,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={track["gain"]:.8f}[s{i}]')
        labels.append(f'[s{i}]')
    # Em 44100 Hz, padding/corte de 219 amostras compensam attack=5 sem exigir latency.
    filters.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,apad=pad_len=219,alimiter=limit=0.98:level=false:attack=5,atrim=start_sample=219,asetpts=PTS-STARTPTS[mix]')
    codec = {'wav': ['-c:a', 'pcm_s24le'], 'flac': ['-c:a', 'flac'], 'mp3': ['-c:a', 'libmp3lame', '-b:a', '320k']}[fmt]
    progress = os.path.join(out_dir, 'render.progress')
    cmd += ['-filter_complex', ';'.join(filters), '-map', '[mix]', '-vn', '-ar', '44100'] + codec
    cmd += ['-progress', progress, '-nostats', path]
    _stage(job, 'export', 'Renderizando mixagem…', 'running', 0)
    job['detail'] = ' + '.join(t['label'] for t in job['mix_tracks'])
    try:
        _run_process(job, cmd, progress_file=progress)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError('A mixagem não gerou um arquivo de áudio válido.')
        _check_cancel(job)
        drive = _copy_to_drive(job, path, os.path.join('Mixagens', job['id']))
        size = os.path.getsize(path)
        prev = os.path.join(out_dir, 'mix.preview.mp3')
        job['files'] = [{'stem': 'Mix', 'label': 'Mixagem', 'icon': '🎛', 'color': '#34d399',
                         'file': filename, 'rel': f"{job['id']}/{filename}", 'size': size, 'size_label': _fmt_size(size),
                         'preview': f"{job['id']}/mix.preview.mp3" if _make_preview(path, prev, job) else None, 'drive_path': drive}]
        _stage(job, 'export', 'Mixagem concluída', 'done', 100)
    except BaseException:
        if os.path.exists(path): os.remove(path)
        raise
    finally:
        if os.path.exists(progress): os.remove(progress)

# ---------- fila: duas pistas (downloads e processamento na GPU rodam em paralelo) ----------
LANES = {'download': 'download', 'separate': 'process', 'mix': 'process'}
JOB_QUEUES = STATE.setdefault('queues', {'download': queue.Queue(), 'process': queue.Queue()})

def _run_job(job_id):
    job = STATE['jobs'][job_id]
    job['started'] = time.time()
    try:
        {'separate': _run_separate_job, 'mix': _run_mix_job, 'download': _run_download_job}[job['kind']](job)
        _check_cancel(job)
        job['status'] = 'done'; job['percent'] = 100
        for s in job['stages']:
            if s['status'] in ('pending', 'running'): s['status'] = 'done'; s['percent'] = 100
    except yt_dlp.utils.DownloadCancelled:
        job['status'] = 'cancelled'; job['stage_label'] = 'Cancelado'
        for s in job['stages']:
            if s['status'] == 'running': s['status'] = 'cancelled'
    except Exception as e:
        job['status'] = 'error'; job['error'] = _friendly_error(str(e)); job['stage_label'] = 'Erro'
        for s in job['stages']:
            if s['status'] == 'running': s['status'] = 'error'
    job['finished'] = time.time()
    job['elapsed'] = round(job['finished'] - job['started'])

def _worker(lane):
    q = JOB_QUEUES[lane]
    while True:
        job_id = q.get()
        try:
            job = STATE['jobs'].get(job_id)
            if job and job.get('cancel'):
                job['status'] = 'cancelled'; job['stage_label'] = 'Cancelado'; job['finished'] = time.time()
                for it in job.get('items') or []: it.update({'status': 'cancelled', 'stage': 'Cancelado'})
            elif job:
                _run_job(job_id)
        except Exception as e:
            job = STATE['jobs'].get(job_id)
            if job:
                job['status'] = 'error'; job['error'] = _friendly_error(str(e)); job['finished'] = time.time()
        finally:
            q.task_done()

def _ensure_workers():
    workers = STATE.setdefault('workers', {})
    for lane in JOB_QUEUES:
        w = workers.get(lane)
        if not w or not w.is_alive():
            w = threading.Thread(target=_worker, args=(lane,), daemon=True); w.start()
            workers[lane] = w

def _ahead_of(job):
    lane = LANES[job['kind']]
    return sum(1 for j in STATE['jobs'].values() if j['id'] != job['id'] and LANES[j['kind']] == lane
               and j['status'] in ('queued', 'running') and j['created'] < job['created'])

def _enqueue(job):
    job_id = uuid.uuid4().hex[:10]
    job.update({'id': job_id, 'status': 'queued', 'cancel': False, 'created': time.time(), 'percent': 0, 'detail': '',
                'stage': None, 'stage_label': 'Na fila', 'error': None})
    job.setdefault('files', []); job.setdefault('items', []); job.setdefault('warning', None); job.setdefault('save_drive', False)
    STATE['jobs'][job_id] = job
    job['ahead'] = _ahead_of(job)
    JOB_QUEUES[LANES[job['kind']]].put(job_id); _ensure_workers()
    return job

def cb_start_job(payload):
    try:
        kind = payload.get('kind')
        if kind == 'download':
            job = _new_download_job(payload)
        elif kind == 'separate':
            job = _new_separate_job(payload)
        else:
            return JSON({'ok': False, 'error': 'Tipo de tarefa inválido.'})
        job['save_drive'] = bool(payload.get('save_drive'))
        _enqueue(job)
        return JSON({'ok': True, 'job_id': job['id'], 'ahead': job['ahead']})
    except Exception as e:
        return JSON({'ok': False, 'error': _friendly_error(str(e))})

def _job_view(job):
    v = {k: val for k, val in job.items() if k not in ('cancel', 'proc', 'mix_tracks')}
    v['ok'] = True
    if job['status'] == 'running' and job.get('started'):
        v['elapsed'] = round(time.time() - job['started'])
    v['ahead'] = _ahead_of(job) if job['status'] == 'queued' else 0
    return v

def cb_job_status(job_id):
    job = STATE['jobs'].get(job_id)
    if not job:
        return JSON({'ok': False, 'error': 'Tarefa não encontrada.'})
    return JSON(_job_view(job))

def cb_jobs_list():
    try:
        out = []
        for j in sorted(STATE['jobs'].values(), key=lambda x: x['created']):
            out.append({'id': j['id'], 'kind': j['kind'], 'status': j['status'], 'label': j.get('label'), 'title': j.get('title'),
                        'thumbnail': j.get('thumbnail'), 'percent': round(j.get('percent') or 0), 'stage_label': j.get('stage_label'),
                        'detail': j.get('detail'), 'error': j.get('error'), 'created': j['created'], 'files': len(j.get('files') or []),
                        'items': len(j.get('items') or []), 'errors': j.get('error_items') or 0})
        return JSON({'ok': True, 'jobs': out, 'active': any(j['status'] in ('queued', 'running') for j in STATE['jobs'].values())})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_cancel_job(job_id):
    job = STATE['jobs'].get(job_id)
    if job and job.get('status') in ('queued', 'running'):
        job['cancel'] = True
        p = job.get('proc')
        if p:
            try: p.kill()
            except Exception: pass
    return JSON({'ok': True})

def cb_zip_job(job_id):
    try:
        job = STATE['jobs'].get(job_id)
        if not job or job.get('status') not in ('done', 'cancelled') or not job.get('files'):
            return JSON({'ok': False, 'error': 'Nenhum arquivo para compactar.'})
        src = os.path.join(OUT_DIR, job_id)
        name = _safe_name(job.get('folder') or job.get('title') or 'arquivos', 60)
        tmp = os.path.join(OUT_DIR, f'{job_id}_zipsrc'); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
        for f in job['files']:
            shutil.copy2(os.path.join(src, f['file']), os.path.join(tmp, f['file']))
        zp = shutil.make_archive(os.path.join(OUT_DIR, f'{job_id}_{re.sub(r"[^\w.-]+", "_", name)}'), 'zip', tmp)
        shutil.rmtree(tmp, ignore_errors=True)
        sub = {'download': 'Downloads', 'separate': 'Faixas', 'mix': 'Mixagens'}[job['kind']]
        drive = _copy_to_drive(job, zp, sub) if job.get('save_drive') else None
        return JSON({'ok': True, 'rel': os.path.basename(zp), 'size_label': _fmt_size(os.path.getsize(zp)), 'drive_path': drive})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_colab_download(rel):
    """Download pelo mecanismo nativo do Colab (vai direto para a pasta Downloads do navegador)."""
    try:
        path = _output_path(rel)
        from google.colab import files as colab_files
        colab_files.download(path)
        return JSON({'ok': True})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_preview_b64(rel):
    """Plano B do mixer: entrega a prévia em base64 pela ponte do Colab quando o proxy de portas não responde."""
    try:
        path = _output_path(rel, preview=True)
        if os.path.getsize(path) > 32 * 1024 * 1024:
            raise ValueError('Use o carregamento em blocos para esta prévia.')
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return JSON({'ok': True, 'b64': data, 'mime': 'video/mp4' if path.endswith('.mp4') else 'audio/mpeg'})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_preview_chunk(rel, offset=0):
    """Transfere prévias em blocos pequenos quando o proxy do Colab falha."""
    try:
        path = _output_path(rel, preview=True)
        total = os.path.getsize(path)
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= total:
            raise ValueError('Posição da prévia inválida.')
        with open(path, 'rb') as stream:
            stream.seek(offset)
            chunk = stream.read(512 * 1024)
        return JSON({'ok': True, 'b64': base64.b64encode(chunk).decode('ascii'),
                     'offset': offset, 'next_offset': offset + len(chunk), 'total': total,
                     'mime': 'video/mp4' if path.endswith('.mp4') else 'audio/mpeg'})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

def cb_cleanup():
    try:
        for j in list(STATE['jobs'].values()):
            if j['status'] in ('queued', 'running'):
                return JSON({'ok': False, 'error': 'Há tarefas em andamento. Aguarde ou cancele antes de limpar.'})
        shutil.rmtree(OUT_DIR, ignore_errors=True); os.makedirs(OUT_DIR, exist_ok=True)
        shutil.rmtree(WORK_DIR, ignore_errors=True); os.makedirs(WORK_DIR, exist_ok=True)
        STATE['jobs'].clear(); STATE['sources'].clear(); STATE['uploads'].clear()
        return JSON({'ok': True})
    except Exception as e:
        return JSON({'ok': False, 'error': str(e)})

# ---------- pré-download do modelo padrão (em segundo plano) ----------
def _prefetch_model(model):
    if MOCK or not SEP_AVAILABLE or _model_ready(model) or STATE['prefetch'].get(model):
        return
    STATE['prefetch'][model] = 'running'
    def run():
        with MODEL_LOCK:
            try:
                if not _model_ready(model):
                    subprocess.run(_sep_cmd() + ['--download_model_only', '--model_filename', model,
                                   '--model_file_dir', MODELS_DIR, '--log_level', 'warning'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800, check=True)
                    STATE.setdefault('ready_models', set()).add(model)
                STATE['prefetch'][model] = 'done'
            except Exception:
                STATE['prefetch'][model] = 'failed'
    threading.Thread(target=run, daemon=True).start()

def cb_models_status():
    return JSON({'ok': True, 'separator': SEP_AVAILABLE,
                 'models': {k: {'ready': _model_ready(v['model']), 'prefetch': STATE['prefetch'].get(v['model'])} for k, v in MODES.items()}})

# ---------- servidor de arquivos (prévias do mixer, com suporte a Range) ----------
class _FileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=OUT_DIR, **k)
    def log_message(self, *a): pass
    def list_directory(self, path):
        self.send_error(403, 'Listagem desabilitada'); return None
    def do_HEAD(self):
        try:
            rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).lstrip('/')
            _output_path(rel)
        except (ValueError, OSError):
            self.send_error(404); return
        super().do_HEAD()
    def do_GET(self):
        try:
            rel = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).lstrip('/')
            path = _output_path(rel)
        except (ValueError, OSError):
            self.send_error(404); return
        size = os.path.getsize(path)
        rng = self.headers.get('Range')
        start, end = 0, size - 1
        if rng:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', rng)
            try:
                if not match or not any(match.groups()) or size == 0: raise ValueError()
                a, b = match.groups()
                if a:
                    start = int(a); end = min(int(b), size - 1) if b else size - 1
                else:
                    suffix = int(b)
                    if suffix <= 0: raise ValueError()
                    start = max(0, size - suffix)
                if start >= size or end < start: raise ValueError()
            except ValueError:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.send_header('Content-Length', '0'); self.end_headers(); return
        ctype = self.guess_type(path)
        self.send_response(206 if rng else 200)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if rng: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        with open(path, 'rb') as f:
            f.seek(start); remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): break
                remaining -= len(chunk)

def _start_file_server():
    if STATE.get('server'): return
    class _Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True; daemon_threads = True
    try:
        srv = _Srv(('0.0.0.0', FILE_PORT), _FileHandler)
    except OSError as e:
        raise RuntimeError('A porta de prévias está ocupada. Reinicie a sessão e execute as células 1 e 2.') from e
    STATE['server'] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()

_start_file_server()
_ensure_workers()
_prefetch_model(MODES['2stem']['model'])

# ---------- registro das funções para a interface ----------
def _register(name, fn):
    try:
        from google.colab import output as _out
        _out.register_callback(f'stemtube.{name}', fn)
    except Exception:
        pass

for _n, _f in {
    'bootstrap': cb_bootstrap, 'save_cookies': cb_save_cookies, 'clear_cookies': cb_clear_cookies, 'test_cookies': cb_test_cookies,
    'analyze': cb_analyze, 'upload_start': cb_upload_start, 'upload_chunk': cb_upload_chunk, 'upload_finish': cb_upload_finish,
    'start_job': cb_start_job, 'job_status': cb_job_status, 'jobs_list': cb_jobs_list, 'cancel_job': cb_cancel_job,
    'zip_job': cb_zip_job, 'colab_download': cb_colab_download, 'cleanup': cb_cleanup, 'models_status': cb_models_status,
    'preview_b64': cb_preview_b64, 'preview_chunk': cb_preview_chunk, 'mix_job': cb_mix_job,
}.items():
    _register(_n, _f)
