"""Testes locais do backend do StemTube Studio (sem Colab, sem YouTube, sem GPU).

Executa o backend em modo simulado (STEMTUBE_MOCK=1) e verifica: análise de links,
cookies, upload em pedaços, separação simulada, mixagem, ZIP, validação de tarefas de
download, servidor de arquivos (Range e bloqueio de travessia) e limpeza.

Requer: python, ffmpeg/ffprobe no PATH, yt-dlp e ipython instalados.
Uso:  python src/tests/test_backend.py
"""
import os, sys, time, json, base64, subprocess, tempfile, urllib.request, urllib.parse, urllib.error

os.environ['STEMTUBE_MOCK'] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
TEST_ROOT = os.path.join(tempfile.gettempdir(), 'stemtube_test').replace(os.sep, '/')

src = (open(os.path.join(SRC, 'backend.py'), encoding='utf-8').read()
       .replace("'/content/stemtube'", repr(TEST_ROOT))
       .replace('FILE_PORT     = 8767', 'FILE_PORT     = 8768'))   # porta própria: não colide com o dev_server
ns = {'USER_EMAIL': 'teste@gmail.com'}
exec(compile(src, 'backend.py', 'exec'), ns)

passed = 0
def check(cond, label):
    global passed
    if not cond:
        raise AssertionError('FALHOU: ' + label)
    passed += 1
    print('  ok  ', label)

def wait_job(job_id, limit=120):
    for _ in range(int(limit / 0.2)):
        j = ns['cb_job_status'](job_id).data
        if j['status'] in ('done', 'error', 'cancelled'):
            return j
        time.sleep(0.2)
    raise TimeoutError(job_id)

print('1) bootstrap')
b = ns['cb_bootstrap']().data
check(b['ok'] and b['mock'] and b['separator'] and b['version'], 'bootstrap responde em modo simulado')
check(set(b['modes']) == {'2stem', '4stem', '6stem'}, 'três modos de separação')

print('2) links do YouTube')
P = ns['_parse_url']
check(P('https://www.youtube.com/watch?v=dQw4w9WgXcQ')['video_id'] == 'dQw4w9WgXcQ', 'watch?v=')
check(P('youtu.be/dQw4w9WgXcQ')['video_id'] == 'dQw4w9WgXcQ', 'youtu.be sem protocolo')
check(P('https://music.youtube.com/watch?v=dQw4w9WgXcQ')['video_id'] == 'dQw4w9WgXcQ', 'YouTube Music')
check(P('https://www.youtube.com/shorts/dQw4w9WgXcQ')['video_id'] == 'dQw4w9WgXcQ', 'Shorts')
r = P('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc123')
check(r['video_id'] and r['playlist_url'].endswith('list=PLabc123'), 'vídeo + playlist')
check(P('https://www.youtube.com/playlist?list=PLabc123')['video_id'] is None, 'playlist pura')
check(P('https://www.youtube.com/@canal')['playlist_url'].endswith('/videos'), 'canal vira aba Vídeos')
check(P('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ')['is_mix'], 'Mix automático detectado')
check(P('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc', 'video')['playlist_url'] is None, 'modo "somente vídeo" ignora playlist')
for bad in ('https://evil.com/watch?v=dQw4w9WgXcQ', 'https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ',
            'https://www.youtube.com/watch?v=curto', 'https://www.youtube.com/', 'https://user:pw@youtube.com/watch?v=dQw4w9WgXcQ'):
    try:
        P(bad); raise AssertionError('aceitou ' + bad)
    except ValueError:
        pass
