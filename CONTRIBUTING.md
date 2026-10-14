# Contribuindo com o DS4Linux

Obrigado por querer contribuir. Este documento descreve o fluxo completo, do
ambiente local até a revisão do pull request.

## 1. Ambiente de desenvolvimento

Requisitos: Python **3.10 ou superior** (a CI usa 3.12), `pip` e `venv`.

```bash
git clone https://github.com/FrancosCorporation/ds4linux.git
cd ds4linux
python3 -m venv venv
venv/bin/python -m pip install -r requirements-ci.txt
```

`requirements-ci.txt` é a matriz travada usada pela CI e é a mesma referência
de versões usada nos testes locais. O launcher do repositório (`ds4linux.sh`)
procura o interpretador em `venv/bin/python`, então a pasta `venv/` também é o
caminho esperado para executar o aplicativo a partir do código.

Para regenerar o lock depois de mudar `pyproject.toml`:

```bash
uv pip compile pyproject.toml --group dev --python-version 3.12 \
  --python-platform x86_64-unknown-linux-gnu -o requirements-ci.txt
```

## 2. Rodando a suíte e o lint

Antes de abrir um PR, os dois comandos abaixo precisam passar:

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -v
venv/bin/ruff check src tests
```

Também vale conferir a sintaxe dos scripts shell quando eles mudarem:

```bash
bash -n install.sh ds4linux.sh packaging/deb/build-deb.sh
```

Os testes rodam com `QT_QPA_PLATFORM=offscreen`, então funcionam em servidor
sem display. Eles cobrem tradução sintética evdev/HIDRAW, frames e recuperação
de eventos, perfis, ciclo de vida, GUI offscreen, instalação em diretório
temporário e recursos do wheel. **Não** substituem a validação física: leitura
e escrita reais de `/dev/input`, `uinput`, HIDRAW, LEDs, vibração, Steam Input
e jogos seguem pendentes de teste com controle real (ver `plan.md`,
unidades `HARDWARE-01`/`INPUT-01`).

## 3. Fluxo de contribuição

1. Crie uma branch a partir de `version_2.0` (branch de desenvolvimento ativa).
2. Faça commits pequenos e descritivos, no formato Conventional Commits já
   usado no repositório: `feat:`, `fix:`, `fix(security):`, `docs:`, `test:`,
   `ci:`, `chore:`.
3. **Acrescente teste de regressão** para cada contrato alterado. Correção sem
   teste que falhava antes e passa depois não é considerada completa.
4. Atualize a documentação afetada: `README.md` para mudanças visíveis ao
   usuário, `CHANGELOG.md` para mudanças relevantes à release, e
   `plan.md`/`resumo.md` quando o backlog ou o estado validado mudar.
5. Abra o pull request preenchindo o que mudou, por que mudou e como testar.

## 4. O que é revisado

- Suíte completa e Ruff verdes.
- Teste de regressão presente para o comportamento alterado.
- Nenhuma promessa nova no README que o código ainda não entrega.
- Sem credenciais ou senha persistida em disco (o projeto usa polkit).
- Permissões udev restritas: `0660` + `uaccess`, nunca `0666`.

## 5. Reportando problemas

Ao abrir uma issue, inclua:

- Distribuição e versão (`cat /etc/os-release`), versão do kernel e como o
  DS4Linux foi instalado (pacote, `install.sh` ou a partir do código).
- Se o controle está em USB ou Bluetooth e o output virtual escolhido
  (Xbox 360 ou PS4).
- Passos para reproduzir, esperado e obtido, com o traceback completo quando
  houver.
- Para problemas de jogo/menus: título do jogo, launcher/runtime
  (Steam/Proton/Wine/Heroic/Lutris) e perfil ativo.

Traços de Python são bem-vindos como estão — o relato original que motivou a
correção do `List`/`list` em `input_mapper.py` foi exemplo disso.

## 6. Licença

Ao contribuir, você concorda em licenciar a sua contribuição sob os termos da
[LICENSE](LICENSE) (MIT) do projeto.
