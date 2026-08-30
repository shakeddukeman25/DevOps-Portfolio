terraform {
  backend "s3" {
    bucket         = "devops-portfolio-tf-state-bucket"
    key            = "global/s3/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    use_path_style = false
    use_lockfile   = true
  }
}