check(True, 'links inválidos e domínios alheios rejeitados')
try:
    P('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'playlist'); raise AssertionError()
except ValueError:
    check(True, 'modo playlist exige list= ou canal')

print('3) cookies')
r = ns['cb_save_cookies']('.youtube.com\tTRUE\t/\tTRUE\t9999999999\tSID\tabc\n.evil.com\tTRUE\t/\tTRUE\t9999999999\tX\ty\n').data
check(r['ok'] and r['cookies']['total'] == 1 and r['cookies']['logged_in'], 'Netscape: filtra domínio alheio e reconhece login')
check(ns['cb_save_cookies']('#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t9999999999\tLOGIN_INFO\tz\n').data['cookies']['logged_in'], 'HttpOnly aceito')
check(ns['cb_save_cookies']('SID=abc; SAPISID=def').data['cookies']['logged_in'], 'cabeçalho Cookie:')
check(ns['cb_save_cookies'](json.dumps([{'domain': '.youtube.com', 'name': 'SID', 'value': '1', 'expirationDate': 1e10}])).data['ok'], 'JSON de extensão')
check(not ns['cb_save_cookies']('.evil.com\tTRUE\t/\tTRUE\t1\tA\tb\n').data['ok'], 'arquivo sem cookies do YouTube rejeitado')
check(not ns['cb_save_cookies']('texto qualquer').data['ok'], 'formato desconhecido rejeitado')
check(not ns['cb_save_cookies']('x' * (3 * 1024 * 1024)).data['ok'], 'limite de 2 MB')
check(ns['cb_clear_cookies']().data['cookies'] == {'found': False}, 'remoção de cookies')

print('4) upload + separação simulada + mixagem')
wav = os.path.join(TEST_ROOT, 'teste.wav')
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
                '-f', 'lavfi', '-i', 'sine=frequency=110:duration=3', '-filter_complex', 'amix=inputs=2', '-ac', '2', wav], check=True)
data = open(wav, 'rb').read()
check(not ns['cb_upload_start']('x.exe', 10).data['ok'], 'extensão não suportada rejeitada')
check(not ns['cb_upload_start']('x.mp3', 2 * 1024 ** 3).data['ok'], 'arquivo acima do limite rejeitado')
st = ns['cb_upload_start']('Minha música.wav', len(data)).data
check(st['ok'], 'upload iniciado')
check(not ns['cb_upload_chunk'](st['upload_id'], '!!!').data['ok'], 'base64 inválido rejeitado')
for i in range(0, len(data), 200000):
    assert ns['cb_upload_chunk'](st['upload_id'], base64.b64encode(data[i:i + 200000]).decode()).data['ok']
fin = ns['cb_upload_finish'](st['upload_id']).data
check(fin['ok'] and fin['source']['kind'] == 'file' and 2.5 < fin['source']['duration'] < 3.5, 'upload concluído e duração lida')
st2 = ns['cb_upload_start']('incompleto.wav', len(data)).data
ns['cb_upload_chunk'](st2['upload_id'], base64.b64encode(data[:1000]).decode())
check(not ns['cb_upload_finish'](st2['upload_id']).data['ok'], 'upload incompleto descartado')

check(not ns['cb_start_job']({'kind': 'separate', 'source_id': 'nope', 'mode': '2stem'}).data['ok'], 'fonte inexistente rejeitada')
check(not ns['cb_start_job']({'kind': 'separate', 'source_id': fin['source']['id'], 'mode': '9stem'}).data['ok'], 'modo inválido rejeitado')
job = ns['cb_start_job']({'kind': 'separate', 'source_id': fin['source']['id'], 'mode': '4stem', 'out_format': 'mp3'}).data
check(job['ok'], 'separação enfileirada')
j = wait_job(job['job_id'])
check(j['status'] == 'done' and len(j['files']) == 4 and all(f['preview'] for f in j['files']), 'separação simulada gerou 4 faixas com prévias')
check(j.get('original_preview') and all(s['status'] == 'done' for s in j['stages']), 'prévia do original e etapas concluídas')
check(all(f['file'].endswith('.mp3') for f in j['files']), 'formato MP3 respeitado')

check(not ns['cb_mix_job'](job['job_id'], [], 'wav').data['ok'], 'mixagem vazia rejeitada')
check(not ns['cb_mix_job'](job['job_id'], [{'stem': 'Vocals', 'gain': 2}], 'wav').data['ok'], 'ganho fora da faixa rejeitado')
mix = ns['cb_mix_job'](job['job_id'], [{'stem': 'Vocals', 'gain': 1}, {'stem': 'Bass', 'gain': 0.5}], 'flac').data
check(mix['ok'], 'mixagem enfileirada')
m = wait_job(mix['job_id'])
check(m['status'] == 'done' and m['files'][0]['file'].endswith('.flac') and m['files'][0]['preview'], 'mixagem FLAC renderizada com prévia')

