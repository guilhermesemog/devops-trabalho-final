# Task Manager API

API REST para criar, listar, consultar, atualizar e excluir tarefas. O projeto usa FastAPI, SQLAlchemy 2, PostgreSQL, Alembic e Pytest. As Etapas 1–3 cobrem o backend, a execução containerizada local e CI com publicação de imagens.

## Requisitos

- Python 3.10 ou superior
- PostgreSQL acessível pela máquina que executa a API
- Docker Engine e Docker Compose plugin para a execução containerizada

## Configuração local

Na raiz do repositório, crie e ative o ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Configure `DATABASE_URL` com a URL do banco PostgreSQL. O formato esperado é:

```text
postgresql+psycopg://<usuario>:<senha>@<host>:<porta>/<banco>
```

Substitua os valores entre `<...>` pelos dados do seu banco. Não salve credenciais no repositório.

## Migrações e execução

Com o ambiente virtual ativo e `DATABASE_URL` configurada:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

A documentação interativa do FastAPI ficará disponível em `http://127.0.0.1:8000/docs`.

## Execução com Docker Compose

O Compose inicia a API e o PostgreSQL. O banco usa um volume nomeado persistente e pode ser acessado pela API através do DNS interno `db`. O arquivo `.env.example` contém apenas credenciais locais de exemplo; copie-o para `.env` e altere a senha antes de usar:

```bash
cp .env.example .env
```

As portas publicadas por padrão são `5433` para PostgreSQL e `8000` para a API. A API fica limitada a `127.0.0.1`; o PostgreSQL também é publicado no gateway Docker para acesso do K3d, conforme a seção abaixo. Se alguma porta estiver ocupada, defina `POSTGRES_PORT` ou `API_PORT` em `.env` para uma porta livre.

Construa a imagem e inicie o banco:

```bash
docker compose build api
docker compose up -d db
```

As migrações são explícitas e devem ser aplicadas antes de iniciar a API:

```bash
docker compose run --rm api alembic upgrade head
docker compose up -d api
docker compose ps
curl http://127.0.0.1:8000/health
```

A imagem `task-manager-api:local` não contém dependências de teste e executa Uvicorn como usuário não-root. O health check da API consulta o PostgreSQL; o banco também tem seu próprio health check, usado como condição de inicialização da API.
Se configurar `API_PORT` com outro valor, use essa porta nos comandos `curl`.

Para validar a persistência, crie uma tarefa, recrie os containers do projeto e consulte a tarefa novamente:

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"title":"Persistent task"}'

