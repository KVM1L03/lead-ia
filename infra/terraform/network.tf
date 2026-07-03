# ── VPC ───────────────────────────────────────────────────────────────────────
# auto_create_subnetworks = false means GCP won't auto-create a subnet in every
# region. We create exactly one subnet below, in our chosen region only.

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "lead-forge-vpc"
  auto_create_subnetworks = false

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [google_project_service.apis]
}

# ── Subnet ────────────────────────────────────────────────────────────────────
# Private IP range for Cloud SQL, Redis, and Cloud Run egress.
# 10.0.0.0/24 = 254 usable addresses — plenty for this demo.

resource "google_compute_subnetwork" "subnet" {
  project       = var.project_id
  name          = "lead-forge-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.0.0.0/24"

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }
}

# ── Serverless VPC Access connector ───────────────────────────────────────────
# Cloud Run services are "serverless" — they run outside the VPC by default.
# This connector gives them a tunnel to reach private IPs (Cloud SQL, Redis)
# on the VPC above.
#
# ip_cidr_range must be a /28 that does NOT overlap with any subnet CIDR.
# 10.8.0.0/28 is safely separate from the 10.0.0.0/24 subnet above.
#
# min_instances=2 / max_instances=3 on e2-micro: ~$0.02/hr at rest.
# Scale up if you see connector saturation warnings in Cloud Logging.

resource "google_vpc_access_connector" "connector" {
  project       = var.project_id
  name          = "lead-forge-connector"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.8.0.0/28"

  min_instances = 2
  max_instances = 3
  machine_type  = "e2-micro"

  labels = {
    environment = var.environment
    managed-by  = "terraform"
  }

  depends_on = [google_project_service.apis]
}
