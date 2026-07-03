terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Partial backend — bucket is supplied at init time to avoid hardcoding
  # the project ID in a version-controlled file:
  #
  #   terraform init -backend-config="bucket=YOUR_PROJECT_ID-tf-state"
  #
  # See README.md for the one-time bucket creation command.
  backend "gcs" {
    prefix = "terraform/state"
  }
}
