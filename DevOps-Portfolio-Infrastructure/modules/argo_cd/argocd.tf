resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "10.2.1"
  namespace        = "argocd"
  create_namespace = true

  values = [
    file("${path.module}/argocd-values.yaml")
  ]

}

data "aws_secretsmanager_secret" "argocd_ssh_key" {
  name = "argocd/github/ssh"
}

data "aws_secretsmanager_secret_version" "argocd_ssh_key" {
  secret_id = data.aws_secretsmanager_secret.argocd_ssh_key.id
}

resource "kubernetes_secret_v1" "argocd_repo_ssh" {
  metadata {
    name      = "repo-github-ssh"
    namespace = "argocd"
    labels = {
      "argocd.argoproj.io/secret-type" = "repository"
    }
  }
  data = {
    type          = "git"
    url           = "git@github.com:shakeddukeman25/DevOps-Portfolio-Cluster_Resources.git"
    sshPrivateKey = jsondecode(data.aws_secretsmanager_secret_version.argocd_ssh_key.secret_string)["git-ssh"]
  }
  type       = "Opaque"
  depends_on = [helm_release.argocd]
}
module "bootstrap" {
  source = "./bootstrap"

  external_secrets_role_arn = var.external_secrets_role_arn

  providers = {
    kubectl = kubectl
    helm    = helm
  }

  depends_on = [
    helm_release.argocd,
    kubernetes_secret_v1.argocd_repo_ssh
  ]
}