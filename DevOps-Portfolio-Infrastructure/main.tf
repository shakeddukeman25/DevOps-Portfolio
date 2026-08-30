locals {
  name_prefix = "${var.common_tags.owner}-${var.common_tags.app_name}"
}

module "network" {
  source      = "./modules/network"
  name_prefix = local.name_prefix
  vpc_cidrs   = var.vpc_cidrs
  ha          = var.ha
}

module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "~> 20.31"
  cluster_name    = "${var.common_tags.owner}-cluster"
  cluster_version = var.cluster_version
  subnet_ids      = module.network.subnet_ids
  vpc_id          = module.network.vpc_id

  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    main = {
      name         = "${var.common_tags.owner}-eks-node"
      desired_size = 2
      max_size     = 3
      min_size     = 2

      instance_types = [var.node_type]

      # grant access to private ECR
      iam_role_additional_policies = {
        AmazonEC2ContainerRegistryReadOnly = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
      }
    }
  }
}

module "eks_blueprints_addons" {
  source  = "aws-ia/eks-blueprints-addons/aws"
  version = "~> 1.0"

  cluster_name      = module.eks.cluster_name
  cluster_endpoint  = module.eks.cluster_endpoint
  cluster_version   = module.eks.cluster_version
  oidc_provider_arn = module.eks.oidc_provider_arn

  eks_addons = {
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa_role.iam_role_arn
    }
    coredns = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
  }
  #   enable_metrics_server                  = true
}

module "ebs_csi_irsa_role" {
  source                = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version               = "5.30.0"
  role_name             = "${local.name_prefix}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    ex = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

module "ebs_csi_storageclass" {
  source                 = "./modules/ebs-csi-storageclass"
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.this.token
}
# Allows External Secrets to read, create and update secrets in AWS Secrets Manager
resource "aws_iam_policy" "external_secrets_policy" {
  name = "external-secrets-policy"

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:CreateSecret",
          "secretsmanager:PutSecretValue",
          "secretsmanager:TagResource",
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:PutResourcePolicy",
          "secretsmanager:DeleteResourcePolicy"
        ]

        Resource = "*"
      }
    ]
  })
}
# Creates an IAM Role that allows the External Secrets ServiceAccount in EKS to use the Secrets Manager permissions
module "external_secrets_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.30.0"

  role_name = "${local.name_prefix}-external-secrets"

  role_policy_arns = {
    external_secrets = aws_iam_policy.external_secrets_policy.arn
  }

  oidc_providers = {
    ex = {
      provider_arn = module.eks.oidc_provider_arn

      namespace_service_accounts = [
        "external-secrets:external-secrets"
      ]
    }
  }
}
module "argo_cd" {
  source = "./modules/argo_cd"

  external_secrets_role_arn = module.external_secrets_irsa_role.iam_role_arn

  providers = {
    kubectl    = kubectl
    helm       = helm
    kubernetes = kubernetes
  }

  depends_on = [
    module.eks,
    module.eks_blueprints_addons
  ]
}
