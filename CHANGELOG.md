## Player de prévias para todos os resultados

- Novo player com reprodução, pausa, busca, volume e velocidade para áudio e vídeo.
- Prévias individuais para downloads, recortes, faixas separadas e mixagens.
- Prévia de vídeo completa H.264/AAC até 480p, sem alterar o arquivo de download.
- Recuperação de erros do proxy com transferência em blocos de 512 KiB e nova tentativa.
- Carregamento sob demanda e liberação da mídia ao sair do resultado.
- 87 verificações do backend aprovadas, incluindo geração real de prévia de vídeo e integridade dos blocos. Outros 15 testes temporários da lógica do player passaram com DOM simulado. Validação visual e execução no Colab permanecem pendentes: o navegador deste ambiente bloqueou a página local e o teste incorporado por política de URL.

## Revisão técnica de 2026-09-08

- Erros de conversão deixam de ser tratados como downloads concluídos.
- Recorte de áudio converte apenas o trecho no formato escolhido. O formato original mantém cópia por pacotes, com aviso de precisão limitada.
- Recortes respeitam a opção de metadados e selecionam explicitamente os fluxos de áudio/vídeo.
- Cópias no Drive preservam arquivos homônimos e mantêm resultados locais acessíveis em caso de falha de salvamento.
- Seleções de vídeos são deduplicadas e links divergentes dos identificadores são recusados.
- Pastas especiais e durações não finitas são tratadas.
- 75 verificações locais aprovadas; notebook regenerado com fontes sincronizadas.

# Changelog

Todas as mudanças relevantes do StemTube Studio ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] — 2026-09-07

Primeira versão. Reúne o **StemLab 2.0 RC1** (separação de faixas com IA e mixer) e o **YT Downloader Pessoal** (vídeos, playlists e áudio do YouTube) em um único aplicativo, sem duplicar nada.

### Adicionado
- **Um só assistente em 5 etapas** (Fonte → Prévia → Opções → Processar → Resultado) para as três ações: baixar vídeo em MP4, baixar só o áudio e separar faixas com IA.
- **Fila com duas pistas**: downloads e processamento na GPU rodam em paralelo, cada um com sua própria fila; a barra de tarefas mostra tudo em qualquer etapa.
- **Separar faixas desta música** direto do resultado de um download de vídeo único, e **Separar de outro jeito** a partir das faixas prontas.
- **Prévia da mixagem** renderizada (player embutido no resultado).
- **Migração automática de cookies** salvos pelas versões anteriores (`Meu Drive/StemLab` e `Meu Drive/YT_Downloader`) para `Meu Drive/StemTube`.
- Opção `instalar_separador_ia` na célula 1 para preparar só os downloads (mais rápido, sem GPU).
- Testes locais do backend (`src/tests/test_backend.py`, 59 verificações) e servidor de desenvolvimento em modo simulado.

### Herdado do YT Downloader Pessoal
- Vídeo em MP4 em qualquer resolução disponível (144p a 8K), com fps, HDR e tamanho estimado.
- Áudio em MP3, M4A/AAC, OPUS, FLAC, WAV ou original, com escolha de qualidade e capa/metadados embutidos.
- Vídeo único, playlist ou canal, com seleção item a item, filtro por título e detecção de Mixes automáticos.
- Recorte por tempo com corte exato (vídeo recodificado em H.264, áudio copiado sem perda).
- Nova tentativa apenas dos itens que falharam; ZIP de tudo; subpasta no Drive.

### Herdado do StemLab
- Separação em 2 (BS-Roformer), 4 (htdemucs_ft) ou 6 faixas (htdemucs_6s), na GPU quando disponível, com pré-download do modelo de voz em segundo plano.
- Arquivo local de até 1 GB (áudio ou vídeo) como fonte.
- Mixer no navegador com mudo, solo, volume e comparação com o original; renderização da mixagem em WAV, FLAC ou MP3 com limitador.
- Validações de segurança: caminhos reais dentro da pasta de saída, servidor de prévias com HTTP Range, cookies em formato Netscape validados e com permissão 0600, limites de upload e de duração, cancelamento com encerramento de processos.

### Alterado
- Identidade visual nova (coral → violeta → ciano), tema claro/escuro, layout responsivo e assinatura *Desenvolvido por @emersonms - 2026*.
- Pasta temporária única: `/content/stemtube`; pasta no Drive: `Meu Drive/StemTube/{Downloads,Faixas,Mixagens}`.
- Verificação de certificados HTTPS mantida ativa no yt-dlp (o YT Downloader a desativava).
