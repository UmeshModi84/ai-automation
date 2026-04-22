variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Prefix for resource names"
  default     = "ai-cicd"
}

variable "environment" {
  type        = string
  description = "Environment tag"
  default     = "production"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.42.1.0/24"
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key for EC2 access"
  sensitive   = true
}

variable "allowed_cidr" {
  type        = string
  description = "CIDR allowed to reach SSH/HTTP (use your IP/32 for SSH)"
  default     = "0.0.0.0/0"
}

variable "ghcr_username" {
  type        = string
  description = "GitHub username or org for GHCR login"
  default     = ""
}

variable "ghcr_token" {
  type        = string
  description = "PAT with read:packages for docker pull"
  default     = ""
  sensitive   = true
}

variable "app_image" {
  type        = string
  description = "Full image ref e.g. ghcr.io/org/repo:tag"
  default     = "ghcr.io/example/app:latest"
}
