variable "vpc_cidrs" {
  description = "vpc cidrs"
  type        = string
}

variable "name_prefix" {
  type        = string
  default     = "John-App"
  description = "Prefix to attach to each of the names of the resources"
}

variable "ha" {
  type        = number
  default     = "3"
  description = "High Availabilty Redundancy"
}
