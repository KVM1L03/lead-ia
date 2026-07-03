# LeadForge — Terraform (GCP)

This directory manages the GCP infrastructure for LeadForge using Terraform.

> **Scope of this config:** VPC, subnet, Serverless VPC connector, Artifact Registry, and API enablement.
> Cloud Run, Cloud SQL, and Redis are in separate tickets — not here yet.

---

## What each file does

| File | Purpose |
|---|---|
| `versions.tf` | Pins Terraform ≥ 1.9 and Google provider ~> 6.0; configures GCS remote state backend |
| `variables.tf` | Declares input variables: `project_id`, `region`, `environment` |
| `providers.tf` | Configures the Google Cloud provider with your project and region |
| `apis.tf` | Enables required GCP APIs (Cloud Run, Artifact Registry, Secret Manager, …) |
| `network.tf` | VPC, subnet (10.0.0.0/24), Serverless VPC Access connector (10.8.0.0/28) |
| `registry.tf` | Artifact Registry Docker repository where CI pushes container images |
| `terraform.tfvars.example` | Template for your variable values — copy to `terraform.tfvars` |

---

## Prerequisites

1. **GCP project** — create one at console.cloud.google.com if you don't have one
2. **gcloud CLI** — install from https://cloud.google.com/sdk/docs/install
3. **Authenticate:**
   ```bash
   gcloud auth login
   gcloud auth application-default login   # Terraform uses this
   ```
4. **Terraform** — install from https://developer.hashicorp.com/terraform/downloads
   ```bash
   terraform version   # should print >= 1.9
   ```

---

## One-time setup — GCS state bucket

Terraform needs somewhere to store its state file. You can't use Terraform to create
the state bucket itself (chicken-and-egg), so create it manually once:

```bash
export PROJECT_ID=your-gcp-project-id   # replace with your real project ID

gcloud storage buckets create gs://${PROJECT_ID}-tf-state \
  --project=${PROJECT_ID} \
  --location=europe-central2 \
  --uniform-bucket-level-access
```

This bucket name — `{project_id}-tf-state` — matches what you'll pass to `terraform init` below.
You only do this once. The bucket persists across `terraform destroy`.

---

## Day-to-day workflow

All commands run from this directory (`infra/terraform/`).

### 1. Copy and fill your variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set `project_id` to your real GCP project ID.
(`terraform.tfvars` is git-ignored — it never leaves your machine.)

### 2. Init — download providers and connect to remote state

```bash
export PROJECT_ID=$(grep project_id terraform.tfvars | awk -F'"' '{print $2}')

terraform init -backend-config="bucket=${PROJECT_ID}-tf-state"
```

`terraform init` downloads the Google provider plugin (~40 MB) and connects to the GCS
state bucket. Run it once after cloning, and again whenever you change `versions.tf`.

### 3. Plan — dry run (READ THIS CAREFULLY)

```bash
terraform plan
```

The plan shows every resource Terraform will create, update, or destroy.
**Always read the plan before applying.** Key symbols:

| Symbol | Meaning |
|---|---|
| `+` | Resource will be **created** |
| `-` | Resource will be **destroyed** |
| `~` | Resource will be **updated in-place** (no disruption) |
| `-/+` | Resource will be **replaced** (destroy + create) — check why! |

At the bottom you'll see a summary like `Plan: 12 to add, 0 to change, 0 to destroy`.

### 4. Apply — create the resources

```bash
terraform apply
```

Terraform prints the plan again and asks for confirmation. Type `yes` to proceed.
Takes a few minutes on first apply (API enablement can take up to 60 seconds each).

After apply, you can verify in the GCP Console:
- **VPC Networks** → `lead-forge-vpc`
- **Artifact Registry** → `lead-forge` repository in `europe-central2`
- **VPC Access connectors** → `lead-forge-connector`
- **APIs & Services** → all 8 APIs enabled

### 5. Destroy — remove everything (use this to clean up)

```bash
terraform destroy
```

Removes all resources Terraform created. Asks for confirmation.
The GCS state bucket is NOT destroyed (you created it manually).
The 8 APIs are NOT disabled (`disable_on_destroy = false`) — this prevents
accidentally breaking other workloads in the project.

---

## How Terraform state works

Terraform keeps a `terraform.tfstate` file that records the real GCP resource IDs
for everything it manages. Without it, Terraform can't track what it created.

We store state in a GCS bucket (remote state) so:
- It's backed up automatically
- Multiple people can work on the same infra without conflicts
- It survives if your local machine dies

**Never delete the state bucket.** If you lose state, Terraform will try to
re-create resources that already exist, causing errors.

---

## Cost when applied

| Resource | Cost |
|---|---|
| VPC + subnet | **Free** |
| Serverless VPC connector (2× e2-micro) | ~$0.02/hr ≈ $14/month while running |
| Artifact Registry storage | $0.10/GB/month (free until you push images) |
| API enablement | **Free** |

Run `terraform destroy` when you're done experimenting to stop the VPC connector cost.

---

## Pushing Docker images to the registry

After `terraform apply`, configure Docker to authenticate with Artifact Registry:

```bash
gcloud auth configure-docker europe-central2-docker.pkg.dev
```

Then tag and push your images:

```bash
export PROJECT_ID=your-gcp-project-id
export TAG=latest

# Build (from repo root)
docker build -f api_gateway/Dockerfile -t lead-api .
docker build -f ai_worker/Dockerfile  -t lead-worker .

# Tag
docker tag lead-api   europe-central2-docker.pkg.dev/${PROJECT_ID}/lead-forge/lead-api:${TAG}
docker tag lead-worker europe-central2-docker.pkg.dev/${PROJECT_ID}/lead-forge/lead-worker:${TAG}

# Push
docker push europe-central2-docker.pkg.dev/${PROJECT_ID}/lead-forge/lead-api:${TAG}
docker push europe-central2-docker.pkg.dev/${PROJECT_ID}/lead-forge/lead-worker:${TAG}
```

---

## What's NOT in this config yet

- **Cloud Run services** — next ticket (api_gateway, ai_worker)
- **Cloud SQL (Postgres)** — next ticket
- **Memorystore (Redis)** — next ticket
- **Secret Manager secrets** — ANTHROPIC_API_KEY, SERPAPI_API_KEY, etc.
- **IAM service accounts** — for Cloud Run → Cloud SQL / Artifact Registry access
- **CI/CD pipeline** — GitHub Actions pushing images on PR merge
