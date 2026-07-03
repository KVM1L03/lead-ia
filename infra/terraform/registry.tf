# Artifact Registry Docker repository.
#
# CI (GitHub Actions or Cloud Build) pushes images here:
#   europe-central2-docker.pkg.dev/PROJECT_ID/lead-forge/lead-api:TAG
#   europe-central2-docker.pkg.dev/PROJECT_ID/lead-forge/lead-worker:TAG
#
# Cloud Run pulls from here at deploy time.
# Storage: $0.10/GB/month — negligible until you accumulate many image layers.

resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = "lead-forge"
  format        = "DOCKER"
  description   = "LeadForge container images (api-gateway, ai-worker)"

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [google_project_service.apis]
}
