# Cluster Resources

The GitOps repository for the Contact Book project. Argo CD — installed by the
[Infrastructure](Infrastructure-README.md) repository — watches this repository and reconciles its
contents into the EKS cluster.

## Overview

Everything that runs in the cluster is defined here as Kubernetes manifests and Argo CD
`Application` resources. Nothing is applied by hand or by CI; Argo CD is the only thing that talks to
the cluster.

## GitOps Model

Deployment is pull-based. The CI pipeline in the application repository commits a new image tag to
this repository; Argo CD detects the commit and syncs the change. A root `Application` (the
App-of-Apps) points at the `applications/` directory and pulls in the child applications defined
there.

## App-of-Apps

| Application | Source | Namespace | Sync |
|---|---|---|---|
| `contact-book` | this repo, `applications/contact-book` | `default` | automated, prune + self-heal |
| `mongodb` | Bitnami `mongodb` chart + this repo, `applications/mongodb` | `mongodb` | automated, prune + self-heal |
| `ingress-nginx` | community `ingress-nginx` chart | `ingress-nginx` | automated, prune + self-heal |

## Namespaces

`argocd` (Argo CD itself), `external-secrets` (the operator), `default` (the application),
`mongodb` (the database), and `ingress-nginx` (the ingress controller). The database and ingress
namespaces are created automatically by their applications.

## ingress-nginx

Installed from the community chart. It provides the `nginx` ingress class and a `LoadBalancer`
service, which AWS fulfils with a load balancer. This is the external entry point for the
application.

## contact-book Workload

Three manifests under `applications/contact-book`:

- **Deployment** — two replicas of the application image; environment variables are loaded from the
  `mongodb-secret` secret.
- **Service** — a `ClusterIP` service mapping port 80 to the container port.
- **Ingress** — routes `/` to the service using the `nginx` ingress class. No host and no TLS.

The image tag in the Deployment is the line the CI pipeline rewrites on every release.

## MongoDB

Deployed from the Bitnami `mongodb` chart as a three-member replica set with authentication enabled
and persistence on the default gp3 storage class. It consumes its credentials from an existing
secret (`mongodb-auth`) that External Secrets Operator produces.

## External Secrets Operator

A `ClusterSecretStore` named `aws-secrets-manager` connects the operator to AWS Secrets Manager,
authenticating through the operator's IRSA-annotated service account. All `ExternalSecret` and
`PushSecret` resources reference this store.

## PushSecret / ExternalSecret Flow

1. A `Password` generator creates the MongoDB passwords inside the cluster.
2. An `ExternalSecret` materialises them into the `mongodb-auth` secret, which the MongoDB chart
   consumes.
3. A `PushSecret` copies those values up to AWS Secrets Manager.
4. A separate `ExternalSecret` in the `default` namespace reads them back from Secrets Manager and
   renders the `mongodb-secret` used by the application, including a ready-to-use connection string.

No database password is ever stored in Git.

## AWS Secrets Manager Integration

The generated MongoDB credentials live under a single Secrets Manager entry. The application's
`ExternalSecret` refreshes hourly; the MongoDB credentials are written once and then left in place.

## Synchronization Behavior

Every application syncs automatically with **prune** (remove resources deleted from Git) and
**self-heal** (revert manual drift) enabled. There are no sync waves, so on a first install the
resources may reconcile in more than one pass before everything settles.

## Reconciliation / Rollback

Argo CD continuously reconciles the cluster to match Git. To roll back a release, revert the image
tag commit in this repository; Argo CD applies the previous version on the next sync. There is no
progressive delivery or automated rollback on failed health checks.

## Configuration Relationships

- The application Deployment depends on the `mongodb-secret` secret rendered by the `default`
  namespace `ExternalSecret`.
- That `ExternalSecret` depends on the `ClusterSecretStore` shipped with the `mongodb` application.
- The MongoDB chart depends on the `mongodb-auth` secret produced by the operator.
- Persistent volumes bind to the default gp3 storage class created by Terraform.

## Accessing Argo CD

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
# then open https://localhost:8080  (user: admin)

kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d
```

## Limitations

- The application Deployment defines no liveness/readiness probes and no resource requests or limits.
- There are no NetworkPolicies; traffic between namespaces is unrestricted.
- The ingress serves plain HTTP; there is no TLS and no cert-manager.
- First-run sync ordering is not guaranteed and relies on self-heal to converge.
