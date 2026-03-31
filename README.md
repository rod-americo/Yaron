# Yarion

Aplicativo web de acompanhamento semanal com frontend em JavaScript puro e backend Python sem framework, com persistência local em SQLite3.

## Nome do projeto

**Yarion** vem de **Yara** (minha filha) + **ion** (movimento): a ideia de evolução contínua, semana após semana.

## Funcionalidades

- Autosave em `data/tracker.db`.
- Atualização automática dos dados a cada 30 segundos no painel e no relatório.
- Resumo semanal em cards (2 colunas no desktop).
- Card extra de **Consistência** em tempo real.
- Relatório semanal com exportação para PDF.
- Múltiplas entradas por atividade no mesmo dia e na mesma semana.
- PWA com manifest e ícones.
- API simples para leitura e escrita do estado (`/api/state`).
- Migração automática e não destrutiva de `data/tracker.json` para SQLite no primeiro boot.

## Regras de exibição atuais

- Decimal com vírgula (`56,5`).
- Percentual sem casas (`98%`).
- `Academia` sem casas decimais.
- Formato razão sem espaço (`4/4 sessão`).
- Mobile: seletor de semana em `DD/MM/AAAA` com input nativo por trás.
- Relatório: `Semana | seletor | Voltar` na primeira linha e `Exportar PDF` abaixo.

## Stack

- Python 3 (HTTP nativo)
- SQLite3
- HTML + CSS + JavaScript (vanilla)
- Persistência em banco SQLite local

## Como executar

### 1) Iniciar servidor

```bash
python3 app.py
```

Na primeira execução, se existir `data/tracker.json`, o app importa os dados para `data/tracker.db` sem apagar o arquivo legado.

### 2) Acessar

- Local: `http://localhost:3080`
- Rede local: `http://<ip-da-maquina>:3080`

## Estrutura do projeto

```text
.
├── .skills/
│   └── yarion-maintenance/
│       └── SKILL.md
├── app.py
├── data/
│   ├── tracker.db                # ignorado no Git
│   ├── tracker.example.json
│   └── tracker.json              # legado/local, ignorado no Git
├── public/
│   ├── icons/
│   ├── app.js
│   ├── index.html
│   ├── report.js
│   ├── report.html
│   ├── site.webmanifest
│   └── styles.css
├── server.js                     # legado da versão Node.js
├── LICENSE
└── README.md
```

## API

### `GET /api/state`

Retorna o estado completo do acompanhamento.

### `POST /api/state`

Salva o estado completo enviado no body (JSON) no banco SQLite.

Validação mínima:

- body deve ser objeto
- deve conter `activities` e `weeks`

## Migração e dados

- `data/tracker.db`: base SQLite usada pelo app (não versionada).
- `data/tracker.json`: fonte legada local importada automaticamente quando o banco está vazio.
- `data/tracker.example.json`: exemplo limpo versionado no repositório.
- `server.js`: referência legada da implementação anterior em Node.js, mantida fora do fluxo principal atual.

## Licença

Este projeto está licenciado sob a Licença MIT. Consulte o arquivo [LICENSE](./LICENSE) para mais detalhes.
