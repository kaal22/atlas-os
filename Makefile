VERSION := $(shell cat VERSION)
PROFILE ?= core
CACHE_DIR ?= $(CURDIR)/build-cache
RELEASE_DIR ?= $(CURDIR)/release
OUT_DIR ?= $(CURDIR)/dist

.PHONY: help deps catalog lock-refresh verify-cache build-debs iso oem recovery \
	test-unit test-integration test-install test-security clean sbom sign

help:
	@echo "Atlas OS $(VERSION) — targets:"
	@echo "  deps            Install build dependencies (Debian host)"
	@echo "  catalog         Validate sources.catalog.yaml"
	@echo "  lock-refresh    Resolve digests / hashes (requires network)"
	@echo "  verify-cache    Verify build-cache against sources.lock.yaml"
	@echo "  build-debs      Build Atlas Debian packages"
	@echo "  iso             Build hybrid ISO (offline, profile=$(PROFILE))"
	@echo "  oem             Build OEM disk image"
	@echo "  recovery        Build recovery ISO"
	@echo "  test-unit       Run unit tests"
	@echo "  test-integration Run integration tests"
	@echo "  test-install    QEMU UEFI install smoke test"
	@echo "  test-security   Security regression tests"
	@echo "  sbom            Generate SPDX SBOM"
	@echo "  sign            Sign release artefacts"
	@echo "  clean           Remove build artefacts"

deps:
	./scripts/install-build-deps.sh

catalog:
	./scripts/validate-catalog.sh $(RELEASE_DIR)/sources.catalog.yaml

lock-refresh:
	./scripts/lock-refresh.sh $(RELEASE_DIR) $(CACHE_DIR)

verify-cache:
	./scripts/verify-cache.sh $(RELEASE_DIR)/sources.lock.yaml $(CACHE_DIR)

build-debs:
	./scripts/build-debs.sh $(OUT_DIR)/debs

iso: verify-cache build-debs
	./scripts/build-iso.sh --profile $(PROFILE) --cache $(CACHE_DIR) --out $(OUT_DIR)

oem:
	./scripts/build-oem-image.sh --cache $(CACHE_DIR) --out $(OUT_DIR)

recovery:
	./scripts/build-iso.sh --profile recovery --cache $(CACHE_DIR) --out $(OUT_DIR)

test-unit:
	./scripts/test-unit.sh

test-integration:
	./scripts/test-integration.sh

test-install:
	./scripts/test-release.sh install

test-security:
	./scripts/test-security.sh

sbom:
	./scripts/generate-sbom.sh $(OUT_DIR)

sign:
	./scripts/sign-release.sh $(OUT_DIR)

clean:
	rm -rf $(OUT_DIR) build/ chroot/ binary/ .build/
	lb clean || true
