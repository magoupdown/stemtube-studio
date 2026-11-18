"""Testes locais de downloads, conversão, prévias e fila."""
import os, sys, time, json, base64, subprocess, tempfile, urllib.request, urllib.parse, urllib.error

from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

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
check(b['ok'] and b['version'] and 'modes' not in b, 'inicialização do conversor')
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

print('4) upload e conversão')
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

source_id = fin['source']['id']
def local_job(mode, fmt, **options):
    return ns['cb_start_job'](dict(kind='download', source_id=source_id, mode=mode, audio_format=fmt, **options)).data
check(not local_job('video','mp3')['ok'], 'áudio sem imagem não oferece MP4')
job = local_job('audio','mp3')
j = wait_job(job['job_id'])
check(j['status'] == 'done' and j['files'][0]['preview'], 'conversão MP3 com prévia')
repeat = local_job('audio','flac',trim={'start':0.2,'end':2.2})
result = wait_job(repeat['job_id'])
check(result['status'] == 'done' and abs(ns['_ffprobe_duration'](ns['_output_path'](result['files'][0]['rel']))-2)<0.01,
      'mesmo upload reutilizado para recorte FLAC de dois segundos')
check(not ns['cb_start_job']({'kind':'separate','source_id':source_id}).data['ok'], 'ação descontinuada rejeitada')

z = ns['cb_zip_job'](job['job_id']).data
check(z['ok'] and z['rel'].endswith('.zip'), 'ZIP das faixas')
check(not ns['cb_zip_job']('nope').data['ok'], 'ZIP de tarefa inexistente rejeitado')

zip_path = Path(ns['OUT_DIR'], z['rel'])
with ZipFile(zip_path) as packed:
    check(packed.namelist() == [f['file'] for f in j['files']] and packed.testzip() is None,
          'ZIP íntegro com apenas as faixas finais')
previous = zip_path.read_bytes()
with patch.object(ZipFile, 'write', side_effect=OSError('quota')):
    check(not ns['cb_zip_job'](job['job_id']).data['ok'] and zip_path.read_bytes() == previous,
          'ZIP anterior preservado depois de uma falha')

print('5) tarefas de download (validação sem rede)')
check(not ns['cb_start_job']({'kind': 'download', 'items': []}).data['ok'], 'sem itens')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'bad'}]}).data['ok'], 'id inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'x'}).data['ok'], 'modo inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'video', 'height': 'abc'}).data['ok'], 'resolução inválida')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'mode': 'audio', 'audio_format': 'exe'}).data['ok'], 'formato inválido')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}, {'id': 'dQw4w9WgXcR'}], 'trim': {'start': 0, 'end': 5}}).data['ok'], 'recorte com 2 itens rejeitado')
check(not ns['cb_start_job']({'kind': 'download', 'items': [{'id': 'dQw4w9WgXcQ'}], 'trim': {'start': 5, 'end': 5.5}}).data['ok'], 'trecho curto rejeitado')
check(not ns['cb_start_job']({'kind':'download','items':[{'id':'dQw4w9WgXcQ'}],
                              'trim':{'start':float('nan'),'end':5}}).data['ok'], 'início NaN rejeitado')
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
check(b64['ok'] and b64['mime'] == 'audio/mpeg' and len(b64['b64']) > 100, 'prévia em base64 (reprodução alternativa)')
check(not ns['cb_preview_b64'](rel).data['ok'], 'arquivo que não é prévia recusado no plano B')

print('7) regressões: downloads, recortes e Drive')
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

print('8) prévias de áudio e vídeo e transferência em blocos')
previewdir = os.path.join(ns['OUT_DIR'], 'preview_qa')
os.makedirs(previewdir, exist_ok=True)
video_src = os.path.join(TEST_ROOT, 'test_video.mp4')
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24:duration=2',
                '-f', 'lavfi', '-i', 'sine=frequency=220:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', video_src], check=True)
