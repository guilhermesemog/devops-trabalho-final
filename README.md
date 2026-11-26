# Task Manager API

API REST para criar, listar, consultar, atualizar e excluir tarefas. O projeto usa FastAPI, SQLAlchemy 2, PostgreSQL, Alembic e Pytest. As Etapas 1–6 cobrem o backend, a execução containerizada, CI/CD e deploy local no Kubernetes e Nomad.

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

## CI/CD e publicação no GHCR

O workflow `.github/workflows/ci-cd.yml` executa testes e build em runners hospedados pelo GitHub. Pull requests direcionados à `main` executam os testes com PostgreSQL 17 e não publicam imagens nem usam recursos locais. Um push para `main` executa testes, publica a imagem no GHCR e, após sucesso, aciona automaticamente uma migração e os deploys no K3d e no Nomad.

A imagem é identificada pelo SHA completo do commit, por exemplo `ghcr.io/guilhermesemog/devops-trabalho-final:<sha>`; não há uso de `latest`. Uma migração Kubernetes por execução precede os dois deploys. Os Jobs de deploy usam um runner self-hosted `deploy` dedicado a este repositório. Eles só podem executar para push em `main`; nunca configure o runner local para jobs de pull request. O runner precisa executar como o mesmo usuário que possui o kubeconfig K3d e os arquivos locais do Nomad. O workflow usa Nomad para workloads e não invoca o socket Docker diretamente.

Configure o runner em **Settings → Actions → Runners** no repositório e use o label adicional `deploy`, além dos labels padrão Linux/x64. Baixe-o conforme as instruções mostradas pelo GitHub para Linux x64 e extraia-o fora do checkout. Para evitar colocar o token de registro no histórico do shell, leia-o interativamente:

```bash
read -rs -p 'Runner registration token: ' RUNNER_TOKEN
printf '\n'
./config.sh --url https://github.com/guilhermesemog/devops-trabalho-final \
  --token "$RUNNER_TOKEN" --labels deploy
unset RUNNER_TOKEN
sudo -A ./svc.sh install "$USER"
sudo -A ./svc.sh start
```

O token é temporário: obtenha-o diretamente no GitHub no momento da configuração e não o cole em chats, workflow, logs ou arquivos versionados. Instale o runner como serviço para que fique disponível aos workflows.

Antes de habilitar o deploy, deixe o cluster K3d ativo e configure o Nomad persistente conforme a seção abaixo. O runner usa `~/.config/nomad/task-manager.auto.hcl` e `~/.config/nomad/ci-deploy.token`; ambos devem pertencer ao usuário do runner, ficar fora do checkout e ter permissões restritas. Não são necessários GitHub Actions secrets para essas credenciais. O pacote GHCR está público e não requer credencial de pull.

## Kubernetes local com K3d

O cluster local executa a imagem publicada no GHCR e reutiliza o PostgreSQL do Compose. Os valores de imagem versionados servem como referência para uso manual; o workflow substitui a imagem pelo SHA completo da execução atual. O pacote está público, então não é necessário criar `imagePullSecret`.

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

Para executar manualmente uma migração, use uma referência de imagem publicada e um nome exclusivo para o Job. O workflow gera o nome com o ID da execução e remove automaticamente Jobs concluídos após 24 horas:

