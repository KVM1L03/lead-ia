# Enable all GCP APIs required by LeadForge services.
#
# Using for_each over a set means each API is a separate Terraform resource —
# you can add/remove individual APIs without touching the others.
#
# disable_on_destroy = false: when you run `terraform destroy`, Terraform will
# NOT disable these APIs. This prevents accidentally breaking other workloads
# that might be running in the same project.

locals {
  required_apis = toset([
    "run.googleapis.com",              # Cloud Run (api_gateway + ai_worker)
    "artifactregistry.googleapis.com", # Artifact Registry (Docker images)
    "secretmanager.googleapis.com",    # Secret Manager (ANTHROPIC_API_KEY etc.)
    "sqladmin.googleapis.com",         # Cloud SQL (Postgres — next ticket)
    "redis.googleapis.com",            # Memorystore Redis (next ticket)
    "vpcaccess.googleapis.com",        # Serverless VPC Access connector
    "compute.googleapis.com",          # VPC, subnets, networking
    "cloudbuild.googleapis.com",       # CI image builds (future)
  ])
}

resource "google_project_service" "apis" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
