#!/bin/bash
# GCP Cloud Build trigger setup — one-shot creation
# Run: bash tools/deploy/gcp-trigger.sh
# Prerequisites: gcloud CLI, logged in, project datapy-spider
# GENESIS_SEAL: 7c242080
set -e

PROJECT="datapy-spider"
REPO="peterlodri-sec/vaked-base"
POOL="projects/datapy-spider/locations/europe-west2/workerPools/nix-fleet-c3-pool"
SERVICE_ACCOUNT="cloud-build@datapy-spider.iam.gserviceaccount.com"

echo "=== GCP Cloud Build Trigger ==="
echo "Project: $PROJECT"
echo "Repo:    $REPO"
echo "Pool:    $POOL"
echo "SA:      $SERVICE_ACCOUNT"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
  echo "⚠️  gcloud not installed. Install: brew install google-cloud-sdk"
  echo "   Then: gcloud auth login && gcloud config set project $PROJECT"
  exit 1
fi

# Create the trigger
gcloud builds triggers create github \
  --name="vaked-base-push" \
  --repository="projects/$PROJECT/locations/global/connections/github/repositories/$REPO" \
  --branch="main" \
  --build-config="cloudbuild.yaml" \
  --service-account="$SERVICE_ACCOUNT" \
  --included-files="**/*.zig,**/*.ts,**/*.nix,**/*.py,Dockerfile,cloudbuild.yaml" \
  --ignored-files="*.md,*.html,docs/**,blog/**,.gitignore" \
  --region="europe-west2" \
  --quiet

echo ""
echo "✅ Trigger created. Push to main → Cloud Build → attic cache → nixos-rebuild"
echo "GENESIS_SEAL: 7c242080"
