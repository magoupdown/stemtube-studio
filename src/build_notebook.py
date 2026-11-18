"""Monta o notebook StemTube.ipynb a partir dos arquivos de src/.

    python src/build_notebook.py [pasta_de_saida]

Células geradas:
  0. intro.md        → cabeçalho (markdown)
  1. setup_cell.py   → login Google, Drive, GPU e dependências (form)
  2. backend.py + app.html → o aplicativo (form)
  3. cleanup_cell.py → limpeza opcional (form)
  4. outro.md        → sobre, solução de problemas e limites (markdown)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)
os.makedirs(OUT_DIR, exist_ok=True)

def read(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return f.read()

backend = read('backend.py')
app_html = read('app.html')
assert '"""' not in app_html, 'app.html não pode conter aspas triplas'

APP_PY_HEAD = r'''#@title 2️⃣ Abrir o aplicativo  { display-mode: "form" }
#@markdown Execute esta célula e clique em **Abrir StemTube Studio em nova aba**. Se o ambiente for reiniciado, rode a célula 1 e depois esta.
abrir_em_nova_aba = True  #@param {type:"boolean"}
#@markdown Se o navegador bloquear a nova aba, desmarque a opção para usar a interface nesta célula.
import json as _json
from IPython.display import HTML as _HTML, display as _display

def _erro(msg):
    _display(_HTML(f'<div style="font-family:system-ui,sans-serif;padding:14px 16px;border-radius:12px;border-left:4px solid #ef4444;'
                   f'background:#ef444414;font-size:14px">⛔ <b>{msg}</b></div>'))

_pronto = True
if not globals().get('_STEMTUBE_SETUP_READY'):
    _erro('Execute primeiro a célula 1️⃣ (login na conta Google).'); _pronto = False
else:
    try:
        import google.auth as _ga; _ga.default()
    except Exception:
        _erro('Login na conta Google necessário. Rode a célula 1️⃣ novamente.'); _pronto = False
    try:
        import yt_dlp as _ytdlp
    except Exception:
        _erro('O yt-dlp não está instalado. Rode a célula 1️⃣ novamente e aguarde a instalação terminar.'); _pronto = False

if _pronto:
'''

APP_PY_TAIL = r'''
if _pronto:
    try:
        if abrir_em_nova_aba:
            _page = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                     '<meta name="viewport" content="width=device-width, initial-scale=1">'
                     '<title>StemTube Studio</title></head><body class="studio-window">' + APP_HTML + '</body></html>')
            # A página contém scripts próprios. Escape "<" antes de inseri-la no script lançador.
            _literal = _json.dumps(_page, ensure_ascii=True).replace('<', r'\u003c')
            _display(_HTML(LAUNCHER.replace('__STUDIO_DOCUMENT__', _literal)))
        else:
            _display(_HTML(APP_HTML))
    except Exception as _e:
        import traceback as _tb
        _erro('Falha ao abrir o aplicativo. Copie a mensagem abaixo e envie para suporte.')
        print(_tb.format_exc())
'''

def indent(code, n=4):
    return '\n'.join((' ' * n + l) if l.strip() else l for l in code.splitlines())

app_cell = (APP_PY_HEAD + '    try:\n' + indent(backend, 8) + '\n\n' + indent('APP_HTML = r"""' + app_html + '"""', 8)
            + '\n    except Exception as _e:\n        import traceback as _tb\n        _pronto = False\n'
            + '        _erro(\'Erro ao preparar o aplicativo. Copie a mensagem abaixo e envie para suporte.\')\n'
            + '        print(_tb.format_exc())\n' + 'LAUNCHER = ' + repr(read('launcher.html')) + '\n' + APP_PY_TAIL)

def cell(kind, src, **meta):
    c = {'cell_type': kind, 'metadata': meta, 'source': src.splitlines(keepends=True)}
    if kind == 'code':
        c.update({'execution_count': None, 'outputs': []})
    return c

nb = {
    'nbformat': 4, 'nbformat_minor': 0,
    'metadata': {
        'colab': {'name': 'StemTube.ipynb', 'provenance': [], 'toc_visible': True, 'gpuType': 'T4'},
        'accelerator': 'GPU',
        'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
        'language_info': {'name': 'python'},
    },
    'cells': [
        cell('markdown', read('intro.md'), id='intro'),
        cell('code', read('setup_cell.py'), id='setup', cellView='form'),
        cell('code', app_cell, id='app', cellView='form'),
        cell('code', read('cleanup_cell.py'), id='clean', cellView='form'),
        cell('markdown', read('outro.md'), id='about'),
    ],
}
for c in nb['cells']:
    if c['cell_type'] == 'code':
        compile(''.join(c['source']), c['metadata']['id'], 'exec')

out = os.path.join(OUT_DIR, 'StemTube.ipynb')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('notebook gerado:', out, f'({os.path.getsize(out)//1024} KB)')
