variable "database_url" {
  type = string
}

job "task-manager-api" {
  datacenters = ["dc1"]
  type        = "service"

  group "api" {
    count = 1

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
        image      = "ghcr.io/guilhermesemog/devops-trabalho-final:47500425f393c2679f6282cac8be30e8ce953ef5"
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
