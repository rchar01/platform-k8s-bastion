#!/usr/bin/env bash

# Fixed integration contract constants (non-policy).
BASTION_ETC_DIR="/etc/bastion"
POLICY_FILE="${BASTION_ETC_DIR}/access-policy.yaml"
ADMIN_KUBECONFIG_FILE="${BASTION_ETC_DIR}/admin.kubeconfig"

BOOTSTRAP_AUTH_GROUP="system:bootstrappers:platform-users"

CONTROLLER_NAMESPACE="bastion-system"
CSR_APPROVER_SA="bastion-csr-approver"
CSR_SIGNER_SA="bastion-csr-signer"
CSR_CLEANUP_SA="bastion-csr-cleanup"
TOKEN_ISSUER_SA="bastion-token-issuer"

BOOTSTRAP_TOKEN_NAMESPACE="kube-system"
