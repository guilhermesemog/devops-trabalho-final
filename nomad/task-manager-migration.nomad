variable "database_url" {
  type = string
}

job "task-manager-migration" {
  datacenters = ["dc1"]
  type        = "batch"

  group "migration" {
    restart {
      attempts = 0
      mode     = "fail"
    }

    task "alembic" {
      driver = "docker"

      config {
        image      = "ghcr.io/guilhermesemog/devops-trabalho-final:47500425f393c2679f6282cac8be30e8ce953ef5"
        force_pull = true
        command    = "alembic"
        args       = ["upgrade", "head"]
      }

      env {
        DATABASE_URL = var.database_url
      }

      resources {
        cpu    = 100
        memory = 128
      }
    }
  }
}
