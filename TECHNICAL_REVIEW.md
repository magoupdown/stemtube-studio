# Revisão técnica do StemTube Studio

## Revisão de 17 de novembro de 2026

Base examinada `355020a`. A revisão abrangeu preparação e limpeza da sessão, gerador e notebook distribuído, backend Python, interface, servidor de desenvolvimento e testes.

### Mudanças verificadas

| Área | Comportamento encontrado | Alteração |
|---|---|---|
| Abertura do Studio | A célula 2 inseria todo o HTML na saída. A aplicação dependia de funções JavaScript disponíveis no Colab. | A célula apresenta um botão. O clique abre uma aba de página inteira que encaminha chamadas para a célula original. Clicar novamente traz a aba existente à frente. A opção `abrir_em_nova_aba` permite usar o modo incorporado se o navegador bloquear pop-ups. |
| Layout e carregamento | A interface tinha largura máxima de 1140 px, altura mínima fixa e controles compactos. O carregamento da folha de fontes antes do aplicativo atrasava a montagem da nova página durante o teste. | O fundo ocupa a janela e a área de trabalho usa a altura disponível. A largura de leitura é limitada em monitores grandes. No celular, ações podem quebrar linha, os principais botões têm pelo menos 44 px de altura e os controles do mixer se reorganizam. As fontes externas são carregadas após a interface. |
| Inicialização | O e-mail já podia existir depois de uma falha de instalação. A célula 2 conferia esse valor e a importação do yt-dlp, inclusive após uma preparação parcial. | A célula 1 sinaliza o término apenas após as verificações de instalação. A célula 2 exige esse sinal. |
| Navegação na fila | Uma resposta atrasada de uma tarefa podia substituir o resultado selecionado em seguida. | A interface confere o identificador selecionado após receber a resposta. |
| ZIP | A compactação duplicava todas as faixas em uma pasta intermediária e escrevia diretamente sobre o ZIP anterior. | O arquivo é montado diretamente das faixas e só substitui o ZIP anterior após fechar com sucesso. Uma falha simulada confirmou a preservação do arquivo anterior. |
| Drive | A tela de download podia anunciar cópias salvas com base apenas na opção marcada. O resultado da separação também não distinguia cópia parcial de integral. | O resumo conta os arquivos que receberam caminho de destino. O teste da interface inclui uma tarefa concluída com zero cópias. |
| Recorte e prévias | Um início NaN podia virar zero antes da validação. O servidor de arquivos escutava em todas as interfaces. | A validação de finitude precede o ajuste do início. O servidor de prévias escuta na interface local da máquina do notebook. |

### Evidência local

- Python 3.12.14, yt-dlp 2026.10.26 e FFmpeg 7.1.5. As 90 verificações de `python src/tests/test_backend.py` passaram. Há arquivos de mídia reais nos testes de conversão, recorte, mixagem, prévias e ZIP. O teste substitui a obtenção de vídeos e a inferência neural.
- `python src/tests/test_window.py` executa o lançador da célula gerada em um iframe de outra origem com permissões de pop-up. O Chromium abre outra aba e verifica se ela alcança o backend pela ponte simulada. O teste cobre tamanhos de 320 × 568 a 1440 × 900, incluindo paisagem, e verifica os limites dos controles visíveis.
- O fluxo de navegador inclui envio de WAV, processamento simulado, reprodução no mixer, Solo, criação de ZIP, renderização em FLAC, prévia, seleção do resultado após reabertura e modo incorporado. O teste confere o arquivo solicitado ao acionar Baixar. A transferência nativa para a pasta Downloads depende do Colab real.
- O notebook foi regenerado e suas três células Python foram compiladas. Para repetir o teste de navegador, instale Playwright e Chromium. A variável opcional `CHROMIUM_PATH` seleciona o executável.

### Pontos que ainda merecem trabalho

| Prioridade | Evidência no código | Próxima verificação |
|---|---|---|
| Alta | O indicador de GPU consulta o PyTorch. A instalação pede `audio-separator[cpu]` e o teste local usa separação simulada. A presença de uma T4, isoladamente, não identifica o provedor utilizado por cada modelo. | Em uma T4 real, registrar o provedor do modelo e o tempo de uma faixa curta nos modos de 2, 4 e 6 faixas. Usar os resultados para escolher os pacotes e exibir o dispositivo efetivamente utilizado. |
| Alta | O login, os cookies, o proxy de mídia e a transferência nativa de arquivos dependem do navegador e da sessão Google. O teste automatizado substitui essa comunicação. | Em uma sessão nova, abrir pelo botão no Chrome Android e no Safari iOS, baixar um vídeo autorizado, exportar o áudio e conferir uma cópia no Drive. Manter a aba do notebook aberta. |
| Média | A preparação atualiza pacotes a cada sessão. Um upload interrompido antes da confirmação deixa um registro e um arquivo parcial até a limpeza. | Registrar versões após o teste integrado e validar atualizações em separado. Adicionar descarte de uploads abandonados com prazo e proteção para envios ativos. |
| Média | Cada download gera sua prévia completa antes de disponibilizar o resultado. O mixer usa players independentes com correção de desvio a partir de 120 ms. | Medir tempo e espaço com vídeos longos antes de adotar prévia sob demanda. Para edição musical de precisão, avaliar reprodução por relógio compartilhado. O áudio exportado já é mixado pelo FFmpeg. |

