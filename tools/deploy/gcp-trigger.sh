#!/bin/bash
set -e
PROJECT="datapy-spider"
SA="cloud-build@datapy-spider.iam.gserviceaccount.com"
echo "=== GCP Cloud Build Trigger ==="
gcloud builds triggers create github \
  --name="vaked-base-push" \
  --repository="projects/$PROJECT/locations/global/connections/github/repositories/vaked-base" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --service-account="$SA" \
  --region="europe-west2" \
  --included-files="**/*.zig,**/*.ts,**/*.nix,**/*.py,Dockerfile,cloudbuild.yaml" \
  --ignored-files="*.md,*.html,docs/**,blog/**,.gitignore" \
  --quiet
echo "✅ Trigger created. GENESIS_SEAL: 7c242080"
