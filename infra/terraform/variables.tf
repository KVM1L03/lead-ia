variable "project_id" {
  description = "GCP project ID (e.g. my-project-123456). Find it in the GCP Console header."
  type        = string
}

variable "region" {
  description = "GCP region for all resources."
  type        = string
  default     = "europe-central2" # Warsaw — lowest latency for you
}

variable "environment" {
  description = "Deployment environment label applied to all resources (demo | staging | prod)."
  type        = string
  default     = "demo"
}
