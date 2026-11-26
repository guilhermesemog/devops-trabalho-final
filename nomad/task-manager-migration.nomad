variable "database_url" {
  type = string
}

variable "image" {
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
        image      = var.image
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