video_prev = os.path.join(previewdir, 'test.preview.mp4')
check(ns['_make_video_preview'](video_src, video_prev, {}), 'prévia real de vídeo gerada')
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', video_prev]))
vs = next(x for x in probe['streams'] if x['codec_type'] == 'video')
check(vs['codec_name'] == 'h264' and vs['height'] <= 480 and any(x['codec_name']=='aac' for x in probe['streams']), 'prévia de vídeo em H.264/AAC até 480p')
check(abs(ns['_ffprobe_duration'](video_prev) - 2) < 0.1, 'prévia de vídeo preserva duração completa')
check(ns['cb_preview_b64']('preview_qa/test.preview.mp4').data['mime']=='video/mp4', 'MIME correto para prévia de vídeo')
# Mais de um bloco: verificação exata de bytes, sem enviar arquivo arbitrário pela ponte.
big = os.path.join(previewdir, 'large.preview.mp3')
content = b'0123456789' * 120000
with open(big, 'wb') as f: f.write(content)
offset = 0
rebuilt = bytearray()
while offset < len(content):
    chunk = ns['cb_preview_chunk']('preview_qa/large.preview.mp3', offset).data
    assert chunk['ok'] and chunk['offset']==offset and chunk['total']==len(content)
    decoded = base64.b64decode(chunk['b64'])
    assert len(decoded) <= 512*1024
    rebuilt.extend(decoded); offset = chunk['next_offset']
check(bytes(rebuilt)==content, 'prévia reconstruída em múltiplos blocos sem alteração')
check(not ns['cb_preview_chunk']('preview_qa/large.preview.mp3', -1).data['ok'], 'offset negativo rejeitado')
check(not ns['cb_preview_chunk']('preview_qa/large.preview.mp3', True).data['ok'], 'offset booleano rejeitado')
check(not ns['cb_preview_chunk']('preview_qa/large.preview.mp3', len(content)+1).data['ok'], 'offset acima do arquivo rejeitado')
check(not ns['cb_preview_chunk']('../cookies.txt', 0).data['ok'], 'travessia recusada na transferência em blocos')
check(not ns['cb_preview_chunk'](rel, 0).data['ok'], 'arquivo final que não é prévia recusado')

class SuccessfulDownload:
    def __init__(self, opts): self.opts=opts
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def extract_info(self, *args, **kwargs):
        target = os.path.join(os.path.dirname(self.opts['outtmpl']), 'download' + ('.mp4' if video_mode else '.wav'))
        ns['shutil'].copy2(video_src if video_mode else wav, target)
        return {'filepath':target,'title':'Teste','duration':2 if video_mode else 3}
with open(video_src, 'rb') as f:
    video_bytes = f.read()
upload = ns['cb_upload_start']('ensaio.mp4', len(video_bytes)).data['upload_id']
ns['cb_upload_chunk'](upload, base64.b64encode(video_bytes).decode())
video = ns['cb_upload_finish'](upload).data['source']
check(video['height'] == 360 and video['audio_codec'] == 'aac', 'upload detecta imagem e áudio')
for mode, fmt, expected in [('video','mp3','mp4'), ('audio','best','m4a'), ('audio','wav','wav')]:
    task = ns['cb_start_job']({'kind':'download','source_id':video['id'],'mode':mode,'height':240,'audio_format':fmt}).data
    result = wait_job(task['job_id'])
    check(result['status']=='done' and result['files'][0]['file'].endswith('.'+expected), 'conversão local '+expected)
    path = ns['_output_path'](result['files'][0]['rel'])
    streams = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',path]))['streams']
    if mode == 'video':
        check(any(v.get('height')==240 for v in streams), 'MP4 respeita resolução')
    else:
        check(all(v['codec_type']=='audio' for v in streams), 'extração contém apenas áudio')

for video_mode in (False,True):
    dj = ns['_new_download_job']({'items':[{'id':'dQw4w9WgXcQ'}], 'mode':'video' if video_mode else 'audio','audio_format':'wav'})
    dj['id']='qa_video_download' if video_mode else 'qa_audio_download'
    with patch.object(ns['yt_dlp'],'YoutubeDL',SuccessfulDownload): ns['_run_download_job'](dj)
    check(bool(dj['files'][0]['preview']) and dj['files'][0]['preview_kind']==('video' if video_mode else 'audio'), 'download inclui prévia '+('de vídeo' if video_mode else 'de áudio'))

print('9) cancelamento e limpeza')
job2 = local_job('audio', 'wav')
ns['cb_cancel_job'](job2['job_id'])
c = wait_job(job2['job_id'])
check(c['status'] == 'cancelled', 'conversão cancelada')
check(ns['cb_cleanup']().data['ok'] and not ns['cb_jobs_list']().data['jobs'], 'limpeza com fila ociosa')

print(f'\nTODOS OS {passed} TESTES PASSARAM')
