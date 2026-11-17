# OctorGit no Linux

Requisitos: Python 3.11 ou superior, Bash e um navegador. Não precisa de Node, Docker ou chave de IA para a análise estática.

Extraia o pacote Linux, abra o terminal na pasta `octorgit` e execute:

```bash
bash ABRIR_OCTORGIT.sh
```

O navegador abrirá em **http://127.0.0.1:8765**. Se ele não abrir automaticamente, acesse esse endereço manualmente. Mantenha o terminal aberto; use Ctrl+C para encerrar.

O script usa o código da própria pasta e aceita os mesmos argumentos do servidor:

```bash
bash ABRIR_OCTORGIT.sh --port 8766
bash ABRIR_OCTORGIT.sh --no-browser --data-dir ./meu-historico
```

Também é possível usar o script executável:

```bash
chmod +x ABRIR_OCTORGIT.sh
./ABRIR_OCTORGIT.sh
```

## Instalar em um ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m octorgit.web
```

Em distribuições Debian/Ubuntu, se o comando `venv` estiver indisponível, instale o pacote `python3-venv` pelo gerenciador da sua distribuição. A execução direta pelo script não exige criar um ambiente virtual.

## Histórico

Por padrão, o banco fica em `$XDG_DATA_HOME/octorgit/history.sqlite3`; quando `XDG_DATA_HOME` não estiver definido, usa `~/.local/share/octorgit/history.sqlite3`. A opção `--data-dir` tem precedência. O histórico contém resultados e trechos filtrados; não compartilhe essa pasta junto do código do programa.

## IA opcional

Abra **Configurações de IA** no menu e siga [CONFIGURAR_IA.md](CONFIGURAR_IA.md). A chave fica na memória da sessão; a análise estática funciona sem chave.

## Ver a parte visual sem iniciar o aplicativo

Abra `VER_EXEMPLO_VISUAL.html` no navegador. O relatório contém os diagramas e pode ser salvo em PDF com Ctrl+P. Para testar análise e comparação, use **Experimentar um exemplo** e depois **Comparar versões → Testar exemplo alterado**.