A nova aba precisa da sessão do notebook. É possível fechá-la e reabrir o Studio pelo mesmo botão enquanto a sessão estiver ativa. A interface evita depender de `serve_kernel_port_as_window`, marcada como obsoleta pelo próprio projeto Colab. [Implementação do Google Colab](https://github.com/googlecolab/colabtools/blob/main/google/colab/output/_util.py).

## Revisão de setembro de 2026

Data: 2026-09-08. Base examinada: `9008021`.

## Correções

| Problema no código | Consequência | Correção aplicada |
|---|---|---|
| `ignoreerrors=True` no processamento do download | Uma conversão fracassada podia deixar um arquivo intermediário tratado como resultado | Erros de processamento interrompem o item e ficam disponíveis para nova tentativa |
| Recorte de áudio com `-c copy` anunciado como exato | Limites do trecho dependiam dos pacotes do codec | Recodificação apenas do trecho em MP3, M4A, OPUS, WAV e FLAC; formato original mantém cópia com aviso explícito |
| Conversão completa antes do recorte | Trabalho desnecessário e conversão adicional ao implementar corte preciso | Download do áudio de origem, seguido de uma conversão do trecho |
| `-map 0` e metadados sempre presentes no recorte | Inclusão de fluxos indesejados e desrespeito à opção de metadados | Mapeamento explícito e metadados condicionais |
| Cópia no Drive sobrescrevia nomes existentes | Resultado anterior podia ser perdido | Reserva exclusiva de nome e sufixos numéricos |
| Falha no Drive propagava exceção para processamento | Download/separação podia falhar; mixagem podia apagar o resultado local | Aviso de falha de cópia, remoção de cópia incompleta e preservação do resultado local |
| Identificador e URL eram validados separadamente | Link de outro vídeo podia passar com identificador divergente | Verificação de correspondência e URL canônica |
| Vídeos repetidos na mesma tarefa | Resultados duplicados apontando para o mesmo arquivo | Deduplicação por identificador, preservando a ordem |
| Pasta `..` e duração NaN | Destino inesperado e validação numérica incompleta | Neutralização de pasta especial, contenção de destino no Drive e duração positiva finita |

## Evidências de validação

`python src/tests/test_backend.py`: **75 verificações aprovadas**.

- Upload em blocos e rejeição de entradas inválidas.
- Separação simulada de quatro faixas com FFmpeg e prévias reais.
- Renderização FLAC de duas faixas selecionadas, com ganho diferente.
- Recortes reais em WAV, MP3, M4A, OPUS, FLAC e original. WAV de 1,5 segundo verificado com tolerância inferior a uma amostra em 44,1 kHz; demais contêineres com tolerância de 100 ms.
- Simulação de falha de conversão e de falta de espaço no Drive.
- Preservação de arquivos homônimos no destino de teste.
- ZIP, HTTP Range, bloqueio de travessia, cancelamento e limpeza.

Ambiente local: FFmpeg 6.1.1, yt-dlp 2026.08.19. A validação do Drive usa diretório temporário e falha simulada, sem acesso ao Drive pessoal.

O gerador recompilou todas as células Python e produziu novamente `StemTube.ipynb`. O JavaScript passou em `node --check`. `git diff --check` não apontou problemas de whitespace.

## Limites da revisão

Os testes não executaram autenticação Google, montagem real do Drive, downloads do YouTube, modelos de IA ou GPU T4 no Colab. A separação simulada testa o fluxo de arquivos, sem avaliar a qualidade da separação neural. A verificação JavaScript é sintática, sem validação visual ou de sincronismo do mixer em navegador.

A instalação ainda resolve dependências atualizadas em cada sessão, portanto versões futuras podem introduzir incompatibilidades. O mixer usa elementos de áudio independentes e correção periódica de posição; isso não constitui sincronização com precisão de amostra. A opção de áudio original preserva os pacotes, portanto não oferece a mesma precisão de corte da recodificação. Falhas de pós-processamento, inclusive capa, agora tornam o item falho em vez de apresentar um resultado possivelmente incompleto como sucesso.

Não se afirma ausência absoluta de erros nem validação integral no Colab. Para carregar o código atualizado, abrir novamente o link original e iniciar uma sessão nova, executando as células 1 e 2.

## Referências técnicas

- [FFmpeg: opções de busca temporal e cópia de fluxos](https://ffmpeg.org/ffmpeg.html).
- [yt-dlp: opções de tratamento de erros e pós-processamento](https://github.com/yt-dlp/yt-dlp).
