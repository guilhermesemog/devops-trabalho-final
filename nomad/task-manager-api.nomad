variable "database_url" {
  type = string
}

variable "image" {
  type = string
}

job "task-manager-api" {
  datacenters = ["dc1"]
  type        = "service"

  group "api" {
    count = 1

    update {
      max_parallel      = 1
      min_healthy_time  = "10s"
      healthy_deadline  = "3m"
      progress_deadline = "5m"
      auto_revert       = true
    }

    network {
      port "http" {
        to = 8000
      }
    }

    restart {
      attempts = 2
      interval = "30m"
      delay    = "15s"
      mode     = "fail"
    }

    task "api" {
      driver         = "docker"
      shutdown_delay = "5s"

      config {
        image      = var.image
        force_pull = true
        ports      = ["http"]
        healthchecks {
          disable = true
        }
      }

      env {
        DATABASE_URL = var.database_url
      }

      resources {
        cpu    = 100
        memory = 128
      }

      service {
        provider = "nomad"
        name     = "task-manager-api"
        port     = "http"

        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "2s"
        }
      }
    }
  }
}