docker compose down
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl http://127.0.0.1:8000/tasks
```

`docker compose down` mantém o volume nomeado. Não use `docker compose down -v` se quiser preservar os dados. Para parar os serviços sem remover o volume:

```bash
docker compose down
```

## Testes

Defina `TEST_DATABASE_URL` para um banco PostgreSQL isolado. A suíte aplica as migrações nesse banco e executa cada teste dentro de uma transação que é revertida ao final.

```bash
export TEST_DATABASE_URL='postgresql+psycopg://<usuario>:<senha>@<host>:<porta>/<banco_de_teste>'
pytest
```

Use um banco dedicado aos testes. As migrações são persistidas no banco configurado, embora os dados criados por cada teste sejam revertidos.

Para criar um banco de teste separado no PostgreSQL do Compose, com a configuração de exemplo:

```bash
docker compose exec db createdb -U task_manager -O task_manager task_manager_test
export TEST_DATABASE_URL='postgresql+psycopg://task_manager:<senha-do-.env>@127.0.0.1:5433/task_manager_test'
.venv/bin/pytest
```

Substitua o placeholder pela senha local e ajuste a porta caso `POSTGRES_PORT` tenha sido alterada. Não use o banco de produção da aplicação como banco de testes.

## CI e publicação no GHCR

O workflow `.github/workflows/ci-cd.yml` executa em runners hospedados pelo GitHub:

- Pull requests direcionados à `main` executam os testes com PostgreSQL 17 e não publicam imagens.
- Pushes para `main` executam os testes e, somente após aprovação, constroem a imagem com o Dockerfile do projeto e a publicam no GitHub Container Registry.

A imagem é identificada pelo SHA completo do commit, por exemplo `ghcr.io/guilhermesemog/devops-trabalho-final:<sha>`. O workflow usa `GITHUB_TOKEN` com permissões mínimas de leitura do repositório e publicação de pacotes; não requer PAT nem segredos de registry configurados manualmente. Atualmente o pacote GHCR está público, portanto o pull da imagem não requer autenticação.

## Kubernetes local com K3d

O cluster local executa a imagem publicada no GHCR e reutiliza o PostgreSQL do Compose. A imagem usada pelos manifests está fixada no SHA completo `47500425f393c2679f6282cac8be30e8ce953ef5`. O pacote está público, então não é necessário criar `imagePullSecret`.

Instale K3d `v5.9.0` e kubectl `v1.35.5`, e confirme que os comandos `k3d` e `kubectl` estão no `PATH`. O arquivo `kubernetes/k3d-config.yaml` cria um cluster de nó único na porta API `6443` e configura o alias `postgres.k3d.internal`.

O banco continua publicado em loopback e, adicionalmente, no gateway da bridge Docker, por padrão `172.17.0.1`. Se o gateway da sua bridge for diferente, defina `DOCKER_BRIDGE_GATEWAY` em `.env` e ajuste o IP correspondente em `kubernetes/k3d-config.yaml`. Configure `.env` conforme a seção do Compose e inicie apenas o banco:

```bash
docker compose up -d db
k3d cluster create --config kubernetes/k3d-config.yaml
kubectl apply -f kubernetes/namespace.yaml
```

Crie localmente o arquivo ignorado `.env.k8s` com apenas a URL de conexão que os Pods usarão (não a URL interna `db:5432` do Compose):

```text
DATABASE_URL=postgresql+psycopg://<usuario>:<senha>@postgres.k3d.internal:<POSTGRES_PORT>/task_manager
```

URL-encode caracteres reservados nos campos de usuário e senha.
Restrinja as permissões do arquivo e crie o Secret diretamente no cluster. Não versione `.env.k8s` nem um Secret renderizado:

```bash
chmod 600 .env.k8s
kubectl create secret generic task-manager-db \
  --namespace task-manager \
  --from-env-file=.env.k8s
```

Execute as migrações explicitamente antes de iniciar a API:

```bash
kubectl apply -f kubernetes/migration-job.yaml
kubectl wait --for=condition=complete job/task-manager-migration \
  --namespace task-manager --timeout=180s
kubectl logs job/task-manager-migration --namespace task-manager
kubectl apply -f kubernetes/deployment.yaml
kubectl apply -f kubernetes/service.yaml
kubectl wait --for=condition=available deployment/task-manager-api \
  --namespace task-manager --timeout=180s
```

Em outro terminal, encaminhe a porta local `8080` (ou uma porta livre) ao Service `ClusterIP`:

```bash
kubectl port-forward --namespace task-manager service/task-manager-api 8080:8000
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/tasks
```

Para remover o cluster sem afetar o volume PostgreSQL:

```bash
k3d cluster delete task-manager
```

## Nomad local

Etapa 5 usa Nomad `2.1.1` no Linux amd64. Baixe o binário e a lista de checksums da [fonte oficial](https://releases.hashicorp.com/nomad/2.1.1/) e valide o checksum antes de instalar em `~/.local/bin`:

```bash
set -euo pipefail
mkdir -p "$HOME/.local/bin"
tmpdir=$(mktemp -d)
trap 'rm -f "$tmpdir/nomad_2.1.1_linux_amd64.zip" "$tmpdir/nomad_2.1.1_SHA256SUMS" "$tmpdir/nomad"; rmdir "$tmpdir" 2>/dev/null || true' EXIT
curl -fsSLo "$tmpdir/nomad_2.1.1_linux_amd64.zip" \
  https://releases.hashicorp.com/nomad/2.1.1/nomad_2.1.1_linux_amd64.zip
curl -fsSLo "$tmpdir/nomad_2.1.1_SHA256SUMS" \
  https://releases.hashicorp.com/nomad/2.1.1/nomad_2.1.1_SHA256SUMS
