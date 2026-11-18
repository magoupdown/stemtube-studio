"""Fluxo local da nova aba. Requer Playwright, Chromium e as dependências de test_backend.py."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
os.environ['STEMTUBE_MOCK'] = '1'


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
        errors, downloads = [], []
        def invoke(name, args):
            if name == 'colab_download':
                downloads.append(Path(ns['_output_path'](args[0])))
                data = {'ok': True}
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
        launch.click()
        assert len(context.pages) == 2
        app.set_viewport_size({'width':360,'height':780})
        wav = Path(tmp) / 'ensaio.wav'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=2', str(wav)], check=True)
        app.locator('[data-src=file]').click()
        app.locator('#fileInput').set_input_files(wav)
        app.locator('#toOptionsBtn').click()
        fit(app)
        app.locator('#startBtn').click()
        fit(app)
        expect(app.locator('#mixBtn')).to_be_visible(timeout=60000)
        fit(app)
        expect(app.locator('#mxState')).to_have_text('pronto', timeout=30000)
        app.locator('#mxPlay').click()
        expect(app.locator('#mxState')).to_have_text('tocando')
        app.locator('#mxPlay').click()
        app.locator('[data-solo="1"]').click()
        app.locator('#zipBtn').click()
        expect(app.get_by_text('Download enviado ao navegador.')).to_be_visible()
        assert downloads and downloads[-1].suffix == '.zip'
        app.locator('#mixFormat').select_option('flac')
        app.locator('#mixBtn').click()
        expect(app.locator('#backStemsBtn')).to_be_visible(timeout=60000)
        fit(app)
        expect(app.locator('.preview-play')).to_be_enabled(timeout=30000)
        app.locator('#stemList [data-dl]').first.click()
        expect(app.locator('.toast').filter(has_text='Download enviado ao navegador.').last).to_be_visible()
        assert downloads[-1].suffix == '.flac'
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
        print('Nova aba, cinco tamanhos, upload, fila, ZIP, mixagem FLAC e modo incorporado aprovados.')


if __name__ == '__main__':
    run()
