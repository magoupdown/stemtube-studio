"""Fluxo local da nova aba. Requer Playwright, Chromium e as dependências de test_backend.py."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Event
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]



def render_output(context, external):
    """Executa a parte de apresentação da célula gerada, incluindo seus literais reais."""
    cell = json.loads((ROOT / 'StemTube.ipynb').read_text())['cells'][2]
    code = ''.join(cell['source'])
    def fail(message):
        raise AssertionError(message)

    ctx = dict(context, _json=json, _pronto=True, abrir_em_nova_aba=external,
               _HTML=str, _erro=fail)
    outputs = []
    ctx['_display'] = outputs.append
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('APP_HTML', 'LAUNCHER'):
                ctx[node.targets[0].id] = ast.literal_eval(node.value)
    exec(code[code.rindex('\nif _pronto:'):], ctx)
    return outputs[0]


def fit(page):
    dimensions = page.locator('#stemtube').evaluate("""root => ({
      width: root.getBoundingClientRect().width, height:root.getBoundingClientRect().height,
      viewport:innerWidth, viewportHeight:innerHeight, scroll:document.documentElement.scrollWidth,
      clipped: [...root.querySelectorAll('button, input, select')].filter(el => {
        const r = el.getBoundingClientRect(); return r.width && (r.left < -1 || r.right > innerWidth+1)
      }).map(el => el.id || el.textContent.trim())
    })""")
    assert dimensions['width'] == dimensions['viewport'] == dimensions['scroll'], dimensions
    assert dimensions['height'] >= dimensions['viewportHeight'], dimensions
    assert not dimensions['clipped'], dimensions


def run():
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
        backend = (ROOT / 'src/backend.py').read_text().replace("'/content/stemtube'", repr(tmp))
        backend = backend.replace('FILE_PORT     = 8767', 'FILE_PORT     = 0')
        ns = {'USER_EMAIL': 'studio@example.test'}
        exec(compile(backend, 'backend.py', 'exec'), ns)
        ns['FILE_PORT'] = ns['STATE']['server'].server_address[1]
        ns['DRIVE_MYDRIVE'] = str(Path(tmp) / 'drive')
        ns['DRIVE_ROOT'] = str(Path(ns['DRIVE_MYDRIVE']) / 'StemTube')
        ns['LEGACY_DRIVE_ROOTS'] = []
        browser = pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'), args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 900}, has_touch=True, is_mobile=True)
        errors = []
        fail_next_chunk = False
        def invoke(name, args):
            nonlocal fail_next_chunk
            if name == 'download_chunk' and args[1] > 0 and fail_next_chunk:
                fail_next_chunk = False
                data = {'ok': False, 'error': 'Interrupção de teste'}
            else:
                data = ns['cb_' + name](*args).data
            return {'data': {'application/json': data}}
        context.expose_function('invokeBackend', invoke)
        bridge = """<script>window.google={colab:{kernel:{
          invokeFunction:(name,args)=>invokeBackend(name.slice(9),args),
          proxyPort:async port=>'http://127.0.0.1:'+port+'/'
        }}};</script>"""
        home, output = 'http://notebook.test/', 'http://output.test/'
        context.route(home, lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=
                      '<iframe sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts" src="'+output+'"></iframe>'))
        context.route(output, lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=bridge + render_output(ns, True)))
        context.route('https://fonts.googleapis.com/**', lambda route: route.abort())
        notebook = context.new_page()
        notebook.goto(home)
        launch = notebook.frame_locator('iframe').get_by_role('button')
        with context.expect_page() as opened:
            launch.click()
        app = opened.value
        app.on('pageerror', lambda error: errors.append(str(error)))
        expect(app.locator('#userName')).to_have_text(ns['USER_EMAIL'])
        assert app.evaluate('opener === null')
        assert notebook.frame_locator('iframe').locator('#stemtube').count() == 0
        for width, height in [(1440,900),(768,1024),(390,844),(320,568),(844,390)]:
            app.set_viewport_size({'width':width, 'height':height})
            fit(app)
            for link in app.locator('.cookie-links a').all():
                expect(link).to_be_in_viewport()
                assert link.get_attribute('target') == '_blank'
        for device in ['celular', 'computador']:
            guide = app.locator('.cookie-how').filter(has=app.locator('summary', has_text='Como exportar no '+device))
            guide.locator('summary').click()
            expect(guide.locator('ol')).to_contain_text('Current Site')
            fit(app)
            guide.locator('summary').click()
        app.locator('#chipCookies').click()
        expect(app.locator('label[for=cookiesFile]')).to_be_visible()
        expect(app.locator('#cookiesTestBtn')).to_be_visible()
        app.locator('#cookiesCard summary').click()
        launch.click()
        assert len(context.pages) == 2
        app.set_viewport_size({'width':360,'height':780})
        wav = Path(tmp) / 'ensaio.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anoisesrc=duration=16:sample_rate=48000', str(wav)], check=True)
        app.locator('[data-src=file]').click()
        app.locator('#fileInput').set_input_files(wav)
        app.locator('#toOptionsBtn').click()
        fit(app)
        expect(app.locator('[data-action]')).to_have_count(1)
        app.locator('[data-af=flac]').click()
        app.locator('#startBtn').click()
        expect(app.locator('#resultCard [data-dl]')).to_be_visible(timeout=60000)
        fit(app)
        expect(app.locator('.preview-play')).to_be_enabled(timeout=30000)
        button = app.locator('#resultCard [data-dl]').first
        source = Path(ns['_output_path'](button.get_attribute('data-dl')))
        assert source.stat().st_size > 1024 * 1024
        button.evaluate("""b => {
          window.samples = [];
          new MutationObserver(() => window.samples.push({
            percent: parseFloat(b.style.getPropertyValue('--filled')),
            hue: b.style.getPropertyValue('--fill-hue'), label:b.textContent, busy:b.disabled
          })).observe(b,{childList:true});
        }""")
        fail_next_chunk = True
        button.click()
        expect(button).to_have_text('↻ Tentar baixar')
        expect(button).to_be_enabled()
        with app.expect_download() as audio_file:
            button.click()
        expect(button).to_have_text('✓ 100%')
        assert audio_file.value.suggested_filename == source.name
        assert audio_file.value.path().read_bytes() == source.read_bytes()
        samples = app.evaluate('window.samples')
        assert any(0 < s['percent'] < 100 and s['busy'] and str(s['percent'])+'%' in s['label'] for s in samples)
        assert len({s['hue'] for s in samples}) >= 3
        fit(app)
        # Exercita o caminho de gravação em disco com um destino controlado.
        button.evaluate('''b => {
          b.dataset.size = String(64 * 1024 * 1024);
          window.savedParts = [];
          window.showSaveFilePicker = async () => ({createWritable: async () => ({
            write: bytes => window.savedParts.push(bytes),
            close: () => {window.savedSize = new Blob(window.savedParts).size;}
          })});
        }''')
        button.click()
        app.wait_for_function('window.savedSize > 0')
        assert app.evaluate('window.savedSize') == source.stat().st_size
        expect(button).to_have_text('✓ 100%')
        # A fonte de rede é substituída. A seleção, conversão de prévias e ZIP usam o fluxo real.
        ids = ['dQw4w9WgXcQ', 'dQw4w9WgXcR']
        continue_download = Event()
        class PlaylistFixture:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def extract_info(self, url, download):
                if not download:
                    return {'_type':'playlist', 'id':'PLteste', 'title':'Repertório',
                            'entries':[{'id':v, 'title':'Aula '+v, 'duration':2} for v in ids]}
                for hook in self.opts.get('progress_hooks', []):
                    hook({'status':'downloading', 'total_bytes':100, 'downloaded_bytes':42,
                          'info_dict':{'vcodec':'none'}})
                if not continue_download.wait(15):
                    raise RuntimeError('O teste não liberou o download.')
                video_id = url[-11:]
                target = Path(self.opts['outtmpl']).parent / (video_id + '.wav')
                shutil.copyfile(wav, target)
                return {'title':video_id, 'filepath':str(target), 'duration':2}

        from unittest.mock import patch
        with patch.object(ns['yt_dlp'], 'YoutubeDL', PlaylistFixture):
            app.locator('#newBtn').click()
            app.locator('[data-src=yt]').click()
            app.locator('#urlInput').fill('https://www.youtube.com/playlist?list=PLteste')
            app.locator('#analyzeBtn').click()
            app.locator('#selNone').click()
            expect(app.locator('#toOptionsBtn')).to_be_disabled()
            app.locator('#selAll').click()
            app.locator('#toOptionsBtn').click()
            expect(app.locator('[data-action]')).to_have_count(2)
            app.locator('[data-action=audio]').click()
            app.locator('[data-af=wav]').click()
            app.locator('#startBtn').click()
            app.locator('#modal [data-r="1"]').click()
            try:
                start = app.locator('#procDownloadSlot #startBtn')
                expect(start).to_have_text('Baixando áudio 42%')
                expect(start).to_be_disabled()
                fit(app)
                app.set_viewport_size({'width':1440,'height':900})
                fit(app)
            finally:
                continue_download.set()
            with app.expect_download(timeout=60000) as archive:
                app.locator('#zipBtn').click(timeout=30000)
            expect(app.locator('#zipBtn')).to_have_text('✓ 100%')
            with ZipFile(archive.value.path()) as saved:
                assert len(saved.namelist()) == 2 and saved.testzip() is None
        # Um arquivo local concluído com falha de cópia no Drive.
        ns['STATE']['jobs']['drive_test'] = {
            'id':'drive_test', 'created':1, 'kind':'download', 'status':'done', 'title':'Ensaio',
            'items':[{'id':'clip','title':'Ensaio','status':'done','drive_path':None}],
            'files':[], 'save_drive':True, 'mode':'audio'
        }
        app.close()
        with context.expect_page() as reopened:
            launch.click()
        reopened_app = reopened.value
        reopened_app.locator('[data-view=drive_test]').click()
        expect(reopened_app.locator('#resultCard')).to_contain_text('Drive: 0 de 1')
        reopened_app.close()
        frame = notebook.frames[1]
        frame.evaluate('window.open = () => null')
        launch.click()
        expect(frame.get_by_role('status')).to_contain_text('bloqueou')
        frame.set_content(bridge + render_output(ns, False))
        expect(frame.locator('#userName')).to_have_text(ns['USER_EMAIL'])
        assert not errors, errors
        browser.close()
        ns['STATE']['server'].shutdown()
        print('Nova aba, cinco tamanhos, upload, fila, conversão FLAC e modo incorporado aprovados.')


if __name__ == '__main__':
    run()
