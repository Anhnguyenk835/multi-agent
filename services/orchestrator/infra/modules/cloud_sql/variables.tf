variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "instance_name" {
  type = string
}

variable "database_name" {
  type    = string
  default = "distributed_agents"
}

variable "database_user" {
  type    = string
  default = "distributed_agents"
}

variable "tier" {
  type        = string
  default     = "db-g1-small"
  description = "Smallest generally-available tier; fine for a demo, not for real load."
}
