# Minha Frota — API Python

API REST local, sem dependências externas, usando SQLite. Os dados ficam em `%LOCALAPPDATA%\MinhaFrota\minha_frota.sqlite3`, fora do código. Ao iniciar, abre automaticamente a página local no navegador.

## Executar

```powershell
& "$env:USERPROFILE\Desktop\veiculo\Iniciar-MinhaFrota.ps1"
```

Escuta somente em `http://127.0.0.1:3001`.

A página inicial (`/`) permite consultar os indicadores, atualizar os veículos e cadastrar um veículo de teste. A API permanece local e não envia dados a serviços externos.

## Rotas

- `GET /api/health`
- `GET, POST /api/vehicles`
- `GET, PUT, DELETE /api/vehicles/{id}` — exclusão exige `?confirm=true`
- `GET /api/dashboard`
- `GET, POST /api/records`
- `GET /api/reports/costs`

O primeiro início cria três veículos de demonstração: Toyota Corolla 2022, Honda Civic 2020 e Honda CG 160 2023. Eles podem ser editados ou excluídos pela API.

## Testes

```powershell
python -m unittest -v test_api.py
```
