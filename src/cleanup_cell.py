#@title 3️⃣ (Opcional) Limpar arquivos temporários com segurança { display-mode: "form" }
#@markdown Apaga downloads e arquivos temporários desta sessão do Colab. Não limpa durante tarefas ativas e preserva os cookies e as cópias no Drive.
confirmar_limpeza = False  #@param {type:"boolean"}
if not confirmar_limpeza:
    print('Limpeza desativada. Marque confirmar_limpeza e execute esta célula para apagar os temporários.')
elif 'cb_cleanup' not in globals():
    print('Execute a célula 2 antes de usar a limpeza.')
else:
    _cleanup_result = cb_cleanup().data
    if not _cleanup_result.get('ok'):
        print('⚠️ ' + _cleanup_result.get('error', 'Não foi possível limpar.'))
    else:
        print('✅ Arquivos temporários e histórico limpos. Execute a célula 2 para renovar a interface.')
