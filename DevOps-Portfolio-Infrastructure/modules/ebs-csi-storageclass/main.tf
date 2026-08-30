# remove default storage class annotation from gp2
resource "kubernetes_annotations" "gp2_not_as_default" {
  api_version = "storage.k8s.io/v1"
  kind        = "StorageClass"
  force       = "true"

  metadata {
    name = "gp2"
  }

  annotations = {
    "storageclass.kubernetes.io/is-default-class" = "false"
  }
}

# create gp3 storage class and set as default 
resource "kubernetes_storage_class_v1" "gp3" {
  metadata {
    name = "ebs-csi-gp3"

    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  allow_volume_expansion = true
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"

  parameters = {
    # encrypted = true
    "csi.storage.k8s.io/fstype" = "ext4"
    type                        = "gp3"
  }
}