(cd "$tmpdir" && grep -F 'nomad_2.1.1_linux_amd64.zip' nomad_2.1.1_SHA256SUMS | sha256sum --check -)
python3 - "$tmpdir/nomad_2.1.1_linux_amd64.zip" "$tmpdir" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    archive.extract("nomad", sys.argv[2])
PY
install -m 0755 "$tmpdir/nomad" "$HOME/.local/bin/nomad"
export PATH="$HOME/.local/bin:$PATH"
```

Nos terminais adicionais usados para deploy, adicione o diretório do Nomad ao `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Inicie um agente temporário single-node em modo desenvolvimento. No Linux, execute o cliente Nomad como root para que suporte cgroups; o agente e sua API/UI ficam limitados a loopback. Este modo não usa ACLs e não é apropriado para produção:

```bash
sudo -A "$HOME/.local/bin/nomad" agent -dev -bind=127.0.0.1
```

Em outro terminal, crie `nomad/local.auto.hcl` localmente com a URL do PostgreSQL no gateway Docker. O arquivo é ignorado pelo Git; restrinja suas permissões e não o versione. URL-encode caracteres reservados na senha:

```hcl
database_url = "postgresql+psycopg://<usuario>:<senha>@172.17.0.1:5433/task_manager"
```

```bash
chmod 600 nomad/local.auto.hcl
```

O GHCR está público, então não é necessária credencial de pull. O valor da URL é enviado ao agente local junto com a especificação do job; modo dev não oferece armazenamento de segredos protegido por ACL. Use somente para este ambiente local.

Valide e execute primeiro o Job batch de migração, depois o serviço da API:

```bash
nomad job validate -var-file=nomad/local.auto.hcl nomad/task-manager-migration.nomad
nomad job run -var-file=nomad/local.auto.hcl nomad/task-manager-migration.nomad
nomad job status task-manager-migration

nomad job validate -var-file=nomad/local.auto.hcl nomad/task-manager-api.nomad
nomad job run -var-file=nomad/local.auto.hcl nomad/task-manager-api.nomad
nomad job status task-manager-api
```

Consulte a alocação para encontrar a porta dinâmica, que deve estar vinculada somente a `127.0.0.1`:

```bash
nomad job allocs task-manager-api
nomad alloc status <allocation-id>
curl http://127.0.0.1:<porta>/health
curl http://127.0.0.1:<porta>/tasks
```

O service check HTTP consulta `/health`; falhas temporárias do banco marcam o serviço como não saudável sem reiniciar o processo. Uma falha do processo é tratada pela política de restart do job.

Para encerrar, pare o job da API e interrompa o agente dev com `Ctrl+C` no terminal em que foi iniciado. Isso encerra o ambiente Nomad temporário, mas preserva o volume PostgreSQL do Compose:

```bash
nomad job stop task-manager-api
```

## Endpoints

| Método | Endpoint | Comportamento |
| --- | --- | --- |
| GET | `/health` | Retorna `{"status":"ok"}` quando o PostgreSQL responde |
| POST | `/tasks` | Cria uma tarefa e retorna HTTP 201 |
| GET | `/tasks` | Lista tarefas em ordem de ID |
| GET | `/tasks/{id}` | Consulta uma tarefa; retorna 404 se não existir |
| PUT | `/tasks/{id}` | Substitui os campos mutáveis; retorna 404 se não existir |
| DELETE | `/tasks/{id}` | Exclui uma tarefa e retorna HTTP 204; retorna 404 se não existir |

O corpo de criação requer `title`; `description` é opcional e `completed` assume `false` por padrão. O PUT requer `title` e `completed`; `description` pode ser omitida ou nula e, nesses casos, será definida como nula. Títulos vazios ou compostos apenas por espaços são rejeitados.

O health check executa uma consulta simples ao PostgreSQL e é adequado para verificar prontidão. Uma futura probe de liveness deve verificar o processo sem reiniciá-lo por indisponibilidade temporária do banco.

Cada tarefa possui `id`, `title`, `description`, `completed` e `created_at`. O timestamp é gerado pelo PostgreSQL.

## Estrutura

- `app/`: configuração, conexão, modelos, schemas, serviços e rotas.
- `migrations/`: configuração e revisões Alembic.
- `tests/`: testes de health check e CRUD com PostgreSQL.
- `kubernetes/`: configuração do K3d e manifests Kubernetes.
- `nomad/`: Jobs HCL de migração e API; variáveis locais não são versionadas.

Configuração do self-hosted runner e CI/CD integrado pertencem à etapa seguinte. Kubernetes e Nomad usam a mesma imagem da API; o PostgreSQL permanece independente deles.
