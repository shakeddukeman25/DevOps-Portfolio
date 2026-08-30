# Infrastructure

Terraform that provisions the AWS environment for the Contact Book project and bootstraps the
in-cluster GitOps tooling. A single `terraform apply` builds the network and an EKS cluster, adds the
core cluster add-ons and a default storage class, and installs Argo CD and External Secrets Operator.

## Overview

The root module wires together a small local network module, the community EKS and IAM modules, and
a local module that installs Argo CD. After it runs, Argo CD takes over and reconciles the
[Cluster Resources](Cluster-Resources-README.md) repository into the cluster.

## Prerequisites

- Terraform and the AWS CLI, with credentials for the target account.
- `kubectl` for connecting to the cluster afterwards.
- An S3 bucket for Terraform state (referenced by the backend configuration).
- An AWS Secrets Manager secret holding the SSH deploy key Argo CD uses to read the GitOps
  repository. It must exist before `apply`.

## Terraform Architecture

| Module | Source | Responsibility |
|---|---|---|
| `network` | local | VPC, internet gateway, public subnets, routing |
| `eks` | `terraform-aws-modules/eks/aws` | EKS control plane and a managed node group |
| `eks_blueprints_addons` | `aws-ia/eks-blueprints-addons/aws` | CoreDNS, VPC CNI, kube-proxy, EBS CSI driver |
| `ebs_csi_irsa_role`, `external_secrets_irsa_role` | `terraform-aws-modules/iam/aws` | scoped IRSA roles |
| `ebs_csi_storageclass` | local | default gp3 storage class |
| `argo_cd` (+ `bootstrap`) | local | Argo CD and External Secrets Operator Helm releases, App-of-Apps root |

## Providers

- `aws` (pinned to the 5.x line) for all cloud resources.
- `kubernetes`, `helm`, and `kubectl` for the in-cluster bootstrap; these authenticate to EKS with
  the `aws eks get-token` exec plugin, so no kubeconfig is required.

## Remote State

State is stored in S3 with encryption enabled and native S3 state locking (no DynamoDB table).

## Networking

The `network` module creates a VPC, an internet gateway, one route table with a default route to the
gateway, and one public subnet per availability zone (capped by a redundancy variable). All subnets
are public — there are no private subnets and no NAT gateway. The EKS control plane and the worker
nodes both run in these subnets.

## EKS

A single EKS cluster is created with the Kubernetes version supplied as a variable. The API endpoint
is configured for public access. Kubernetes secret encryption uses a KMS key, and an OIDC provider
is created so in-cluster service accounts can assume IAM roles (IRSA). Control-plane logs are sent to
CloudWatch.

## Node Group

One managed node group with a fixed instance type and a small desired/min/max range. The node role
is granted read-only access to Amazon ECR so it can pull the application image.

## EKS Add-ons

The blueprints add-ons module installs only the essentials: **CoreDNS**, **VPC CNI**, **kube-proxy**,
and the **EBS CSI driver** (bound to its IRSA role). No load balancer controller, autoscaler, or
monitoring add-ons are enabled.

## Storage

The `gp2` storage class is un-marked as default and a new `gp3` storage class is created and set as
the default. It uses `WaitForFirstConsumer` binding, allows volume expansion, and reclaims volumes on
delete. Encryption at rest is not enabled on the storage class.

## IAM / IRSA

Two IRSA roles are created:

- one for the **EBS CSI controller** service account, using the module's managed EBS policy;
- one for the **External Secrets Operator** service account, attached to a custom policy that grants
  Secrets Manager read/write actions.

## Argo CD Bootstrap

Argo CD is installed from its Helm chart into the `argocd` namespace with TLS termination disabled at
the server and no ingress (access is via port-forward). Terraform reads the GitHub SSH deploy key
from AWS Secrets Manager and writes it into a Kubernetes secret Argo CD recognises as a repository
credential. A root `Application` (App-of-Apps) is then applied, pointing Argo CD at the
`applications/` path of the Cluster Resources repository with automated prune and self-heal.

## External Secrets Bootstrap

External Secrets Operator is installed from its Helm chart into the `external-secrets` namespace. Its
service account is annotated with the IRSA role ARN so the controller can reach AWS Secrets Manager.

## Important Variables

| Variable | Purpose |
|---|---|
| `region` | AWS region for the deployment |
| `vpc_cidrs` | VPC CIDR block |
| `ha` | number of availability zones / subnets to spread across |
| `cluster_version` | Kubernetes version for EKS |
| `node_type` | worker node instance type |
| `common_tags` | owner / naming tags applied to resources |

Real values are supplied through a `terraform.tfvars` file that is not committed. Some variable
defaults in the module are template placeholders and are expected to be overridden.

## Terraform Execution Flow

1. Provide `terraform.tfvars` and ensure the state bucket and the Argo CD SSH secret exist.
2. `terraform init` to download providers and modules.
3. `terraform plan` and review.
4. `terraform apply` — network, then EKS (~15 minutes), then add-ons, then Argo CD and External
   Secrets.
5. Run the `cluster_connect` output to configure `kubectl`, then `kubectl get nodes`.
6. Argo CD begins reconciling the Cluster Resources repository automatically.

## Teardown

Remove the Argo CD applications first so it does not fight the deletion, then `terraform destroy`.
Note that credentials pushed to AWS Secrets Manager are not removed by `destroy`.

## Limitations

- The EKS API endpoint is publicly reachable and is not restricted to specific source ranges.
- All networking is on public subnets; there are no private subnets or NAT gateway.
- The default storage class does not enable EBS encryption at rest.
- The `kubernetes`, `helm`, and `kubectl` providers are not version-pinned in the configuration.
- The infrastructure runbook text is older than the current Terraform and disagrees with it on the
  Kubernetes version and node count.
