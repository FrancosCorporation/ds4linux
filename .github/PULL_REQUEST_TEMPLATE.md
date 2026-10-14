## O que este PR muda

<!-- 1-3 frases. Se corrigir um bug, cite o ID (ex.: INPUT-03) ou a issue. -->


## Por quê

<!-- Qual problema isso resolve. Sem isso o "o quê" é difícil de revisar. -->


## Como testar

<!-- Comandos e passos concretos. Alguém sem o teu hardware precisa conseguir validar. -->

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -v
venv/bin/ruff check src tests
```

## Checklist

- [ ] Teste de regressão adicionado (falhava antes / passa depois)
- [ ] `unittest` completo e `ruff check src tests` verdes
- [ ] `CHANGELOG.md` atualizado se o comportamento visível mudou
- [ ] `plan.md`/`resumo.md` atualizados se o backlog ou o estado validado mudou
- [ ] README não ganhou promessa de recurso que ainda não existe
- [ ] Nenhuma credencial/senha persistida em disco; udev segue `0660` + `uaccess`
- [ ] Prints regenerados (`python docs/generate_screenshots.py`) se a GUI mudou

## Hardware / validação

<!-- A suíte automatizada não substitui o teste físico. Marque o que foi verificado. -->

- [ ] Com controle físico (USB / Bluetooth)
- [ ] Em jogo ou aplicativo real
- [ ] Apenas testes sintéticos (sem hardware)