```bash
IMAGE_REF='ghcr.io/guilhermesemog/devops-trabalho-final:<sha>'
MIGRATION_JOB="task-manager-migration-manual-$(date +%s)-$$"
sed -E \
  -e "s|name: task-manager-migration$|name: ${MIGRATION_JOB}|" \
  -e "s|image: ghcr.io/guilhermesemog/devops-trabalho-final:[^[:space:]]+|image: ${IMAGE_REF}|" \
  kubernetes/migration-job.yaml | kubectl apply -f -
kubectl wait --for=condition=complete "job/${MIGRATION_JOB}" \
    --namespace task-manager --timeout=330s
sed -E \
  "s|image: ghcr.io/guilhermesemog/devops-trabalho-final:[^[:space:]]+|image: ${IMAGE_REF}|" \
  kubernetes/deployment.yaml | kubectl apply -f -
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
IMAGE_REF='ghcr.io/guilhermesemog/devops-trabalho-final:47500425f393c2679f6282cac8be30e8ce953ef5'
nomad job validate -var-file=nomad/local.auto.hcl -var="image=${IMAGE_REF}" nomad/task-manager-migration.nomad
nomad job run -var-file=nomad/local.auto.hcl -var="image=${IMAGE_REF}" nomad/task-manager-migration.nomad
nomad job status task-manager-migration

nomad job validate -var-file=nomad/local.auto.hcl -var="image=${IMAGE_REF}" nomad/task-manager-api.nomad
nomad job run -var-file=nomad/local.auto.hcl -var="image=${IMAGE_REF}" nomad/task-manager-api.nomad
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

## Nomad persistente para CI/CD

O workflow integrado usa um agente single-node persistente, diferente do modo `-dev` temporário da etapa anterior. O serviço de sistema executa como root para que o Docker driver funcione; RPC, Serf e HTTP/UI ficam limitados a loopback. O cliente Nomad usa a interface `lo`, então as portas dinâmicas da API também ficam publicadas somente em `127.0.0.1`. ACLs protegem a API e o runner recebe um token de cliente associado somente ao Job `task-manager-api`.

Instale o binário já validado na etapa anterior, a configuração e a unidade systemd:

```bash
sudo -A install -o root -g root -m 0755 "$HOME/.local/bin/nomad" /usr/local/bin/nomad
sudo -A install -d -o root -g root -m 0755 /etc/nomad.d
sudo -A install -o root -g root -m 0644 nomad/agent.hcl /etc/nomad.d/agent.hcl
sudo -A install -o root -g root -m 0644 nomad/nomad.service /etc/systemd/system/nomad.service
sudo -A systemctl daemon-reload
sudo -A systemctl enable --now nomad
```

Crie o arquivo de variáveis que o runner passará ao Job Nomad. Use a URL do banco acessível pelo container Nomad (gateway Docker e porta publicada), não a URL interna `db:5432` do Compose. Restrinja o acesso ao usuário do runner:

```bash
mkdir -p "$HOME/.config/nomad"
chmod 700 "$HOME/.config/nomad"
```

Crie `~/.config/nomad/task-manager.auto.hcl` sem adicionar o arquivo ao repositório:

```hcl
database_url = "postgresql+psycopg://<usuario>:<senha>@172.17.0.1:5433/task_manager"
```

URL-encode caracteres reservados na URL e aplique `chmod 600 "$HOME/.config/nomad/task-manager.auto.hcl"`.

Inicialize ACLs uma única vez. O token de bootstrap é salvo em arquivo somente root; não o imprima nem o copie para o usuário do runner:

```bash
sudo -A install -d -o root -g root -m 0700 /root/.config/nomad
sudo -A sh -c 'umask 077; /usr/local/bin/nomad acl bootstrap > /root/.config/nomad/bootstrap.txt'
```

Use o token de bootstrap para aplicar a política limitada ao Job da API e criar o token do runner. O JSON com o token gerado fica temporariamente sob `/root`; o comando de extração grava apenas o `SecretID` no arquivo local do runner sem exibi-lo no terminal:

```bash
sudo -A sh -c 'set -eu; umask 077; export NOMAD_TOKEN="$(sed -n "s/^Secret ID[[:space:]]*=[[:space:]]*//p" /root/.config/nomad/bootstrap.txt)"; /usr/local/bin/nomad acl policy apply -namespace=default -job=task-manager-api task-manager-api-ci "$1"; /usr/local/bin/nomad acl token create -name=task-manager-ci -policy=task-manager-api-ci -json > /root/.config/nomad/ci-token.json' sh "$PWD/nomad/ci-deploy-policy.hcl"
sudo -A python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["SecretID"])' /root/.config/nomad/ci-token.json > "$HOME/.config/nomad/ci-deploy.token"
sudo -A rm -f /root/.config/nomad/ci-token.json
sudo -A chown "$USER:$(id -gn)" "$HOME/.config/nomad/ci-deploy.token"
chmod 600 "$HOME/.config/nomad/ci-deploy.token"
```

Execute o comando de política a partir da raiz do repositório e substitua `<usuario>` e `<senha>` pela conexão do Compose. Se o ACL bootstrap já foi executado, não o execute novamente; mantenha o token de gestão root-only para futuras operações administrativas. O token `ci-deploy.token` é usado pelo workflow, não é um GitHub Actions secret.

Configure o runner self-hosted em **Settings → Actions → Runners** do repositório. Selecione Linux x64, adicione o label `deploy` e instale-o como serviço do mesmo usuário dono de `~/.kube/config` e `~/.config/nomad`. O token de registro disponibilizado pelo GitHub é temporário; use-o diretamente no host e não o armazene no repositório. Confirme que o cluster K3d e o serviço Nomad estão ativos antes de habilitar o fluxo.

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
- `nomad/`: Jobs HCL, configuração systemd e política ACL; segredos e variáveis locais não são versionados.

Kubernetes e Nomad usam a mesma imagem da API; o PostgreSQL permanece independente deles.
