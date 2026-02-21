#!/usr/bin/env bash
# Push a tagged release to the public remote.
# Usage: ./scripts/push-public.sh settings-v1.0.0
set -euo pipefail

TAG="${1:?Usage: push-public.sh <tag> (e.g., settings-v1.0.0)}"

# Ensure working tree is clean
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: Working tree is dirty. Commit or stash changes first."
  exit 1
fi

# Validate tag format
if ! echo "$TAG" | grep -qE '^(settings|usage)-v[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: Tag must match pattern: (settings|usage)-vX.Y.Z"
  exit 1
fi

# Validate tag exists
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Error: Tag '$TAG' does not exist. Create it first: git tag $TAG"
  exit 1
fi

# Extract version and package
PACKAGE="${TAG%%-v*}"
VERSION="${TAG##*-v}"

# Validate __about__.py version matches tag
ABOUT_FILE="packages/$PACKAGE/src/claude_tui_${PACKAGE}/__about__.py"
ABOUT_VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ABOUT_FILE")
if [ "$ABOUT_VERSION" != "$VERSION" ]; then
  echo "Error: $ABOUT_FILE has version $ABOUT_VERSION but tag says $VERSION"
  exit 1
fi

# Update release branch to tagged commit
echo "Updating release branch to $TAG..."
git checkout release
git reset --hard "$TAG"

echo "Pushing release to public remote..."
git push public release --force
git push public "$TAG"

git checkout main
echo "Done! $TAG published to public remote."