z = ns['cb_zip_job'](job['job_id']).data
check(z['ok'] and z['rel'].endswith('.zip'), 'ZIP das faixas')
check(not ns['cb_zip_job']('nope').data['ok'], 'ZIP de tarefa inexistente rejeitado')

print('5) tarefas de download (validação sem rede)')
check(not ns['cb_start_job']({'kind': 'download', 'items': []}).data['ok'], 'sem itens')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'bad'}]}).data['ok'], 'id inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'x'}).data['ok'], 'modo inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'video', 'height': 'abc'}).data['ok'], 'resolução inválida')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'audio', 'audio_format': 'exe'}).data['ok'], 'formato inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}, {'id': 'dQw4w9WgXcR'}], 'trim': {'start': 0, 'end': 5}}).data['ok'], 'recorte com 2 itens rejeitado')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'trim': {'start': 5, 'end': 5.5}}).data['ok'], 'trecho curto rejeitado')
nd = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ', 'title': 'T'}], 'mode': 'audio', 'audio_format': 'mp3', 'audio_quality': '192', 'trim': {'start': 10, 'end': 70}})
check(nd['label'] == 'Áudio · MP3 192 kbps · trecho 0:10–1:10' and nd['trim']['end'] == 70, 'rótulo e recorte de download')
nd = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ'}, {'id': 'dQw4w9WgXcR'}], 'mode': 'video', 'height': 1080})
check(nd['label'].startswith('2 vídeos · Vídeo MP4 · 1080p') and nd['height'] == 1080, 'rótulo de playlist em vídeo')

print('6) fila e servidor de arquivos')
lst = ns['cb_jobs_list']().data
check(lst['ok'] and not lst['active'] and len(lst['jobs']) == 2, 'lista da fila')
check(not ns['cb_job_status']('nope').data['ok'], 'tarefa inexistente')
rel = j['files'][0]['rel']
port = ns['FILE_PORT']
req = urllib.request.Request(f'http://127.0.0.1:{port}/' + urllib.parse.quote(rel), headers={'Range': 'bytes=0-99'})
with urllib.request.urlopen(req) as resp:
    check(resp.status == 206 and resp.headers['Content-Range'].startswith('bytes 0-99/') and len(resp.read()) == 100, 'HTTP Range 206')
req = urllib.request.Request(f'http://127.0.0.1:{port}/' + urllib.parse.quote(rel), headers={'Range': 'bytes=-50'})
with urllib.request.urlopen(req) as resp:
    check(resp.status == 206 and len(resp.read()) == 50, 'HTTP Range sufixo')
try:
    urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/' + urllib.parse.quote(rel), headers={'Range': 'bytes=999999999-'}))
    raise AssertionError()
except urllib.error.HTTPError as e:
    check(e.code == 416, 'HTTP Range inválido → 416')
try:
    urllib.request.urlopen(f'http://127.0.0.1:{port}/../backend.py'); raise AssertionError()
except urllib.error.HTTPError as e:
    check(e.code == 404, 'travessia de diretório bloqueada')
try:
    urllib.request.urlopen(f'http://127.0.0.1:{port}/{job["job_id"]}/'); raise AssertionError()
except urllib.error.HTTPError as e:
    check(e.code in (403, 404), 'listagem de pasta bloqueada')
b64 = ns['cb_preview_b64'](j['files'][0]['preview']).data
check(b64['ok'] and b64['mime'] == 'audio/mpeg' and len(b64['b64']) > 100, 'prévia em base64 (plano B do mixer)')
check(not ns['cb_preview_b64'](rel).data['ok'], 'arquivo que não é prévia recusado no plano B')

print('7) regressões: downloads, recortes e Drive')
from unittest.mock import patch
payload = {'items': [{'id': 'dQw4w9WgXcQ'}, {'id': 'dQw4w9WgXcQ'}], 'mode': 'audio', 'audio_format': 'wav'}
clean = ns['_new_download_job'](payload)
check(len(clean['items']) == 1, 'seleção duplicada não sobrescreve o mesmo resultado')
try:
    ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ', 'url': 'https://youtu.be/dQw4w9WgXcR'}]})
    raise AssertionError('link divergente aceito')
except ValueError:
    check(True, 'link e identificador divergentes rejeitados')
clean = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ'}], 'folder': '..'})
check(clean['folder'] == '', 'pasta ponto-ponto neutralizada')
with patch.object(ns['subprocess'], 'run') as proc:
    proc.return_value.stdout = 'nan'
    check(ns['_ffprobe_duration']('fake') == 0, 'duração NaN rejeitada')

cutdir = tempfile.mkdtemp(dir=TEST_ROOT)
cutjob = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'audio', 'audio_format': 'wav', 'trim': {'start': 0.137, 'end': 1.637}})
opts = ns['_build_dl_opts'](cutjob, cutjob['items'][0], cutdir)
check(not opts['postprocessors'], 'recorte evita conversão completa anterior ao corte')
source = os.path.join(cutdir, 'source.wav')
ns['shutil'].copy2(wav, source)
cut = ns['_cut_clip'](cutjob, cutjob['items'][0], source, {'duration': 3}, cutdir)
check(abs(ns['_ffprobe_duration'](cut) - 1.5) < 1/44100, 'recorte WAV real tem duração precisa de 1,5 s')

for fmt in ('mp3', 'm4a', 'opus', 'flac', 'best'):
    cutjob = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'audio', 'audio_format': fmt, 'trim': {'start': 0.137, 'end': 1.637}})
    source = os.path.join(cutdir, 'source.wav')
    ns['shutil'].copy2(wav, source)
    cut = ns['_cut_clip'](cutjob, cutjob['items'][0], source, {'duration': 3}, cutdir)
    expected = 'wav' if fmt == 'best' else fmt
    check(cut.endswith('.' + expected) and abs(ns['_ffprobe_duration'](cut) - 1.5) < 0.1, 'recorte real em ' + fmt)

class FailedConversion:
    def __init__(self, opts):
        self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def extract_info(self, *args, **kwargs):
        check(self.opts['ignoreerrors'] is False, 'erro de conversão não é ignorado')
        raise ns['yt_dlp'].utils.DownloadError('conversion failed')
failed = ns['_new_download_job']({'items': [{'id': 'dQw4w9WgXcQ'}]})
failed['id'] = 'failed_conversion'
with patch.object(ns['yt_dlp'], 'YoutubeDL', FailedConversion):
    try:
        ns['_run_download_job'](failed)
        raise AssertionError('falha marcada como sucesso')
    except RuntimeError:
        check(failed['items'][0]['status'] == 'error' and not failed['files'], 'conversão falhada não produz sucesso falso')

drive_root = tempfile.mkdtemp(dir=TEST_ROOT)
old_root, old_drive = ns['DRIVE_ROOT'], ns['DRIVE_MYDRIVE']
ns['DRIVE_ROOT'], ns['DRIVE_MYDRIVE'] = os.path.join(drive_root, 'StemTube'), drive_root
drivejob = {'save_drive': True}
try:
    first = ns['_copy_to_drive'](drivejob, wav, 'Downloads')
    second = ns['_copy_to_drive'](drivejob, wav, 'Downloads')
    check(first != second and len(os.listdir(os.path.join(ns['DRIVE_ROOT'], 'Downloads'))) == 2, 'Drive preserva dois arquivos de mesmo nome')
    with patch.object(ns['shutil'], 'copyfileobj', side_effect=OSError('quota exceeded')):
        check(ns['_copy_to_drive'](drivejob, wav, 'Downloads') is None and 'quota exceeded' in drivejob['warning'], 'falha no Drive retorna aviso e preserva arquivo local')
    check(os.path.exists(wav) and len(os.listdir(os.path.join(ns['DRIVE_ROOT'], 'Downloads'))) == 2, 'cópia incompleta removida sem apagar resultados')
finally:
    ns['DRIVE_ROOT'], ns['DRIVE_MYDRIVE'] = old_root, old_drive

print('8) cancelamento e limpeza')
job2 = ns['cb_start_job']({'kind': 'separate', 'source_id': fin['source']['id'], 'mode': '6stem', 'out_format': 'wav'}).data
ns['cb_cancel_job'](job2['job_id'])
c = wait_job(job2['job_id'])
check(c['status'] == 'cancelled', 'separação cancelada')
check(ns['cb_cleanup']().data['ok'] and not ns['cb_jobs_list']().data['jobs'], 'limpeza com fila ociosa')

print(f'\nTODOS OS {passed} TESTES PASSARAM')
